"""Comprehensive chaos and load tests.

Tests cover:
- High load scenarios
- Concurrent operations
- Error conditions under load
- Resource exhaustion simulation
- Timeout handling
- Race conditions
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.tenant_aware_logger import TenantAwareLogger
from domain.orchestrator.runtime_kernel import (
    ExecutionResult,
    ExecutionStrategy,
    RuntimeKernel,
    RuntimeKernelConfigurationError,
    StopReason,
    TokenUsage,
)
from domain.tenant.namespace import TenantNamespace
from domain.workflow.durable import (
    RetryPolicy,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowStatus,
)


class TestConcurrentOperations:
    """Test concurrent operations."""

    def test_concurrent_namespace_creation(self):
        """Test concurrent TenantNamespace creation."""
        namespaces = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(
                    TenantNamespace,
                    f"tenant_{i}",
                    f"account_{i}",
                )
                for i in range(100)
            ]
            namespaces = [f.result() for f in futures]

        assert len(namespaces) == 100
        assert all(isinstance(ns, TenantNamespace) for ns in namespaces)

    def test_concurrent_hash_operations(self):
        """Test concurrent hash operations."""
        from core.tenant_aware_logger import hash_tenant_id

        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(hash_tenant_id, f"tenant_{i}") for i in range(1000)
            ]
            results = [f.result() for f in futures]

        assert len(results) == 1000
        assert all(isinstance(r, str) and len(r) == 8 for r in results)

    def test_concurrent_workflow_creation(self):
        """Test concurrent workflow definition creation."""
        workflows = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(
                    WorkflowDefinition.create,
                    f"wf_{i}",
                    f"workflow_{i}",
                    f"tenant_{i}",
                    f"account_{i}",
                )
                for i in range(100)
            ]
            workflows = [f.result() for f in futures]

        assert len(workflows) == 100
        assert all(isinstance(wf, WorkflowDefinition) for wf in workflows)

    def test_concurrent_execution_result_creation(self):
        """Test concurrent execution result creation."""
        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(
                    ExecutionResult,
                    f"content_{i}",
                    [],
                    TokenUsage(input_tokens=i, output_tokens=i * 2),
                    i * 10,
                    i,
                    StopReason.END_TURN,
                )
                for i in range(100)
            ]
            results = [f.result() for f in futures]

        assert len(results) == 100
        assert all(isinstance(r, ExecutionResult) for r in results)


class TestHighLoadScenarios:
    """Test high load scenarios."""

    def test_large_namespace_prefix_generation(self):
        """Test generating many namespace prefixes."""
        prefixes = []
        for i in range(10000):
            ns = TenantNamespace(f"tenant_{i}", f"account_{i}")
            prefixes.append(ns.to_redis_prefix())

        assert len(prefixes) == 10000
        assert all("butler:tenant:" in p for p in prefixes)

    def test_large_workflow_batch(self):
        """Test creating large batch of workflow executions."""
        executions = []
        for i in range(1000):
            execution = WorkflowExecution(
                workflow_id=f"wf_{i}",
                status=WorkflowStatus.COMPLETED,
                result={"index": i},
                error=None,
                started_at=float(i),
                completed_at=float(i + 1),
            )
            executions.append(execution)

        assert len(executions) == 1000
        assert all(e.is_complete() for e in executions)

    def test_large_token_usage_accounting(self):
        """Test large token usage accounting."""
        total_input = 0
        total_output = 0
        for i in range(10000):
            usage = TokenUsage(
                input_tokens=i,
                output_tokens=i * 2,
                cache_read_tokens=i // 2,
                estimated_cost_usd=i * 0.0001,
            )
            total_input += usage.input_tokens
            total_output += usage.output_tokens

        assert total_input == sum(range(10000))
        assert total_output == sum(range(10000)) * 2


class TestResourceExhaustion:
    """Test resource exhaustion scenarios."""

    def test_very_long_content_handling(self):
        """Test handling very long content in execution result."""
        very_long_content = "x" * 10000000  # 10MB
        result = ExecutionResult(content=very_long_content)

        assert len(result.content) == 10000000

    def test_many_actions_in_result(self):
        """Test result with many actions."""
        actions = [{"type": "action", "index": i} for i in range(10000)]
        result = ExecutionResult(content="Response", actions=actions)

        assert len(result.actions) == 10000

    def test_large_context_in_logger(self):
        """Test logger with very large context."""
        logger = TenantAwareLogger("test")
        large_context = {"key_" + str(i): "value_" + str(i) for i in range(10000)}

        # Should handle large context without error
        logger.info("Test", **large_context)

    def test_deeply_nested_context(self):
        """Test logger with deeply nested context."""
        logger = TenantAwareLogger("test")
        nested = {"level1": {"level2": {"level3": {"level4": "value"}}}}

        # Should handle nested context
        logger.info("Test", **nested)


class TestTimeoutHandling:
    """Test timeout handling."""

    def test_timeout_simulation(self):
        """Test timeout simulation with asyncio."""
        async def slow_operation():
            await asyncio.sleep(0.1)
            return "done"

        async def with_timeout():
            try:
                result = await asyncio.wait_for(slow_operation(), timeout=0.2)
                return result
            except asyncio.TimeoutError:
                return "timeout"

        result = asyncio.run(with_timeout())
        assert result == "done"

    def test_timeout_exceeded(self):
        """Test timeout exceeded scenario."""
        async def very_slow_operation():
            await asyncio.sleep(1.0)
            return "done"

        async def with_timeout():
            try:
                result = await asyncio.wait_for(very_slow_operation(), timeout=0.1)
                return result
            except asyncio.TimeoutError:
                return "timeout"

        result = asyncio.run(with_timeout())
        assert result == "timeout"


class TestRaceConditions:
    """Test race condition scenarios."""

    def test_concurrent_namespace_prefix_generation(self):
        """Test concurrent namespace prefix generation."""
        prefixes = set()
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = []
            for i in range(100):
                for j in range(10):
                    # Use default arguments to capture loop variables
                    future = executor.submit(
                        lambda i=i, j=j: TenantNamespace(f"tenant_{i}", f"account_{j}").to_redis_prefix()
                    )
                    futures.append(future)

            for future in futures:
                prefixes.add(future.result())

        # All prefixes should be unique
        assert len(prefixes) == 1000

    def test_concurrent_hash_collision_unlikely(self):
        """Test concurrent hash operations (collision unlikely)."""
        from core.tenant_aware_logger import hash_tenant_id

        hashes = set()
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [
                executor.submit(hash_tenant_id, f"unique_string_{i}_{j}")
                for i in range(100)
                for j in range(10)
            ]

            for future in futures:
                hashes.add(future.result())

        # With 1000 unique strings, collisions are extremely unlikely with SHA256
        assert len(hashes) == 1000


class TestErrorConditionsUnderLoad:
    """Test error conditions under load."""

    def test_workflow_with_negative_timeout(self):
        """Test workflow with negative timeout."""
        wf = WorkflowDefinition.create(
            "wf_1", "workflow_1", "tenant_1", "account_1", timeout_seconds=-1
        )
        assert wf.timeout_seconds == -1

    def test_workflow_with_zero_retries(self):
        """Test workflow with zero retries."""
        wf = WorkflowDefinition.create(
            "wf_1", "workflow_1", "tenant_1", "account_1", max_retries=0
        )
        assert wf.max_retries == 0

    def test_execution_result_with_invalid_stop_reason(self):
        """Test execution result normalization with invalid stop reason."""
        payload = {"content": "Response", "stopped_reason": "invalid_reason"}
        result = ExecutionResult.from_backend_payload(payload)

        # Should normalize to ERROR
        assert result.stopped_reason == StopReason.ERROR

    def test_kernel_without_backends_error(self):
        """Test kernel without backends raises error."""
        kernel = RuntimeKernel()
        task = MagicMock()
        task.task_type = "system_stats"
        workflow = MagicMock()
        workflow.mode = ""
        workflow.intent = "system_stats"
        workflow.plan_schema = {"steps": [{}]}

        strategy = kernel.choose_strategy(task, workflow)

        # Create context with deterministic strategy
        ctx = MagicMock()
        ctx.strategy = ExecutionStrategy.DETERMINISTIC
        ctx.task = task
        ctx.workflow = workflow

        # Should raise error when trying to execute without backend
        with pytest.raises(RuntimeKernelConfigurationError):
            asyncio.run(kernel._dispatch(ctx))


class TestMemoryPressure:
    """Test memory pressure scenarios."""

    def test_many_large_objects(self):
        """Test creating many large objects."""
        objects = []
        for i in range(100):
            large_obj = {"data": "x" * 100000}  # 100KB each
            objects.append(large_obj)

        assert len(objects) == 100
        assert all(len(o["data"]) == 100000 for o in objects)

    def test_large_list_operations(self):
        """Test large list operations."""
        large_list = list(range(100000))

        # Should handle large list operations
        assert len(large_list) == 100000
        assert sum(large_list[:1000]) == sum(range(1000))


class TestIntegrationScenarios:
    """Test integration scenarios under load."""

    def test_full_workflow_lifecycle_under_load(self):
        """Test full workflow lifecycle with many workflows."""
        workflows = []
        executions = []

        # Create many workflows
        for i in range(100):
            wf = WorkflowDefinition.create(
                f"wf_{i}", f"workflow_{i}", f"tenant_{i}", f"account_{i}"
            )
            workflows.append(wf)

        # Execute them
        for i, wf in enumerate(workflows):
            execution = WorkflowExecution(
                workflow_id=wf.workflow_id,
                status=WorkflowStatus.COMPLETED,
                result={"index": i},
                error=None,
                started_at=float(i),
                completed_at=float(i + 1),
            )
            executions.append(execution)

        assert len(workflows) == 100
        assert len(executions) == 100
        assert all(e.is_successful() for e in executions)

    def test_namespace_isolation_under_load(self):
        """Test namespace isolation with many tenants."""
        namespaces = []
        for i in range(100):
            ns = TenantNamespace(f"tenant_{i}", f"account_{i}")
            namespaces.append(ns)

        # Verify all prefixes are unique
        prefixes = [ns.to_redis_prefix() for ns in namespaces]
        assert len(set(prefixes)) == len(prefixes)

    def test_runtime_kernel_strategy_selection_under_load(self):
        """Test strategy selection with many tasks."""
        kernel = RuntimeKernel()
        strategies = []

        for i in range(100):
            task = MagicMock()
            task.task_type = "chat" if i % 2 == 0 else "system_stats"
            workflow = MagicMock()
            workflow.mode = ""
            workflow.intent = "system_stats" if i % 2 == 1 else ""
            workflow.plan_schema = {"steps": [{}]} if i % 2 == 1 else {}

            strategy = kernel.choose_strategy(task, workflow)
            strategies.append(strategy)

        # Should have a mix of strategies
        assert ExecutionStrategy.DETERMINISTIC in strategies
        assert ExecutionStrategy.HERMES_AGENT in strategies
