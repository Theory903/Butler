"""OperationRouter + AdmissionController for operation routing and validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OperationType(str, Enum):
    """Operation types for routing."""

    CHAT = "chat"
    TOOL_CALL = "tool_call"
    MEMORY_WRITE = "memory_write"
    MEMORY_READ = "memory_read"
    WORKFLOW_EXECUTION = "workflow_execution"
    STREAMING = "streaming"


class AdmissionDecision(str, Enum):
    """Admission decision."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    RATE_LIMITED = "rate_limited"


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    """Result of admission control check."""

    decision: AdmissionDecision
    reason: str
    approval_id: str | None = None
    retry_after_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class OperationRequest:
    """Operation request for routing."""

    operation_type: OperationType
    tenant_id: str
    account_id: str
    user_id: str | None
    tool_name: str | None
    risk_tier: str | None
    estimated_cost: float | None

    def requires_admission_check(self) -> bool:
        """Check if operation requires admission control."""
        return self.operation_type in {
            OperationType.TOOL_CALL,
            OperationType.WORKFLOW_EXECUTION,
        }

    def is_high_risk(self) -> bool:
        """Check if operation is high risk."""
        return self.risk_tier in {"L3", "L4"} if self.risk_tier else False


class AdmissionController:
    """Admission controller for operation validation.

    Rule: All high-risk operations must pass admission control.
    """

    def __init__(self, enable_rate_limiting: bool = True) -> None:
        self.enable_rate_limiting = enable_rate_limiting

    def check_admission(self, request: OperationRequest) -> AdmissionResult:
        """Check if operation is allowed to proceed."""
        if not request.requires_admission_check():
            return AdmissionResult(
                decision=AdmissionDecision.ALLOW,
                reason="Operation does not require admission check",
            )

        if request.is_high_risk():
            return AdmissionResult(
                decision=AdmissionDecision.REQUIRE_APPROVAL,
                reason="High-risk operation requires approval",
                approval_id=f"apr_{request.tenant_id}_{request.account_id}",
            )

        return AdmissionResult(
            decision=AdmissionDecision.ALLOW,
            reason="Operation allowed",
        )


class OperationRouter:
    """Router for operation routing based on type and risk.

    Rule: Route operations to appropriate execution path.
    """

    def __init__(self, admission_controller: AdmissionController) -> None:
        if admission_controller is None:
            raise TypeError("admission_controller cannot be None")
        self.admission_controller = admission_controller

    def route(self, request: OperationRequest) -> tuple[str, AdmissionResult]:
        """Route operation to execution path and check admission."""
        admission = self.admission_controller.check_admission(request)

        if admission.decision != AdmissionDecision.ALLOW:
            return "blocked", admission

        if request.operation_type == OperationType.TOOL_CALL:
            return "tool_executor", admission
        elif request.operation_type == OperationType.WORKFLOW_EXECUTION:
            return "workflow_engine", admission
        elif request.operation_type == OperationType.MEMORY_WRITE:
            return "memory_writer", admission
        elif request.operation_type == OperationType.MEMORY_READ:
            return "memory_reader", admission
        else:
            return "chat_handler", admission
