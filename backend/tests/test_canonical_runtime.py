"""Comprehensive tests for canonical runtime components.

Tests cover:
- ExecutionStrategy enum
- StopReason enum
- ExecutionMessage
- ExecutionContext
- TokenUsage
- ExecutionResult
- RuntimeKernel
- Protocol contracts
- Strategy selection logic
- Result normalization
- Edge cases and error handling
"""

import dataclasses
from unittest.mock import MagicMock

import pytest

from domain.orchestrator.runtime_kernel import (
    DeterministicExecutionBackend,
    ExecutionContext,
    ExecutionMessage,
    ExecutionResult,
    ExecutionStrategy,
    HermesExecutionBackend,
    RuntimeKernel,
    RuntimeKernelConfigurationError,
    StopReason,
    SubagentExecutionBackend,
    TokenUsage,
    WorkflowExecutionBackend,
)


class TestExecutionStrategy:
    """Test ExecutionStrategy enum."""

    def test_strategy_values(self):
        """Test all strategy values exist."""
        assert ExecutionStrategy.DETERMINISTIC.value == "deterministic"
        assert ExecutionStrategy.HERMES_AGENT.value == "hermes_agent"
        assert ExecutionStrategy.WORKFLOW_DAG.value == "workflow_dag"
        assert ExecutionStrategy.SUBAGENT.value == "subagent"

    def test_strategy_comparison(self):
        """Test strategy comparison."""
        assert ExecutionStrategy.DETERMINISTIC == ExecutionStrategy.DETERMINISTIC
        assert ExecutionStrategy.DETERMINISTIC != ExecutionStrategy.HERMES_AGENT


class TestStopReason:
    """Test StopReason enum."""

    def test_reason_values(self):
        """Test all reason values exist."""
        assert StopReason.END_TURN.value == "end_turn"
        assert StopReason.APPROVAL_REQUIRED.value == "approval_required"
        assert StopReason.MAX_ITERATIONS.value == "max_iterations"
        assert StopReason.ERROR.value == "error"
        assert StopReason.CANCELLED.value == "cancelled"

    def test_reason_comparison(self):
        """Test reason comparison."""
        assert StopReason.END_TURN == StopReason.END_TURN
        assert StopReason.END_TURN != StopReason.ERROR


class TestExecutionMessage:
    """Test ExecutionMessage dataclass."""

    def test_create_message(self):
        """Test creating execution message."""
        message = ExecutionMessage(role="user", content="Hello")
        assert message.role == "user"
        assert message.content == "Hello"
        assert message.metadata == {}

    def test_create_message_with_metadata(self):
        """Test creating message with metadata."""
        message = ExecutionMessage(role="user", content="Hello", metadata={"key": "value"})
        assert message.metadata == {"key": "value"}

    def test_message_frozen(self):
        """Test ExecutionMessage is frozen (immutable)."""
        message = ExecutionMessage(role="user", content="Hello")
        with pytest.raises(dataclasses.FrozenInstanceError):
            message.role = "assistant"  # type: ignore


class TestTokenUsage:
    """Test TokenUsage dataclass."""

    def test_default_values(self):
        """Test default token usage values."""
        usage = TokenUsage()
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.cache_read_tokens == 0
        assert usage.estimated_cost_usd == 0.0

    def test_custom_values(self):
        """Test custom token usage values."""
        usage = TokenUsage(
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=25,
            estimated_cost_usd=0.01,
        )
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.cache_read_tokens == 25
        assert usage.estimated_cost_usd == 0.01

    def test_token_usage_frozen(self):
        """Test TokenUsage is frozen (immutable)."""
        usage = TokenUsage(input_tokens=100)
        with pytest.raises(dataclasses.FrozenInstanceError):
            usage.input_tokens = 200  # type: ignore


class TestExecutionResult:
    """Test ExecutionResult dataclass."""

    def test_create_result(self):
        """Test creating execution result."""
        result = ExecutionResult(content="Response")
        assert result.content == "Response"
        assert result.actions == ()
        assert result.token_usage == TokenUsage()
        assert result.duration_ms == 0
        assert result.tool_calls_made == 0
        assert result.stopped_reason == StopReason.END_TURN

    def test_create_result_with_values(self):
        """Test creating result with values."""
        result = ExecutionResult(
            content="Response",
            actions=[{"type": "tool_call"}],
            token_usage=TokenUsage(input_tokens=100, output_tokens=50),
            duration_ms=1000,
            tool_calls_made=2,
            stopped_reason=StopReason.MAX_ITERATIONS,
        )
        assert result.content == "Response"
        assert result.tool_calls_made == 2
        assert result.stopped_reason == StopReason.MAX_ITERATIONS

    def test_to_legacy_dict(self):
        """Test converting to legacy dict format."""
        result = ExecutionResult(
            content="Response",
            actions=[{"type": "tool_call"}],
            token_usage=TokenUsage(input_tokens=100, output_tokens=50),
            duration_ms=1000,
            tool_calls_made=2,
            stopped_reason=StopReason.MAX_ITERATIONS,
        )
        legacy = result.to_legacy_dict()

        assert legacy["content"] == "Response"
        assert legacy["actions"] == [{"type": "tool_call"}]
        assert legacy["input_tokens"] == 100
        assert legacy["output_tokens"] == 50
        assert legacy["stopped_reason"] == "max_iterations"

    def test_from_backend_payload(self):
        """Test creating result from backend payload."""
        payload = {
            "content": "Response",
            "actions": [{"type": "tool_call"}],
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_tokens": 25,
            "estimated_cost_usd": 0.01,
            "duration_ms": 1000,
            "tool_calls_made": 2,
            "stopped_reason": "max_iterations",
        }
        result = ExecutionResult.from_backend_payload(payload)

        assert result.content == "Response"
        assert result.token_usage.input_tokens == 100
        assert result.token_usage.output_tokens == 50
        assert result.stopped_reason == StopReason.MAX_ITERATIONS

    def test_from_backend_payload_with_missing_fields(self):
        """Test creating result with missing fields uses defaults."""
        payload = {"content": "Response"}
        result = ExecutionResult.from_backend_payload(payload)

        assert result.content == "Response"
        assert result.token_usage == TokenUsage()
        assert result.duration_ms == 0
        assert result.stopped_reason == StopReason.END_TURN

    def test_result_frozen(self):
        """Test ExecutionResult is frozen (immutable)."""
        result = ExecutionResult(content="Response")
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.content = "New Response"  # type: ignore


class TestRuntimeKernel:
    """Test RuntimeKernel class."""

    def test_init_with_no_backends(self):
        """Test initialization with no backends."""
        kernel = RuntimeKernel()
        assert kernel._deterministic is None
        assert kernel._hermes is None
        assert kernel._workflow is None
        assert kernel._subagent is None

    def test_init_with_backends(self):
        """Test initialization with backends."""
        deterministic = MagicMock(spec=DeterministicExecutionBackend)
        hermes = MagicMock(spec=HermesExecutionBackend)
        workflow = MagicMock(spec=WorkflowExecutionBackend)
        subagent = MagicMock(spec=SubagentExecutionBackend)

        kernel = RuntimeKernel(
            deterministic_backend=deterministic,
            hermes_backend=hermes,
            workflow_backend=workflow,
            subagent_backend=subagent,
        )

        assert kernel._deterministic is deterministic
        assert kernel._hermes is hermes
        assert kernel._workflow is workflow
        assert kernel._subagent is subagent

    def test_bind_workflow_backend(self):
        """Test binding workflow backend."""
        kernel = RuntimeKernel()
        workflow = MagicMock(spec=WorkflowExecutionBackend)

        kernel.bind_workflow_backend(workflow)
        assert kernel._workflow is workflow

    def test_bind_subagent_backend(self):
        """Test binding subagent backend."""
        kernel = RuntimeKernel()
        subagent = MagicMock(spec=SubagentExecutionBackend)

        kernel.bind_subagent_backend(subagent)
        assert kernel._subagent is subagent

    def test_require_deterministic_backend_raises_error(self):
        """Test requiring deterministic backend raises error when not configured."""
        kernel = RuntimeKernel()
        with pytest.raises(RuntimeKernelConfigurationError):
            kernel._require_deterministic_backend()

    def test_require_hermes_backend_raises_error(self):
        """Test requiring Hermes backend raises error when not configured."""
        kernel = RuntimeKernel()
        with pytest.raises(RuntimeKernelConfigurationError):
            kernel._require_hermes_backend()

    def test_require_workflow_backend_raises_error(self):
        """Test requiring workflow backend raises error when not configured."""
        kernel = RuntimeKernel()
        with pytest.raises(RuntimeKernelConfigurationError):
            kernel._require_workflow_backend()

    def test_require_subagent_backend_raises_error(self):
        """Test requiring subagent backend raises error when not configured."""
        kernel = RuntimeKernel()
        with pytest.raises(RuntimeKernelConfigurationError):
            kernel._require_subagent_backend()


class TestStrategySelection:
    """Test strategy selection logic."""

    def test_choose_strategy_subagent_task(self):
        """Test choosing subagent strategy for delegate task."""
        kernel = RuntimeKernel()
        task = MagicMock()
        task.task_type = "delegate"
        workflow = MagicMock()
        workflow.mode = ""
        workflow.intent = ""
        workflow.plan_schema = {}

        strategy = kernel.choose_strategy(task, workflow)
        assert strategy == ExecutionStrategy.SUBAGENT

    def test_choose_strategy_deterministic_task(self):
        """Test choosing deterministic strategy for system_stats task."""
        kernel = RuntimeKernel()
        task = MagicMock()
        task.task_type = "system_stats"
        workflow = MagicMock()
        workflow.mode = ""
        workflow.intent = "system_stats"
        workflow.plan_schema = {"steps": [{}]}

        strategy = kernel.choose_strategy(task, workflow)
        assert strategy == ExecutionStrategy.DETERMINISTIC

    def test_choose_strategy_workflow_task(self):
        """Test choosing workflow strategy for durable workflow."""
        kernel = RuntimeKernel()
        task = MagicMock()
        task.task_type = "session"
        workflow = MagicMock()
        workflow.mode = "durable"
        workflow.intent = ""
        workflow.plan_schema = {"steps": [{}]}

        strategy = kernel.choose_strategy(task, workflow)
        assert strategy == ExecutionStrategy.WORKFLOW_DAG

    def test_choose_strategy_default_hermes(self):
        """Test default strategy is Hermes agent."""
        kernel = RuntimeKernel()
        task = MagicMock()
        task.task_type = "chat"
        workflow = MagicMock()
        workflow.mode = ""
        workflow.intent = ""
        workflow.plan_schema = {}

        strategy = kernel.choose_strategy(task, workflow)
        assert strategy == ExecutionStrategy.HERMES_AGENT


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_token_usage_with_negative_values(self):
        """Test token usage with negative values (should be allowed)."""
        usage = TokenUsage(input_tokens=-1, output_tokens=-1)
        assert usage.input_tokens == -1
        assert usage.output_tokens == -1

    def test_token_usage_with_large_values(self):
        """Test token usage with very large values."""
        usage = TokenUsage(input_tokens=1000000, output_tokens=1000000)
        assert usage.input_tokens == 1000000
        assert usage.output_tokens == 1000000

    def test_execution_message_with_unicode(self):
        """Test execution message with unicode content."""
        message = ExecutionMessage(role="user", content="日本語 中文 العربية")
        assert "日本語" in message.content

    def test_execution_result_with_empty_content(self):
        """Test execution result with empty content."""
        result = ExecutionResult(content="")
        assert result.content == ""

    def test_execution_result_with_large_content(self):
        """Test execution result with large content."""
        large_content = "x" * 100000
        result = ExecutionResult(content=large_content)
        assert len(result.content) == 100000

    def test_from_backend_payload_with_none_values(self):
        """Test creating result with None values in payload."""
        payload = {"content": None, "actions": None}
        result = ExecutionResult.from_backend_payload(payload)
        assert result.content == ""
        assert result.actions == ()

    def test_from_backend_payload_with_invalid_actions(self):
        """Test creating result with invalid actions."""
        payload = {"content": "Response", "actions": ["not_a_dict", {"type": "valid"}]}
        result = ExecutionResult.from_backend_payload(payload)
        assert len(result.actions) == 1
        assert result.actions[0] == {"type": "valid"}

    def test_normalize_stop_reason_invalid(self):
        """Test normalizing invalid stop reason returns ERROR."""
        from domain.orchestrator.runtime_kernel import _normalize_stop_reason

        result = _normalize_stop_reason("invalid_reason")
        assert result == StopReason.ERROR

    def test_normalize_stop_reason_case_insensitive(self):
        """Test normalizing stop reason is case insensitive."""
        from domain.orchestrator.runtime_kernel import _normalize_stop_reason

        result = _normalize_stop_reason("ERROR")
        assert result == StopReason.ERROR

    def test_normalize_stop_reason_whitespace(self):
        """Test normalizing stop reason with whitespace."""
        from domain.orchestrator.runtime_kernel import _normalize_stop_reason

        result = _normalize_stop_reason("  end_turn  ")
        assert result == StopReason.END_TURN


class TestIntegrationScenarios:
    """Test integration scenarios."""

    def test_full_result_conversion_cycle(self):
        """Test full conversion cycle: result -> dict -> result."""
        original = ExecutionResult(
            content="Response",
            actions=[{"type": "tool_call"}],
            token_usage=TokenUsage(input_tokens=100, output_tokens=50),
            duration_ms=1000,
            tool_calls_made=2,
            stopped_reason=StopReason.MAX_ITERATIONS,
        )

        legacy = original.to_legacy_dict()
        reconstructed = ExecutionResult.from_backend_payload(legacy)

        assert reconstructed.content == original.content
        assert reconstructed.token_usage.input_tokens == original.token_usage.input_tokens
        assert reconstructed.stopped_reason == original.stopped_reason

    def test_multiple_strategy_selections(self):
        """Test multiple strategy selections."""
        kernel = RuntimeKernel()

        # Subagent task
        task1 = MagicMock(task_type="delegate")
        workflow1 = MagicMock(mode="", intent="", plan_schema={})
        strategy1 = kernel.choose_strategy(task1, workflow1)

        # Deterministic task
        task2 = MagicMock(task_type="system_stats")
        workflow2 = MagicMock(mode="", intent="system_stats", plan_schema={"steps": [{}]})
        strategy2 = kernel.choose_strategy(task2, workflow2)

        # Default Hermes
        task3 = MagicMock(task_type="chat")
        workflow3 = MagicMock(mode="", intent="", plan_schema={})
        strategy3 = kernel.choose_strategy(task3, workflow3)

        assert strategy1 == ExecutionStrategy.SUBAGENT
        assert strategy2 == ExecutionStrategy.DETERMINISTIC
        assert strategy3 == ExecutionStrategy.HERMES_AGENT

    def test_kernel_with_partial_backends(self):
        """Test kernel with only some backends configured."""
        deterministic = MagicMock(spec=DeterministicExecutionBackend)
        kernel = RuntimeKernel(deterministic_backend=deterministic)

        assert kernel._deterministic is not None
        assert kernel._hermes is None
        assert kernel._workflow is None
        assert kernel._subagent is None

    def test_execution_context_immutability(self):
        """Test ExecutionContext is immutable (frozen)."""
        task = MagicMock()
        workflow = MagicMock()
        ctx = ExecutionContext(
            task=task,
            workflow=workflow,
            strategy=ExecutionStrategy.DETERMINISTIC,
            model="gpt-4",
            toolset=[],
            system_prompt="",
            messages=[],
            trace_id="trace_1",
            account_id="account_1",
            tenant_id="tenant_1",
            session_id="session_1",
        )

        with pytest.raises(dataclasses.FrozenInstanceError):
            ctx.strategy = ExecutionStrategy.HERMES_AGENT  # type: ignore
