"""Butler Human-in-the-Loop (HITL) Middleware.

Implements approval interrupts for sensitive operations.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from langchain.middleware.base import (
    ButlerBaseMiddleware,
    ButlerMiddlewareContext,
    MiddlewareResult,
)

import structlog

logger = structlog.get_logger(__name__)


class ApprovalStrategy(str, Enum):
    """Strategy for handling approval requests."""

    AUTO_APPROVE = "auto_approve"
    AUTO_DENY = "auto_deny"
    MANUAL = "manual"


class ApprovalStatus(str, Enum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    CANCELLED = "cancelled"


@dataclass
class ApprovalRequest:
    """A request for human approval."""

    request_id: str
    tenant_id: str
    account_id: str
    session_id: str
    trace_id: str
    operation_type: str  # "tool_call", "model_output", "sensitive_action"
    operation_details: dict[str, Any]
    status: ApprovalStatus = ApprovalStatus.PENDING
    strategy: ApprovalStrategy = ApprovalStrategy.MANUAL
    metadata: dict[str, Any] = field(default_factory=dict)

    def approve(self):
        """Approve the request."""
        self.status = ApprovalStatus.APPROVED

    def deny(self):
        """Deny the request."""
        self.status = ApprovalStatus.DENIED

    def cancel(self):
        """Cancel the request."""
        self.status = ApprovalStatus.CANCELLED


class ButlerHITLMiddleware(ButlerBaseMiddleware):
    """Middleware for Human-in-the-Loop approval interrupts.

    This middleware:
    - Intercepts tool calls and model outputs requiring approval
    - Stores approval requests for human review
    - Blocks execution until approval is granted
    - Supports different approval strategies
    """

    def __init__(
        self,
        enabled: bool = True,
        strategy: ApprovalStrategy = ApprovalStrategy.MANUAL,
        require_tool_approval: bool = True,
        sensitive_tools: list[str] | None = None,
        require_output_approval: bool = False,
    ):
        super().__init__(enabled=enabled)
        self._strategy = strategy
        self._require_tool_approval = require_tool_approval
        self._sensitive_tools = set(sensitive_tools or [])
        self._require_output_approval = require_output_approval
        self._pending_approvals: dict[str, ApprovalRequest] = {}

    def get_pending_approvals(self) -> list[ApprovalRequest]:
        """Get all pending approval requests."""
        return [
            req for req in self._pending_approvals.values() if req.status == ApprovalStatus.PENDING
        ]

    def get_approval_request(self, request_id: str) -> ApprovalRequest | None:
        """Get an approval request by ID."""
        return self._pending_approvals.get(request_id)

    def approve_request(self, request_id: str) -> bool:
        """Approve a pending request."""
        request = self._pending_approvals.get(request_id)
        if request and request.status == ApprovalStatus.PENDING:
            request.approve()
            logger.info(
                "approval_request_approved",
                request_id=request_id,
                operation_type=request.operation_type,
            )
            return True
        return False

    def deny_request(self, request_id: str) -> bool:
        """Deny a pending request."""
        request = self._pending_approvals.get(request_id)
        if request and request.status == ApprovalStatus.PENDING:
            request.deny()
            logger.info(
                "approval_request_denied",
                request_id=request_id,
                operation_type=request.operation_type,
            )
            return True
        return False

    async def pre_tool(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Check tool calls for approval requirements."""
        if not self._require_tool_approval:
            return MiddlewareResult(success=True, should_continue=True)

        for tool_call in context.tool_calls:
            tool_name = tool_call.get("name", "")
            tool_args = tool_call.get("args", {})

            # Check if tool requires approval
            requires_approval = (
                tool_name in self._sensitive_tools
                or tool_name.startswith("sensitive_")
                or "email" in tool_name.lower()
                or "payment" in tool_name.lower()
                or "delete" in tool_name.lower()
            )

            if not requires_approval:
                continue

            # Create approval request
            request_id = f"{context.session_id}_{context.trace_id}_{tool_name}"
            approval_request = ApprovalRequest(
                request_id=request_id,
                tenant_id=context.tenant_id,
                account_id=context.account_id,
                session_id=context.session_id,
                trace_id=context.trace_id,
                operation_type="tool_call",
                operation_details={
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                },
                strategy=self._strategy,
            )

            self._pending_approvals[request_id] = approval_request

            # Handle based on strategy
            if self._strategy == ApprovalStrategy.AUTO_APPROVE:
                approval_request.approve()
                logger.info(
                    "auto_approved_tool_call",
                    tool_name=tool_name,
                    request_id=request_id,
                )
            elif self._strategy == ApprovalStrategy.AUTO_DENY:
                approval_request.deny()
                logger.warning(
                    "auto_denied_tool_call",
                    tool_name=tool_name,
                    request_id=request_id,
                )
                return MiddlewareResult(
                    success=False,
                    should_continue=False,
                    error=f"Tool call denied by HITL policy: {tool_name}",
                    metadata={"approval_request_id": request_id},
                )
            else:
                # Manual approval required
                logger.info(
                    "approval_required_tool_call",
                    tool_name=tool_name,
                    request_id=request_id,
                )
                return MiddlewareResult(
                    success=False,
                    should_continue=False,
                    error=f"Approval required for tool call: {tool_name}",
                    metadata={"approval_request_id": request_id},
                )

        return MiddlewareResult(success=True, should_continue=True)

    async def post_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Check model outputs for approval requirements."""
        if not self._require_output_approval:
            return MiddlewareResult(success=True, should_continue=True)

        # Check for sensitive content in output
        messages = context.messages
        if not messages:
            return MiddlewareResult(success=True, should_continue=True)

        last_message = messages[-1] if messages else None
        if not last_message:
            return MiddlewareResult(success=True, should_continue=True)

        content = last_message.get("content", "")
        # Simple heuristics for sensitive content
        sensitive_keywords = [
            "password",
            "api_key",
            "secret",
            "credit_card",
            "ssn",
            "social_security",
        ]

        requires_approval = any(keyword in content.lower() for keyword in sensitive_keywords)

        if requires_approval:
            request_id = f"{context.session_id}_{context.trace_id}_output"
            approval_request = ApprovalRequest(
                request_id=request_id,
                tenant_id=context.tenant_id,
                account_id=context.account_id,
                session_id=context.session_id,
                trace_id=context.trace_id,
                operation_type="model_output",
                operation_details={"content_preview": content[:200]},
                strategy=self._strategy,
            )

            self._pending_approvals[request_id] = approval_request

            if self._strategy == ApprovalStrategy.AUTO_APPROVE:
                approval_request.approve()
            elif self._strategy == ApprovalStrategy.AUTO_DENY:
                approval_request.deny()
                return MiddlewareResult(
                    success=False,
                    should_continue=False,
                    error="Model output denied by HITL policy",
                    metadata={"approval_request_id": request_id},
                )
            else:
                return MiddlewareResult(
                    success=False,
                    should_continue=False,
                    error="Approval required for model output",
                    metadata={"approval_request_id": request_id},
                )

        return MiddlewareResult(success=True, should_continue=True)

    def clear_pending_approvals(self):
        """Clear all pending approvals."""
        self._pending_approvals.clear()
        logger.info("pending_approvals_cleared")
