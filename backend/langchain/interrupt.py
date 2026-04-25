"""
LangGraph Interrupt Handler - Butler approval workflow integration.

This module provides enhanced human-in-the-loop approval interrupts
for LangGraph workflows, with UI hooks for approval requests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog

from services.tools.risk import RiskTier

logger = structlog.get_logger(__name__)


class ButlerInterruptHandler:
    """Handler for LangGraph interrupts with Butler approval integration.

    This handler:
    - Wraps LangGraph interrupt() for TIER_3/4 tool approvals
    - Provides UI metadata for approval requests
    - Supports realtime approval streaming
    - Manages approval timeout (30 minutes)
    """

    APPROVAL_TIMEOUT_MINUTES = 30

    def __init__(self):
        self._pending_approvals: dict[str, dict[str, Any]] = {}

    async def request_approval(
        self,
        tool_name: str,
        args: dict[str, Any],
        risk_tier: RiskTier,
        description: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Request human approval for a high-risk tool execution.

        Args:
            tool_name: Name of the tool requiring approval
            args: Arguments passed to the tool
            risk_tier: Risk tier classification
            description: Optional description of the operation
            session_id: Session identifier for tracking

        Returns:
            Approval metadata including approval_id, timeout timestamp, and UI hooks

        Raises:
            PermissionError: If LangGraph interrupt is unavailable
        """
        approval_id = str(uuid4())
        timeout_at = datetime.now(UTC).replace(
            minute=datetime.now(UTC).minute + self.APPROVAL_TIMEOUT_MINUTES
        )

        approval_metadata = {
            "approval_id": approval_id,
            "tool_name": tool_name,
            "risk_tier": risk_tier.value,
            "description": description or f"Tool execution: {tool_name}",
            "args": args,
            "session_id": session_id,
            "requested_at": datetime.now(UTC).isoformat(),
            "timeout_at": timeout_at.isoformat(),
            "status": "pending",
            # UI hooks for approval interface
            "ui_hooks": {
                "approve_url": f"/api/v1/approvals/{approval_id}/approve",
                "deny_url": f"/api/v1/approvals/{approval_id}/deny",
                "stream_url": f"/api/v1/approvals/{approval_id}/stream",
            },
        }

        self._pending_approvals[approval_id] = approval_metadata

        logger.info(
            "approval_requested",
            approval_id=approval_id,
            tool_name=tool_name,
            risk_tier=risk_tier.value,
            session_id=session_id,
        )

        # Trigger LangGraph interrupt
        try:
            from langgraph.types import interrupt

            interrupt(approval_metadata)
        except ImportError:
            # Fallback when LangGraph unavailable
            raise PermissionError(
                f"Tool {tool_name} requires approval (RiskTier {risk_tier.value}) "
                f"but LangGraph interrupt is unavailable"
            )

        return approval_metadata

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        """Get approval metadata by ID."""
        return self._pending_approvals.get(approval_id)

    def approve(self, approval_id: str, approved_by: str | None = None) -> dict[str, Any]:
        """Approve a pending approval request.

        Args:
            approval_id: Approval request identifier
            approved_by: Identifier of the user who approved

        Returns:
            Updated approval metadata

        Raises:
            ValueError: If approval not found or already processed
        """
        if approval_id not in self._pending_approvals:
            raise ValueError(f"Approval {approval_id} not found")

        approval = self._pending_approvals[approval_id]
        if approval["status"] != "pending":
            raise ValueError(f"Approval {approval_id} already {approval['status']}")

        approval["status"] = "approved"
        approval["approved_by"] = approved_by
        approval["approved_at"] = datetime.now(UTC).isoformat()

        logger.info(
            "approval_granted",
            approval_id=approval_id,
            tool_name=approval["tool_name"],
            approved_by=approved_by,
        )

        return approval

    def deny(
        self, approval_id: str, denied_by: str | None = None, reason: str | None = None
    ) -> dict[str, Any]:
        """Deny a pending approval request.

        Args:
            approval_id: Approval request identifier
            denied_by: Identifier of the user who denied
            reason: Optional reason for denial

        Returns:
            Updated approval metadata

        Raises:
            ValueError: If approval not found or already processed
        """
        if approval_id not in self._pending_approvals:
            raise ValueError(f"Approval {approval_id} not found")

        approval = self._pending_approvals[approval_id]
        if approval["status"] != "pending":
            raise ValueError(f"Approval {approval_id} already {approval['status']}")

        approval["status"] = "denied"
        approval["denied_by"] = denied_by
        approval["denied_reason"] = reason
        approval["denied_at"] = datetime.now(UTC).isoformat()

        logger.info(
            "approval_denied",
            approval_id=approval_id,
            tool_name=approval["tool_name"],
            denied_by=denied_by,
            reason=reason,
        )

        return approval

    def cleanup_expired(self) -> int:
        """Clean up expired approval requests.

        Returns:
            Number of expired approvals removed
        """
        now = datetime.now(UTC)
        expired_ids = []

        for approval_id, approval in self._pending_approvals.items():
            if approval["status"] == "pending":
                timeout_at = datetime.fromisoformat(approval["timeout_at"])
                if now > timeout_at:
                    expired_ids.append(approval_id)

        for approval_id in expired_ids:
            approval = self._pending_approvals[approval_id]
            approval["status"] = "expired"
            approval["expired_at"] = datetime.now(UTC).isoformat()
            del self._pending_approvals[approval_id]

            logger.info(
                "approval_expired",
                approval_id=approval_id,
                tool_name=approval["tool_name"],
            )

        return len(expired_ids)

    def list_pending(self, session_id: str | None = None) -> list[dict[str, Any]]:
        """List pending approvals, optionally filtered by session.

        Args:
            session_id: Optional session filter

        Returns:
            List of pending approval metadata
        """
        pending = [
            approval
            for approval in self._pending_approvals.values()
            if approval["status"] == "pending"
        ]

        if session_id:
            pending = [a for a in pending if a.get("session_id") == session_id]

        return pending

    async def resume_workflow(
        self,
        thread_id: str,
        approval_id: str,
        resume_value: dict[str, Any],
    ) -> dict[str, Any]:
        """Resume a workflow after approval using LangGraph Command(resume=).

        Args:
            thread_id: LangGraph thread identifier
            approval_id: Approval request identifier
            resume_value: Value to pass back to the interrupted node

        Returns:
            Resume metadata

        Raises:
            ValueError: If approval not found or not approved
        """
        approval = self.get_approval(approval_id)
        if not approval:
            raise ValueError(f"Approval {approval_id} not found")

        if approval["status"] != "approved":
            raise ValueError(f"Approval {approval_id} is {approval['status']}, cannot resume")

        try:
            from langgraph.types import Command

            resume_command = Command(resume=resume_value)

            logger.info(
                "workflow_resumed",
                approval_id=approval_id,
                thread_id=thread_id,
                tool_name=approval["tool_name"],
            )

            return {
                "approval_id": approval_id,
                "thread_id": thread_id,
                "status": "resumed",
                "resumed_at": datetime.now(UTC).isoformat(),
                "resume_command": resume_command,
            }
        except ImportError:
            raise RuntimeError("LangGraph Command not available for resume")


# Singleton instance
_interrupt_handler: ButlerInterruptHandler | None = None


def get_interrupt_handler() -> ButlerInterruptHandler:
    """Get the singleton interrupt handler instance."""
    global _interrupt_handler
    if _interrupt_handler is None:
        _interrupt_handler = ButlerInterruptHandler()
    return _interrupt_handler
