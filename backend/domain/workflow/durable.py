"""Durable workflow engine contracts (Temporal)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class WorkflowStatus(str, Enum):
    """Workflow execution status."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class RetryPolicy(str, Enum):
    """Retry policy for workflow steps."""

    NONE = "none"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    FIXED = "fixed"


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    """Durable workflow definition.

    Rule: Long-running operations must use durable workflows.
    """

    workflow_id: str
    workflow_name: str
    tenant_id: str
    account_id: str
    task_id: str | None
    timeout_seconds: int
    retry_policy: RetryPolicy
    max_retries: int

    @classmethod
    def create(
        cls,
        workflow_id: str,
        workflow_name: str,
        tenant_id: str,
        account_id: str,
        task_id: str | None = None,
        timeout_seconds: int = 300,
        retry_policy: RetryPolicy = RetryPolicy.EXPONENTIAL,
        max_retries: int = 3,
    ) -> WorkflowDefinition:
        """Factory method to create a WorkflowDefinition."""
        return cls(
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            tenant_id=tenant_id,
            account_id=account_id,
            task_id=task_id,
            timeout_seconds=timeout_seconds,
            retry_policy=retry_policy,
            max_retries=max_retries,
        )


@dataclass(frozen=True, slots=True)
class WorkflowExecution:
    """Workflow execution result."""

    workflow_id: str
    status: WorkflowStatus
    result: dict[str, object] | None
    error: str | None
    started_at: float
    completed_at: float | None

    def is_complete(self) -> bool:
        """Check if workflow is complete."""
        return self.status in {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.TIMED_OUT,
        }

    def is_successful(self) -> bool:
        """Check if workflow completed successfully."""
        return self.status == WorkflowStatus.COMPLETED
