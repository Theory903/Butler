from __future__ import annotations

from core.errors import Problem


class OrchestratorErrors:
    """Problem catalog for orchestrator-facing API/domain boundary errors."""

    WORKFLOW_NOT_FOUND = Problem(
        type="https://docs.butler.lasmoid.ai/problems/workflow-not-found",
        title="Workflow Not Found",
        status=404,
    )

    TASK_NOT_FOUND = Problem(
        type="https://docs.butler.lasmoid.ai/problems/task-not-found",
        title="Task Not Found",
        status=404,
    )

    APPROVAL_NOT_FOUND = Problem(
        type="https://docs.butler.lasmoid.ai/problems/approval-not-found",
        title="Approval Request Not Found",
        status=404,
    )

    APPROVAL_EXPIRED = Problem(
        type="https://docs.butler.lasmoid.ai/problems/approval-expired",
        title="Approval Request Expired",
        status=409,
    )

    @staticmethod
    def invalid_transition(from_status: str, to_status: str) -> Problem:
        """Return a conflict problem for an invalid task state transition."""
        return Problem(
            type="https://docs.butler.lasmoid.ai/problems/invalid-task-transition",
            title="Invalid Task Transition",
            status=409,
            detail=f"Cannot transition from '{from_status}' to '{to_status}'.",
        )

    @staticmethod
    def invalid_approval_decision(decision: str) -> Problem:
        """Return a validation problem for unsupported approval decisions."""
        return Problem(
            type="https://docs.butler.lasmoid.ai/problems/invalid-approval-decision",
            title="Invalid Approval Decision",
            status=422,
            detail=f"Unsupported approval decision: {decision!r}.",
        )


class ApprovalRequiredError(Exception):
    """Domain-level suspension signal for actions requiring human approval.

    This is intentionally NOT an HTTP Problem. It is used inside orchestration
    and executor flows to suspend execution and create an approval request.
    The API layer may later map that state to an appropriate response/event.
    """

    def __init__(
        self,
        approval_type: str,
        description: str,
        *,
        tool_name: str | None = None,
        risk_tier: str = "L2",
    ) -> None:
        self.approval_type = approval_type
        self.description = description
        self.tool_name = tool_name
        self.risk_tier = risk_tier
        super().__init__(description)
