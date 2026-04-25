"""
Integration tests for Agent Execution Engine.

Tests task execution with timeout handling and retry logic.
"""

import pytest

from services.agent.execution_engine import AgentExecutionEngine, ExecutionStatus


class TestAgentExecutionEngine:
    """Test suite for AgentExecutionEngine."""

    @pytest.fixture
    def execution_engine(self):
        """Create execution engine instance."""
        return AgentExecutionEngine()

    @pytest.mark.asyncio
    async def test_execute_task_success(self, execution_engine):
        """Test successful task execution."""

        async def handler():
            return "success"

        result = await execution_engine.execute_task(
            task_id="task-1",
            agent_id="agent-1",
            handler=handler,
            timeout_seconds=10,
        )

        assert result.status == ExecutionStatus.COMPLETED
        assert result.result == "success"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_execute_task_timeout(self, execution_engine):
        """Test task execution timeout."""
        import asyncio

        async def handler():
            await asyncio.sleep(20)
            return "success"

        result = await execution_engine.execute_task(
            task_id="task-1",
            agent_id="agent-1",
            handler=handler,
            timeout_seconds=1,
        )

        assert result.status == ExecutionStatus.TIMEOUT
        assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_task_failure(self, execution_engine):
        """Test task execution failure."""

        async def handler():
            raise ValueError("Test error")

        result = await execution_engine.execute_task(
            task_id="task-1",
            agent_id="agent-1",
            handler=handler,
            timeout_seconds=10,
        )

        assert result.status == ExecutionStatus.FAILED
        assert "Test error" in result.error

    @pytest.mark.asyncio
    async def test_execute_task_with_retry(self, execution_engine):
        """Test task execution with retry."""
        attempt_count = [0]

        async def handler():
            attempt_count[0] += 1
            if attempt_count[0] < 3:
                raise ValueError("Retry me")
            return "success"

        result = await execution_engine.execute_task_with_retry(
            task_id="task-1",
            agent_id="agent-1",
            handler=handler,
            max_retries=3,
            timeout_seconds=10,
        )

        assert result.status == ExecutionStatus.COMPLETED
        assert result.result == "success"
        assert attempt_count[0] == 3

    @pytest.mark.asyncio
    async def test_cancel_task(self, execution_engine):
        """Test task cancellation."""
        import asyncio

        async def handler():
            await asyncio.sleep(20)
            return "success"

        # Start task in background
        asyncio.create_task(
            execution_engine.execute_task(
                task_id="task-1",
                agent_id="agent-1",
                handler=handler,
                timeout_seconds=30,
            )
        )

        # Give it a moment to start
        await asyncio.sleep(0.1)

        # Cancel the task
        cancelled = await execution_engine.cancel_task("task-1")

        assert cancelled is True
        assert execution_engine.is_task_running("task-1") is False

    def test_get_execution_result(self, execution_engine):
        """Test getting execution result."""
        # This test requires a completed task, which is tested in other tests
        result = execution_engine.get_execution_result("task-1")
        assert result is None

    def test_get_running_tasks(self, execution_engine):
        """Test getting running tasks."""
        running = execution_engine.get_running_tasks()
        assert running == []

    def test_get_execution_stats(self, execution_engine):
        """Test getting execution statistics."""
        stats = execution_engine.get_execution_stats()

        assert "total_executions" in stats
        assert "currently_running" in stats
        assert "status_breakdown" in stats
