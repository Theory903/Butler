"""
Task Scheduler - Task Scheduling and Prioritization

Schedules tasks to available agents with priority-based queuing.
Implements fair scheduling and tenant-aware task distribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class TaskPriority(StrEnum):
    """Task priority levels."""

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class Task:
    """Task to be scheduled."""

    task_id: str
    tenant_id: str
    agent_type: str
    priority: TaskPriority
    payload: dict[str, Any]
    created_at: datetime
    scheduled_at: datetime | None
    timeout_seconds: int = 300


@dataclass(frozen=True, slots=True)
class ScheduledTask:
    """Task with scheduling metadata."""

    task: Task
    priority_score: int
    queue_index: int


class TaskScheduler:
    """
    Task scheduler for agent execution.

    Features:
    - Priority-based task queuing
    - Tenant-aware fair scheduling
    - Agent type matching
    - Timeout management
    """

    def __init__(self) -> None:
        """Initialize task scheduler."""
        self._queues: dict[str, list[ScheduledTask]] = {
            "critical": [],
            "high": [],
            "normal": [],
            "low": [],
        }
        self._queue_index = 0
        self._scheduled_tasks: dict[str, ScheduledTask] = {}  # task_id -> ScheduledTask
        self._tenant_task_counts: dict[str, int] = {}  # tenant_id -> count

    def _priority_to_score(self, priority: TaskPriority) -> int:
        """Convert priority to numeric score for comparison."""
        scores = {
            TaskPriority.CRITICAL: 4,
            TaskPriority.HIGH: 3,
            TaskPriority.NORMAL: 2,
            TaskPriority.LOW: 1,
        }
        return scores.get(priority, 2)

    def submit_task(
        self,
        task_id: str,
        tenant_id: str,
        agent_type: str,
        payload: dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        timeout_seconds: int = 300,
    ) -> Task:
        """
        Submit a task for scheduling.

        Args:
            task_id: Unique task identifier
            tenant_id: Tenant UUID
            agent_type: Required agent type
            payload: Task payload
            priority: Task priority
            timeout_seconds: Task timeout

        Returns:
            Submitted task
        """
        task = Task(
            task_id=task_id,
            tenant_id=tenant_id,
            agent_type=agent_type,
            priority=priority,
            payload=payload,
            created_at=datetime.now(UTC),
            scheduled_at=None,
            timeout_seconds=timeout_seconds,
        )

        scheduled_task = ScheduledTask(
            task=task,
            priority_score=self._priority_to_score(priority),
            queue_index=self._queue_index,
        )

        self._queue_index += 1
        self._scheduled_tasks[task_id] = scheduled_task
        self._queues[priority].append(scheduled_task)

        # Update tenant task count
        self._tenant_task_counts[tenant_id] = self._tenant_task_counts.get(tenant_id, 0) + 1

        logger.info(
            "task_submitted",
            task_id=task_id,
            tenant_id=tenant_id,
            agent_type=agent_type,
            priority=priority,
        )

        return task

    def get_next_task(
        self,
        agent_type: str,
        available_agents: list[str],
    ) -> Task | None:
        """
        Get the next task to execute.

        Args:
            agent_type: Type of agent requesting task
            available_agents: List of available agent IDs

        Returns:
            Next task or None if no tasks available
        """
        if not available_agents:
            return None

        # Check queues in priority order
        for priority in [
            TaskPriority.CRITICAL,
            TaskPriority.HIGH,
            TaskPriority.NORMAL,
            TaskPriority.LOW,
        ]:
            queue = self._queues[priority]

            if not queue:
                continue

            # Find task matching agent type
            for i, scheduled_task in enumerate(queue):
                task = scheduled_task.task

                if task.agent_type == agent_type:
                    # Remove from queue
                    queue.pop(i)
                    del self._scheduled_tasks[task.task_id]

                    # Update tenant task count
                    self._tenant_task_counts[task.tenant_id] = max(
                        0, self._tenant_task_counts.get(task.tenant_id, 0) - 1
                    )

                    # Mark as scheduled
                    scheduled_task = ScheduledTask(
                        task=Task(
                            task_id=task.task_id,
                            tenant_id=task.tenant_id,
                            agent_type=task.agent_type,
                            priority=task.priority,
                            payload=task.payload,
                            created_at=task.created_at,
                            scheduled_at=datetime.now(UTC),
                            timeout_seconds=task.timeout_seconds,
                        ),
                        priority_score=scheduled_task.priority_score,
                        queue_index=scheduled_task.queue_index,
                    )

                    logger.info(
                        "task_scheduled",
                        task_id=task.task_id,
                        agent_type=agent_type,
                        priority=priority,
                    )

                    return scheduled_task.task

        return None

    def get_next_task_fair(
        self,
        agent_type: str,
        available_agents: list[str],
    ) -> Task | None:
        """
        Get the next task with tenant-aware fair scheduling.

        Args:
            agent_type: Type of agent requesting task
            available_agents: List of available agent IDs

        Returns:
            Next task or None if no tasks available
        """
        if not available_agents:
            return None

        # Collect all tasks for this agent type
        all_tasks = []

        for priority in [
            TaskPriority.CRITICAL,
            TaskPriority.HIGH,
            TaskPriority.NORMAL,
            TaskPriority.LOW,
        ]:
            queue = self._queues[priority]

            for scheduled_task in queue:
                task = scheduled_task.task

                if task.agent_type == agent_type:
                    # Calculate fair score based on tenant task count
                    tenant_count = self._tenant_task_counts.get(task.tenant_id, 0)
                    fair_score = scheduled_task.priority_score * 1000 - tenant_count

                    all_tasks.append((fair_score, scheduled_task))

        if not all_tasks:
            return None

        # Sort by fair score (higher is better)
        all_tasks.sort(key=lambda x: x[0], reverse=True)

        # Get best task
        _, scheduled_task = all_tasks[0]
        task = scheduled_task.task

        # Remove from queue
        priority = task.priority
        queue = self._queues[priority]
        for i, st in enumerate(queue):
            if st.task.task_id == task.task_id:
                queue.pop(i)
                break

        del self._scheduled_tasks[task.task_id]

        # Update tenant task count
        self._tenant_task_counts[task.tenant_id] = max(
            0, self._tenant_task_counts.get(task.tenant_id, 0) - 1
        )

        # Mark as scheduled
        scheduled_task = ScheduledTask(
            task=Task(
                task_id=task.task_id,
                tenant_id=task.tenant_id,
                agent_type=task.agent_type,
                priority=task.priority,
                payload=task.payload,
                created_at=task.created_at,
                scheduled_at=datetime.now(UTC),
                timeout_seconds=task.timeout_seconds,
            ),
            priority_score=scheduled_task.priority_score,
            queue_index=scheduled_task.queue_index,
        )

        logger.info(
            "task_scheduled_fair",
            task_id=task.task_id,
            agent_type=agent_type,
            priority=priority,
        )

        return scheduled_task.task

    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a pending task.

        Args:
            task_id: Task identifier

        Returns:
            True if task was cancelled, False if not found
        """
        if task_id not in self._scheduled_tasks:
            return False

        scheduled_task = self._scheduled_tasks[task_id]
        task = scheduled_task.task

        # Remove from queue
        queue = self._queues[task.priority]
        for i, st in enumerate(queue):
            if st.task.task_id == task_id:
                queue.pop(i)
                break

        del self._scheduled_tasks[task_id]

        # Update tenant task count
        self._tenant_task_counts[task.tenant_id] = max(
            0, self._tenant_task_counts.get(task.tenant_id, 0) - 1
        )

        logger.info(
            "task_cancelled",
            task_id=task_id,
        )

        return True

    def get_task_status(self, task_id: str) -> str | None:
        """
        Get task status (pending or scheduled).

        Args:
            task_id: Task identifier

        Returns:
            Task status or None
        """
        if task_id in self._scheduled_tasks:
            return "pending"
        return None

    def get_queue_stats(self) -> dict[str, Any]:
        """
        Get queue statistics.

        Returns:
            Queue statistics
        """
        return {
            "pending_tasks": {
                "critical": len(self._queues["critical"]),
                "high": len(self._queues["high"]),
                "normal": len(self._queues["normal"]),
                "low": len(self._queues["low"]),
                "total": sum(len(q) for q in self._queues.values()),
            },
            "tenant_task_counts": self._tenant_task_counts.copy(),
        }

    def get_tenant_tasks(self, tenant_id: str) -> list[Task]:
        """
        Get all pending tasks for a tenant.

        Args:
            tenant_id: Tenant UUID

        Returns:
            List of pending tasks
        """
        tasks = []

        for queue in self._queues.values():
            for scheduled_task in queue:
                if scheduled_task.task.tenant_id == tenant_id:
                    tasks.append(scheduled_task.task)

        return tasks

    def clear_queue(self, priority: TaskPriority | None = None) -> int:
        """
        Clear tasks from queue.

        Args:
            priority: Specific priority to clear, or None for all

        Returns:
            Number of tasks cleared
        """
        count = 0

        if priority:
            queue = self._queues[priority]
            count = len(queue)

            for scheduled_task in queue:
                task_id = scheduled_task.task.task_id
                tenant_id = scheduled_task.task.tenant_id
                del self._scheduled_tasks[task_id]
                self._tenant_task_counts[tenant_id] = max(
                    0, self._tenant_task_counts.get(tenant_id, 0) - 1
                )

            self._queues[priority] = []
        else:
            for queue in self._queues.values():
                count += len(queue)

                for scheduled_task in queue:
                    task_id = scheduled_task.task.task_id
                    tenant_id = scheduled_task.task.tenant_id
                    del self._scheduled_tasks[task_id]
                    self._tenant_task_counts[tenant_id] = max(
                        0, self._tenant_task_counts.get(tenant_id, 0) - 1
                    )

                queue.clear()

        logger.info(
            "queue_cleared",
            priority=priority,
            count=count,
        )

        return count
