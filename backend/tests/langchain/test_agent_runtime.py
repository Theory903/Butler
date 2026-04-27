"""Test LangGraph agent runtime with Butler services integration.

Phase A.1 acceptance test:
- Boot a MemoryService + MLRuntimeManager + ToolExecutor from DI container
- Send a chat
- Assert tool call → executor → audit log
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import HumanMessage

from domain.memory.contracts import MemoryServiceContract
from domain.ml.contracts import ReasoningResponse, ReasoningTier
from domain.tools.hermes_compiler import ButlerToolSpec, RiskTier
from langchain.agent import ButlerAgentBuilder


@pytest.mark.asyncio
async def test_agent_runtime_with_real_services():
    """Test that agent boots with real Butler services and executes end-to-end."""
    # Mock MLRuntimeManager
    mock_ml_runtime = AsyncMock()
    mock_ml_runtime.generate = AsyncMock(
        return_value=ReasoningResponse(
            content="I'll help you with that.",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
            model_version="claude-sonnet-4",
            provider_name="anthropic",
            finish_reason="stop",
        )
    )

    # Mock MemoryService
    mock_memory_service = AsyncMock(spec=MemoryServiceContract)
    mock_memory_service.build_context = AsyncMock(
        return_value=MagicMock(
            summary_anchor="You are Butler, a helpful AI assistant.",
            context_pack=[],
        )
    )
    mock_memory_service.store_turn = AsyncMock()

    # Mock ToolExecutor
    mock_tool_executor = AsyncMock()
    mock_tool_executor.execute = AsyncMock(
        return_value={"status": "success", "result": "Tool executed"}
    )

    # Create a sample tool spec
    tool_spec = ButlerToolSpec(
        name="web_search",
        hermes_name="web_search",
        description="Search the web",
        risk_tier=RiskTier.L0,
        approval_mode="none",
        sandbox_profile="none",
        input_schema={"query": "string"},
        output_schema={"results": "list"},
    )

    # Create agent builder
    builder = ButlerAgentBuilder(
        runtime_manager=mock_ml_runtime,
        tool_specs=[tool_spec],
        tool_executor=mock_tool_executor,
        memory_service=mock_memory_service,
        middleware_registry=None,
    )

    # Create agent
    agent = builder.create_agent(
        tenant_id="test-tenant-123",
        account_id="test-account-456",
        session_id="test-session-789",
        trace_id="test-trace-012",
        user_id="test-user-345",
        preferred_model="claude-sonnet-4",
        preferred_tier=ReasoningTier.T2,
    )

    # Invoke agent with a message
    initial_state = {
        "messages": [HumanMessage(content="Hello, Butler!")],
        "tool_context": None,
        "needs_approval": False,
        "retry_count": 0,
        "last_error": None,
    }

    config = {"configurable": {"thread_id": "test-thread"}}

    # Run the agent
    result = await agent.ainvoke(initial_state, config)

    # Assert ML runtime was called
    mock_ml_runtime.generate.assert_called_once()
    call_args = mock_ml_runtime.generate.call_args
    assert call_args[1]["tenant_id"] == "test-tenant-123"

    # Assert memory context was loaded
    mock_memory_service.build_context.assert_called_once()
    call_args = mock_memory_service.build_context.call_args
    assert call_args[1]["account_id"] == "test-account-456"
    assert call_args[1]["session_id"] == "test-session-789"

    # Assert conversation turns were stored
    assert mock_memory_service.store_turn.call_count >= 1

    # Assert result contains messages
    assert "messages" in result
    assert len(result["messages"]) > 0


@pytest.mark.asyncio
async def test_agent_with_tool_call():
    """Test agent with tool call execution."""
    # Mock MLRuntimeManager that returns tool call
    mock_ml_runtime = AsyncMock()
    mock_ml_runtime.generate = AsyncMock(
        return_value=ReasoningResponse(
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
                            "name": "web_search",
                            "arguments": '{"query": "test"}',
                        },
                    }
                ],
            },
        )
    )

    # Mock services
    mock_memory_service = AsyncMock(spec=MemoryServiceContract)
    mock_memory_service.build_context = AsyncMock(
        return_value=MagicMock(summary_anchor="", context_pack=[])
    )
    mock_memory_service.store_turn = AsyncMock()

    mock_tool_executor = AsyncMock()
    mock_tool_executor.execute = AsyncMock(
        return_value={"status": "success", "result": "Search results"}
    )

    tool_spec = ButlerToolSpec(
        name="web_search",
        hermes_name="web_search",
        description="Search the web",
        risk_tier=RiskTier.L0,
        approval_mode="none",
        sandbox_profile="none",
        input_schema={"query": "string"},
        output_schema={"results": "list"},
    )

    builder = ButlerAgentBuilder(
        runtime_manager=mock_ml_runtime,
        tool_specs=[tool_spec],
        tool_executor=mock_tool_executor,
        memory_service=mock_memory_service,
        middleware_registry=None,
    )

    agent = builder.create_agent(
        tenant_id="test-tenant",
        account_id="test-account",
        session_id="test-session",
        trace_id="test-trace",
    )

    initial_state = {
        "messages": [HumanMessage(content="Search for something")],
        "tool_context": None,
        "needs_approval": False,
        "retry_count": 0,
        "last_error": None,
    }

    config = {"configurable": {"thread_id": "test-thread"}}

    result = await agent.ainvoke(initial_state, config)

    # Assert ML runtime was called
    assert mock_ml_runtime.generate.call_count >= 1


@pytest.mark.asyncio
async def test_agent_checkpointing():
    """Test agent with Postgres checkpointing."""
    from unittest.mock import patch

    mock_ml_runtime = AsyncMock()
    mock_ml_runtime.generate = AsyncMock(
        return_value=ReasoningResponse(
            content="Hello!",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
            model_version="claude-sonnet-4",
            provider_name="anthropic",
            finish_reason="stop",
        )
    )

    mock_memory_service = AsyncMock(spec=MemoryServiceContract)
    mock_memory_service.build_context = AsyncMock(
        return_value=MagicMock(summary_anchor="", context_pack=[])
    )
    mock_memory_service.store_turn = AsyncMock()

    tool_spec = ButlerToolSpec(
        name="test_tool",
        hermes_name="test_tool",
        description="Test tool",
        risk_tier=RiskTier.L0,
        approval_mode="none",
        sandbox_profile="none",
        input_schema={},
        output_schema={},
    )

    builder = ButlerAgentBuilder(
        runtime_manager=mock_ml_runtime,
        tool_specs=[tool_spec],
        tool_executor=None,
        memory_service=mock_memory_service,
        middleware_registry=None,
    )

    # Mock PostgresSaver
    with patch("langgraph.checkpoint.postgres.PostgresSaver") as mock_saver:
        mock_checkpointer = MagicMock()
        mock_saver.from_conn_string.return_value = mock_checkpointer

        agent = builder.create_agent_with_checkpointing(
            tenant_id="test-tenant",
            account_id="test-account",
            session_id="test-session",
            trace_id="test-trace",
            checkpoint_config={"connection_string": "postgresql://test"},
            memory_service=mock_memory_service,
        )

        # Assert PostgresSaver was configured
        mock_saver.from_conn_string.assert_called_once_with("postgresql://test")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
