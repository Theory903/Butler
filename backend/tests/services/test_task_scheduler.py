"""
Integration tests for Task Scheduler.

Tests task submission, scheduling, and priority handling.
"""

import pytest

from services.agent.task_scheduler import TaskPriority, TaskScheduler


class TestTaskScheduler:
    """Test suite for TaskScheduler."""

    @pytest.fixture
    def scheduler(self):
        """Create task scheduler instance."""
        return TaskScheduler()

    def test_submit_task(self, scheduler):
        """Test task submission."""
        task = scheduler.submit_task(
            task_id="task-1",
            tenant_id="tenant-123",
            agent_type="chat",
            payload={"message": "Hello"},
            priority=TaskPriority.NORMAL,
        )

        assert task.task_id == "task-1"
        assert task.tenant_id == "tenant-123"
        assert task.priority == TaskPriority.NORMAL

    def test_get_next_task(self, scheduler):
        """Test getting next task."""
        scheduler.submit_task(
            task_id="task-1",
            tenant_id="tenant-123",
            agent_type="chat",
            payload={"message": "Hello"},
            priority=TaskPriority.NORMAL,
        )

        task = scheduler.get_next_task(agent_type="chat", available_agents=["agent-1"])

        assert task is not None
        assert task.task_id == "task-1"
        assert task.scheduled_at is not None

    def test_priority_ordering(self, scheduler):
        """Test priority-based task ordering."""
        scheduler.submit_task(
            task_id="task-low",
            tenant_id="tenant-123",
            agent_type="chat",
            payload={"message": "Low"},
            priority=TaskPriority.LOW,
        )
        scheduler.submit_task(
            task_id="task-critical",
            tenant_id="tenant-123",
            agent_type="chat",
            payload={"message": "Critical"},
            priority=TaskPriority.CRITICAL,
        )
        scheduler.submit_task(
            task_id="task-high",
            tenant_id="tenant-123",
            agent_type="chat",
            payload={"message": "High"},
            priority=TaskPriority.HIGH,
        )

        # Critical task should be retrieved first
        task = scheduler.get_next_task(agent_type="chat", available_agents=["agent-1"])
        assert task.task_id == "task-critical"

    def test_cancel_task(self, scheduler):
        """Test task cancellation."""
        scheduler.submit_task(
            task_id="task-1",
            tenant_id="tenant-123",
            agent_type="chat",
            payload={"message": "Hello"},
            priority=TaskPriority.NORMAL,
        )

        cancelled = scheduler.cancel_task("task-1")

        assert cancelled is True
        assert scheduler.get_task_status("task-1") is None

    def test_get_queue_stats(self, scheduler):
        """Test getting queue statistics."""
        scheduler.submit_task(
            task_id="task-1",
            tenant_id="tenant-123",
            agent_type="chat",
            payload={"message": "Hello"},
            priority=TaskPriority.HIGH,
        )
        scheduler.submit_task(
            task_id="task-2",
            tenant_id="tenant-123",
            agent_type="chat",
            payload={"message": "World"},
            priority=TaskPriority.NORMAL,
        )

        stats = scheduler.get_queue_stats()

        assert stats["pending_tasks"]["high"] == 1
        assert stats["pending_tasks"]["normal"] == 1
        assert stats["pending_tasks"]["total"] == 2

    def test_clear_queue(self, scheduler):
        """Test clearing queue."""
        scheduler.submit_task(
            task_id="task-1",
            tenant_id="tenant-123",
            agent_type="chat",
            payload={"message": "Hello"},
            priority=TaskPriority.NORMAL,
        )

        count = scheduler.clear_queue(priority=TaskPriority.NORMAL)

        assert count == 1
        assert scheduler.get_task_status("task-1") is None
