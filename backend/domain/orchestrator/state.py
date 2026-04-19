from datetime import datetime, UTC
from typing import Optional
from domain.orchestrator.models import Task, TaskTransition
from domain.orchestrator.exceptions import OrchestratorErrors

class TaskStateMachine:
    """Strict state transitions — explicit is better than implicit."""

    TRANSITIONS = {
        "pending":              ["planning", "executing", "failed"],
        "planning":             ["executing", "failed"],
        "executing":            ["completed", "awaiting_approval", "failed"],
        "awaiting_approval":    ["executing", "failed", "compensating"],
        "completed":            [],  # Terminal
        "failed":               ["compensating", "pending"],  # Retry allowed
        "compensating":         ["compensated", "compensation_failed"],
        "compensated":          [],  # Terminal
        "compensation_failed":  [],  # Terminal — needs manual intervention
    }

    @classmethod
    def can_transition(cls, from_status: str, to_status: str) -> bool:
        allowed = cls.TRANSITIONS.get(from_status, [])
        return to_status in allowed

    @classmethod
    def transition(cls, task: Task, to_status: str, trigger: str, metadata: Optional[dict] = None) -> TaskTransition:
        """Execute a state transition and create audit trail."""
        if not cls.can_transition(task.status, to_status):
            raise OrchestratorErrors.invalid_transition(task.status, to_status)

        transition = TaskTransition(
            task_id=task.id,
            from_status=task.status,
            to_status=to_status,
            trigger=trigger,
            metadata_col=metadata or {},
        )

        task.status = to_status
        if to_status == "executing" and not task.started_at:
            task.started_at = datetime.now(UTC)
        if to_status in ("completed", "failed", "compensated", "compensation_failed"):
            task.completed_at = datetime.now(UTC)

        return transition
