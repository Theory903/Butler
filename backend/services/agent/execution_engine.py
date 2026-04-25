"""
Agent Execution Engine - Task Execution with Timeout Handling

Executes tasks on agents with timeout management and error handling.
Implements async task execution with cancellation support.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ExecutionStatus(StrEnum):
    """Task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Result of task execution."""

    task_id: str
    agent_id: str
    status: ExecutionStatus
    result: Any | None
    error: str | None
    started_at: datetime
    completed_at: datetime
    duration_ms: float


class AgentExecutionEngine:
    """
    Agent execution engine for task execution.

    Features:
    - Async task execution
    - Timeout management
    - Task cancellation
    - Error handling
    - Execution tracking
    """

    def __init__(self) -> None:
        """Initialize execution engine."""
        self._running_tasks: dict[str, datetime] = {}  # task_id -> start_time
        self._execution_results: dict[str, ExecutionResult] = {}

    async def execute_task(
        self,
        task_id: str,
        agent_id: str,
        handler: Callable[[], Awaitable[Any]],
        timeout_seconds: int = 300,
    ) -> ExecutionResult:
        """
        Execute a task on an agent with timeout.

        Args:
            task_id: Task identifier
            agent_id: Agent identifier
            handler: Async handler function
            timeout_seconds: Timeout in seconds

        Returns:
            Execution result
        """
        started_at = datetime.now(UTC)
        self._running_tasks[task_id] = started_at

        logger.info(
            "task_execution_started",
            task_id=task_id,
            agent_id=agent_id,
            timeout_seconds=timeout_seconds,
        )

        try:
            import asyncio

            # Execute with timeout
            result = await asyncio.wait_for(
                handler(),
                timeout=timeout_seconds,
            )

            completed_at = datetime.now(UTC)
            duration_ms = (completed_at - started_at).total_seconds() * 1000

            execution_result = ExecutionResult(
                task_id=task_id,
                agent_id=agent_id,
                status=ExecutionStatus.COMPLETED,
                result=result,
                error=None,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
            )

            logger.info(
                "task_execution_completed",
                task_id=task_id,
                agent_id=agent_id,
                duration_ms=duration_ms,
            )

        except TimeoutError:
            completed_at = datetime.now(UTC)
            duration_ms = (completed_at - started_at).total_seconds() * 1000

            execution_result = ExecutionResult(
                task_id=task_id,
                agent_id=agent_id,
                status=ExecutionStatus.TIMEOUT,
                result=None,
                error=f"Task timed out after {timeout_seconds} seconds",
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
            )

            logger.warning(
                "task_execution_timeout",
                task_id=task_id,
                agent_id=agent_id,
                timeout_seconds=timeout_seconds,
            )

        except Exception as e:
            completed_at = datetime.now(UTC)
            duration_ms = (completed_at - started_at).total_seconds() * 1000

            execution_result = ExecutionResult(
                task_id=task_id,
                agent_id=agent_id,
                status=ExecutionStatus.FAILED,
                result=None,
                error=str(e),
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
            )

            logger.error(
                "task_execution_failed",
                task_id=task_id,
                agent_id=agent_id,
                error=str(e),
            )

        finally:
            if task_id in self._running_tasks:
                del self._running_tasks[task_id]

            self._execution_results[task_id] = execution_result

        return execution_result

    async def execute_task_with_retry(
        self,
        task_id: str,
        agent_id: str,
        handler: Callable[[], Awaitable[Any]],
        max_retries: int = 3,
        timeout_seconds: int = 300,
    ) -> ExecutionResult:
        """
        Execute a task with retry logic.

        Args:
            task_id: Task identifier
            agent_id: Agent identifier
            handler: Async handler function
            max_retries: Maximum number of retries
            timeout_seconds: Timeout in seconds

        Returns:
            Execution result
        """
        last_error = None

        for attempt in range(max_retries + 1):
            if attempt > 0:
                logger.info(
                    "task_execution_retry",
                    task_id=task_id,
                    attempt=attempt,
                    max_retries=max_retries,
                )

            result = await self.execute_task(
                task_id=task_id,
                agent_id=agent_id,
                handler=handler,
                timeout_seconds=timeout_seconds,
            )

            if result.status == ExecutionStatus.COMPLETED:
                return result

            if result.status in [ExecutionStatus.TIMEOUT, ExecutionStatus.FAILED]:
                last_error = result.error

                # Don't retry on cancellation
                if result.status == ExecutionStatus.CANCELLED:
                    return result

                # Retry if we have attempts left
                if attempt < max_retries:
                    import asyncio

                    await asyncio.sleep(2**attempt)  # Exponential backoff
                    continue

            return result

        # All retries exhausted
        completed_at = datetime.now(UTC)
        started_at = self._execution_results.get(task_id, None)
        started_at = started_at.started_at if started_at else completed_at

        duration_ms = (completed_at - started_at).total_seconds() * 1000

        return ExecutionResult(
            task_id=task_id,
            agent_id=agent_id,
            status=ExecutionStatus.FAILED,
            result=None,
            error=f"All {max_retries} retries exhausted. Last error: {last_error}",
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
        )

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a running task.

        Args:
            task_id: Task identifier

        Returns:
            True if task was cancelled, False otherwise
        """
        if task_id not in self._running_tasks:
            return False

        # Mark as cancelled
        started_at = self._running_tasks[task_id]
        completed_at = datetime.now(UTC)
        duration_ms = (completed_at - started_at).total_seconds() * 1000

        execution_result = ExecutionResult(
            task_id=task_id,
            agent_id="unknown",
            status=ExecutionStatus.CANCELLED,
            result=None,
            error="Task cancelled by user",
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
        )

        del self._running_tasks[task_id]
        self._execution_results[task_id] = execution_result

        logger.info(
            "task_cancelled",
            task_id=task_id,
        )

        return True

    def get_execution_result(self, task_id: str) -> ExecutionResult | None:
        """
        Get execution result for a task.

        Args:
            task_id: Task identifier

        Returns:
            Execution result or None
        """
        return self._execution_results.get(task_id)

    def is_task_running(self, task_id: str) -> bool:
        """
        Check if a task is currently running.

        Args:
            task_id: Task identifier

        Returns:
            True if task is running
        """
        return task_id in self._running_tasks

    def get_running_tasks(self) -> list[str]:
        """Get list of currently running task IDs."""
        return list(self._running_tasks.keys())

    def get_execution_stats(self) -> dict[str, Any]:
        """
        Get execution statistics.

        Returns:
            Execution statistics
        """
        total_executions = len(self._execution_results)
        status_counts: dict[str, int] = {}

        for result in self._execution_results.values():
            status_counts[result.status] = status_counts.get(result.status, 0) + 1

        avg_duration = 0.0
        if self._execution_results:
            total_duration = sum(r.duration_ms for r in self._execution_results.values())
            avg_duration = total_duration / len(self._execution_results)

        return {
            "total_executions": total_executions,
            "currently_running": len(self._running_tasks),
            "status_breakdown": status_counts,
            "average_duration_ms": avg_duration,
        }

    def clear_old_results(self, max_age_hours: int = 24) -> int:
        """
        Clear old execution results.

        Args:
            max_age_hours: Maximum age of results to keep in hours

        Returns:
            Number of results cleared
        """
        cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)

        to_remove = [
            task_id
            for task_id, result in self._execution_results.items()
            if result.completed_at < cutoff
        ]

        for task_id in to_remove:
            del self._execution_results[task_id]

        logger.info(
            "execution_results_cleared",
            count=len(to_remove),
            max_age_hours=max_age_hours,
        )

        return len(to_remove)
