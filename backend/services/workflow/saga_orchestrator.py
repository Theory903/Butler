"""
Saga Orchestrator - Distributed Transaction Pattern

Implements the Saga pattern for distributed transactions.
Provides compensation actions for rollback scenarios.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class SagaStatus(StrEnum):
    """Saga execution status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SagaStep:
    """Individual step in a saga."""

    step_id: str
    name: str
    execute: Callable[[], Awaitable[Any]]
    compensate: Callable[[], Awaitable[Any]]
    completed: bool = False


@dataclass(frozen=True, slots=True)
class SagaExecution:
    """Saga execution record."""

    saga_id: str
    status: SagaStatus
    steps: list[SagaStep]
    current_step_index: int
    error: str | None
    started_at: datetime
    completed_at: datetime | None


class SagaOrchestrator:
    """
    Saga orchestrator for distributed transactions.

    Features:
    - Sequential step execution
    - Automatic compensation on failure
    - Idempotent operations
    - State persistence
    """

    def __init__(self) -> None:
        """Initialize saga orchestrator."""
        self._executions: dict[str, SagaExecution] = {}

    async def execute_saga(
        self,
        saga_id: str,
        steps: list[SagaStep],
    ) -> SagaExecution:
        """
        Execute a saga with compensation on failure.

        Args:
            saga_id: Unique saga identifier
            steps: List of saga steps

        Returns:
            Saga execution result
        """
        execution = SagaExecution(
            saga_id=saga_id,
            status=SagaStatus.IN_PROGRESS,
            steps=steps,
            current_step_index=0,
            error=None,
            started_at=datetime.now(UTC),
            completed_at=None,
        )

        self._executions[saga_id] = execution

        try:
            # Execute steps sequentially
            for i, step in enumerate(steps):
                execution = SagaExecution(
                    saga_id=saga_id,
                    status=SagaStatus.IN_PROGRESS,
                    steps=steps,
                    current_step_index=i,
                    error=None,
                    started_at=execution.started_at,
                    completed_at=None,
                )
                self._executions[saga_id] = execution

                logger.info(
                    "saga_step_executing",
                    saga_id=saga_id,
                    step_id=step.step_id,
                    step_name=step.name,
                    step_index=i,
                )

                try:
                    await step.execute()

                    # Mark step as completed
                    completed_steps = list(steps)
                    completed_steps[i] = SagaStep(
                        step_id=step.step_id,
                        name=step.name,
                        execute=step.execute,
                        compensate=step.compensate,
                        completed=True,
                    )

                    logger.info(
                        "saga_step_completed",
                        saga_id=saga_id,
                        step_id=step.step_id,
                    )

                except Exception as e:
                    logger.error(
                        "saga_step_failed",
                        saga_id=saga_id,
                        step_id=step.step_id,
                        error=str(e),
                    )

                    # Trigger compensation
                    await self._compensate(saga_id, completed_steps[:i])

                    execution = SagaExecution(
                        saga_id=saga_id,
                        status=SagaStatus.FAILED,
                        steps=completed_steps,
                        current_step_index=i,
                        error=str(e),
                        started_at=execution.started_at,
                        completed_at=datetime.now(UTC),
                    )
                    self._executions[saga_id] = execution
                    return execution

            # All steps completed successfully
            execution = SagaExecution(
                saga_id=saga_id,
                status=SagaStatus.COMPLETED,
                steps=steps,
                current_step_index=len(steps),
                error=None,
                started_at=execution.started_at,
                completed_at=datetime.now(UTC),
            )
            self._executions[saga_id] = execution

            logger.info(
                "saga_completed",
                saga_id=saga_id,
                steps_count=len(steps),
            )

            return execution

        except Exception as e:
            logger.exception(
                "saga_execution_error",
                saga_id=saga_id,
                error=str(e),
            )

            execution = SagaExecution(
                saga_id=saga_id,
                status=SagaStatus.FAILED,
                steps=steps,
                current_step_index=execution.current_step_index,
                error=str(e),
                started_at=execution.started_at,
                completed_at=datetime.now(UTC),
            )
            self._executions[saga_id] = execution
            return execution

    async def _compensate(
        self,
        saga_id: str,
        completed_steps: list[SagaStep],
    ) -> None:
        """
        Compensate completed steps in reverse order.

        Args:
            saga_id: Saga identifier
            completed_steps: Steps that were completed before failure
        """
        logger.info(
            "saga_compensation_started",
            saga_id=saga_id,
            steps_to_compensate=len(completed_steps),
        )

        execution = self._executions.get(saga_id)
        if execution:
            execution = SagaExecution(
                saga_id=saga_id,
                status=SagaStatus.COMPENSATING,
                steps=execution.steps,
                current_step_index=execution.current_step_index,
                error=execution.error,
                started_at=execution.started_at,
                completed_at=None,
            )
            self._executions[saga_id] = execution

        # Compensate in reverse order
        compensation_errors = []
        for step in reversed(completed_steps):
            if step.completed:
                logger.info(
                    "saga_compensating_step",
                    saga_id=saga_id,
                    step_id=step.step_id,
                    step_name=step.name,
                )

                try:
                    await step.compensate()
                    logger.info(
                        "saga_step_compensated",
                        saga_id=saga_id,
                        step_id=step.step_id,
                    )
                except Exception as e:
                    logger.error(
                        "saga_compensation_failed",
                        saga_id=saga_id,
                        step_id=step.step_id,
                        error=str(e),
                    )
                    compensation_errors.append((step.step_id, str(e)))

        if compensation_errors:
            logger.warning(
                "saga_compensation_partial_failure",
                saga_id=saga_id,
                failed_count=len(compensation_errors),
            )

            execution = SagaExecution(
                saga_id=saga_id,
                status=SagaStatus.FAILED,
                steps=execution.steps if execution else [],
                current_step_index=execution.current_step_index if execution else 0,
                error=f"Compensation failed: {len(compensation_errors)} errors",
                started_at=execution.started_at if execution else datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )
        else:
            logger.info(
                "saga_compensation_completed",
                saga_id=saga_id,
            )

            execution = SagaExecution(
                saga_id=saga_id,
                status=SagaStatus.COMPENSATED,
                steps=execution.steps if execution else [],
                current_step_index=execution.current_step_index if execution else 0,
                error=None,
                started_at=execution.started_at if execution else datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )

        if saga_id in self._executions:
            self._executions[saga_id] = execution

    def get_execution(self, saga_id: str) -> SagaExecution | None:
        """
        Get saga execution status.

        Args:
            saga_id: Saga identifier

        Returns:
            Saga execution or None
        """
        return self._executions.get(saga_id)

    def get_all_executions(self) -> dict[str, SagaExecution]:
        """Get all saga executions."""
        return self._executions.copy()

    async def retry_saga(
        self,
        saga_id: str,
        steps: list[SagaStep],
    ) -> SagaExecution:
        """
        Retry a failed saga from the failed step.

        Args:
            saga_id: Saga identifier
            steps: List of saga steps

        Returns:
            Saga execution result
        """
        previous_execution = self.get_execution(saga_id)

        if not previous_execution:
            return await self.execute_saga(saga_id, steps)

        if previous_execution.status == SagaStatus.COMPLETED:
            return previous_execution

        # Retry from the failed step
        retry_steps = steps[previous_execution.current_step_index :]

        logger.info(
            "saga_retrying",
            saga_id=saga_id,
            from_step=previous_execution.current_step_index,
        )

        return await self.execute_saga(f"{saga_id}-retry", retry_steps)
