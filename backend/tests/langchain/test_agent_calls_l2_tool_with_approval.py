"""Test agent calls L2 tool with approval through ToolExecutor.

Phase A.2 acceptance test:
- Agent calls L2 tool
- ToolExecutor handles approval gating
- Audit log records execution
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from domain.tools.hermes_compiler import ButlerToolSpec, RiskTier
from domain.tools.contracts import ToolResult
from langchain.agent import ButlerAgentBuilder, create_agent
from langchain_core.messages import HumanMessage


@pytest.mark.asyncio
async def test_agent_calls_l2_tool_with_approval():
    """Test that agent routes L2 tool through ToolExecutor with approval check."""
    # Mock MLRuntimeManager
    mock_ml_runtime = AsyncMock()
    mock_ml_runtime.generate = AsyncMock(
        return_value=MagicMock(
            content="I'll execute that for you.",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
            model_version="claude-sonnet-4",
            provider_name="anthropic",
            finish_reason="stop",
            raw_response={
                "content": "I'll execute that for you.",
                "tool_calls": [],
            },
        )
    )

    # Mock ToolExecutor with approval gating
    mock_tool_executor = AsyncMock()
    mock_tool_executor.execute = AsyncMock(
        return_value=ToolResult(
            success=True,
            data={"result": "Tool executed successfully"},
            tool_name="file_write",
            execution_id="exec-123",
            verification=MagicMock(passed=True, checks=[]),
            compensation=None,
        )
    )

    # Create L2 tool spec (requires approval)
    l2_tool_spec = ButlerToolSpec(
        name="file_write",
        hermes_name="file_write",
        description="Write to file system",
        risk_tier=RiskTier.L2,
        approval_mode="explicit",
        sandbox_profile="docker",
        input_schema={"path": "string", "content": "string"},
        output_schema={"success": "boolean"},
    )

    # Create agent builder with ToolExecutor
    builder = ButlerAgentBuilder(
        runtime_manager=mock_ml_runtime,
        tool_specs=[l2_tool_spec],
        tool_executor=mock_tool_executor,
        middleware_registry=None,
        memory_service=None,
    )

    # Create agent
    agent = builder.create_agent(
        tenant_id="test-tenant-123",
        account_id="test-account-456",
        session_id="test-session-789",
        trace_id="test-trace-012",
    )

    # Invoke agent with a message that would trigger the L2 tool
    initial_state = {
        "messages": [HumanMessage(content="Write 'hello' to /tmp/test.txt")],
        "tool_context": None,
        "needs_approval": False,
        "retry_count": 0,
        "last_error": None,
    }

    config = {"configurable": {"thread_id": "test-thread"}}

    result = await agent.ainvoke(initial_state, config)

    # Assert ToolExecutor was called (not direct Hermes execution)
    mock_tool_executor.execute.assert_called_once()
    call_args = mock_tool_executor.execute.call_args
    assert call_args[1]["tool_name"] == "file_write"
    assert call_args[1]["tenant_id"] == "test-tenant-123"
    assert call_args[1]["account_id"] == "test-account-456"
    assert call_args[1]["session_id"] == "test-session-789"

    # Assert result contains messages
    assert "messages" in result
    assert len(result["messages"]) > 0


@pytest.mark.asyncio
async def test_l2_tool_blocked_without_approval():
    """Test that L2 tool is blocked when approval is not granted."""
    from domain.tools.exceptions import ToolErrors

    # Mock MLRuntimeManager
    mock_ml_runtime = AsyncMock()
    mock_ml_runtime.generate = AsyncMock(
        return_value=MagicMock(
            content="",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
            model_version="claude-sonnet-4",
            provider_name="anthropic",
            finish_reason="tool_calls",
            raw_response={
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "file_delete",
                            "arguments": '{"path": "/tmp/test.txt"}',
                        },
                    }
                ],
            },
        )
    )

    # Mock ToolExecutor that rejects L2 without approval
    mock_tool_executor = AsyncMock()
    mock_tool_executor.execute = AsyncMock(
        side_effect=ToolErrors.precondition_failed(
            "Tool execution requires approval for L2 risk tier"
        )
    )

    # Create L2 tool spec
    l2_tool_spec = ButlerToolSpec(
        name="file_delete",
        hermes_name="file_delete",
        description="Delete file",
        risk_tier=RiskTier.L2,
        approval_mode="explicit",
        sandbox_profile="docker",
        input_schema={"path": "string"},
        output_schema={"success": "boolean"},
    )

    builder = ButlerAgentBuilder(
        runtime_manager=mock_ml_runtime,
        tool_specs=[l2_tool_spec],
        tool_executor=mock_tool_executor,
        middleware_registry=None,
        memory_service=None,
    )

    agent = builder.create_agent(
        tenant_id="test-tenant",
        account_id="test-account",
        session_id="test-session",
        trace_id="test-trace",
    )

    initial_state = {
        "messages": [HumanMessage(content="Delete /tmp/test.txt")],
        "tool_context": None,
        "needs_approval": False,
        "retry_count": 0,
        "last_error": None,
    }

    config = {"configurable": {"thread_id": "test-thread"}}

    # Should raise error due to approval requirement
    with pytest.raises(Exception):  # ToolErrors.precondition_failed
        await agent.ainvoke(initial_state, config)

    # Assert ToolExecutor was called and rejected
    mock_tool_executor.execute.assert_called_once()


@pytest.mark.asyncio
async def test_hermes_tool_uses_executor_not_direct():
    """Test that ButlerHermesTool routes through ToolExecutor, not direct Hermes."""
    from langchain.hermes_tools import ButlerHermesTool, build_single_butler_hermes_tool

    # Mock ToolExecutor
    mock_tool_executor = AsyncMock()
    mock_tool_executor.execute = AsyncMock(
        return_value=ToolResult(
            success=True,
            data={"result": "Executed via ToolExecutor"},
            tool_name="test_tool",
            execution_id="exec-456",
            verification=MagicMock(passed=True, checks=[]),
            compensation=None,
        )
    )

    # Mock Hermes spec
    mock_spec = MagicMock()
    mock_spec.name = "test_tool"
    mock_spec.description = "Test tool"
    mock_spec.risk_tier = 2  # L2
    mock_spec.args_schema = None

    # Create ButlerHermesTool with ToolExecutor
    tool = build_single_butler_hermes_tool(
        spec=mock_spec,
        tool_executor=mock_tool_executor,
        tenant_id="test-tenant",
        account_id="test-account",
        session_id="test-session",
    )

    # Execute tool
    result = await tool._arun(param1="value1")

    # Assert ToolExecutor was called (not direct Hermes execution)
    mock_tool_executor.execute.assert_called_once()
    call_args = mock_tool_executor.execute.call_args
    assert call_args[1]["tool_name"] == "test_tool"
    assert call_args[1]["parameters"] == {"param1": "value1"}
    assert call_args[1]["tenant_id"] == "test-tenant"

    # Assert result is the data portion of ToolResult
    assert result == {"result": "Executed via ToolExecutor"}


@pytest.mark.asyncio
async def test_hermes_tool_requires_executor():
    """Test that ButlerHermesTool raises error without ToolExecutor."""
    from langchain.hermes_tools import ButlerHermesTool, build_single_butler_hermes_tool

    # Mock Hermes spec
    mock_spec = MagicMock()
    mock_spec.name = "test_tool"
    mock_spec.description = "Test tool"
    mock_spec.risk_tier = 1  # L1
    mock_spec.args_schema = None

    # Create ButlerHermesTool WITHOUT ToolExecutor
    tool = build_single_butler_hermes_tool(
        spec=mock_spec,
        tool_executor=None,  # Missing executor
    )

    # Should raise error when trying to execute
    with pytest.raises(RuntimeError) as exc_info:
        await tool._arun(param1="value1")

    assert "ToolExecutor required" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
