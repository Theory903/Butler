from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

from domain.orchestrator.exceptions import OrchestratorErrors
from domain.orchestrator.models import Task, TaskTransition

UTC = UTC


class TaskStateMachine:
    """Authoritative task state transition policy for Butler orchestration.

    This state machine owns:
    - validation of allowed task status transitions
    - creation of task transition audit records
    - task lifecycle timestamps tied to state movement

    It does not persist transitions. Persistence is handled by the caller.
    """

    _TRANSITIONS: Mapping[str, frozenset[str]] = MappingProxyType(
        {
            "pending": frozenset({"planning", "executing", "failed"}),
            "planning": frozenset({"executing", "failed"}),
            "executing": frozenset({"completed", "awaiting_approval", "failed"}),
            "awaiting_approval": frozenset({"executing", "failed", "compensating"}),
            "completed": frozenset(),
            "failed": frozenset({"compensating", "pending"}),
            "compensating": frozenset({"compensated", "compensation_failed"}),
            "compensated": frozenset(),
            "compensation_failed": frozenset(),
        }
    )

    _COMPLETION_STATES = frozenset({"completed", "failed", "compensated", "compensation_failed"})

    @classmethod
    def allowed_transitions(cls, from_status: str) -> frozenset[str]:
        """Return the allowed destination statuses for the given source status."""
        return cls._TRANSITIONS.get(from_status, frozenset())

    @classmethod
    def can_transition(cls, from_status: str, to_status: str) -> bool:
        """Return whether a transition is valid."""
        return to_status in cls.allowed_transitions(from_status)

    @classmethod
    def is_terminal(cls, status: str) -> bool:
        """Return whether the given status is terminal."""
        return len(cls.allowed_transitions(status)) == 0

    @classmethod
    def transition(
        cls,
        task: Task,
        to_status: str,
        trigger: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> TaskTransition:
        """Apply a valid transition to a task and return its audit record.

        This method mutates the provided task object in memory and returns the
        corresponding TaskTransition ORM entity. The caller is responsible for
        persisting both objects within the active transaction.
        """
        from_status = task.status

        if not cls.can_transition(from_status, to_status):
            raise OrchestratorErrors.invalid_transition(from_status, to_status)

        transition = TaskTransition(
            task_id=task.id,
            from_status=from_status,
            to_status=to_status,
            trigger=trigger,
            metadata_col=dict(metadata) if metadata is not None else {},
        )

        task.status = to_status

        if to_status == "executing" and task.started_at is None:
            task.started_at = datetime.now(UTC)

        if to_status in cls._COMPLETION_STATES:
            task.completed_at = datetime.now(UTC)

        return transition
