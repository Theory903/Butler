"""
Production Smoke Tests - Validates end-to-end execution.
"""

import pytest


class TestLangChainIntegration:
    """Smoke tests for LangChain integration."""

    def test_models_import(self):
        from langchain.models import ButlerChatModel, ChatModelFactory

        assert ButlerChatModel is not None
        assert ChatModelFactory is not None

    def test_tools_import(self):
        from langchain.tools import ButlerLangChainTool, ButlerToolFactory

        assert ButlerLangChainTool is not None
        assert ButlerToolFactory is not None

    def test_memory_import(self):
        from langchain.memory import ButlerMemoryAdapter

        assert ButlerMemoryAdapter is not None

    def test_retrievers_import(self):
        from langchain.retrievers import ButlerSearchRetriever

        assert ButlerSearchRetriever is not None

    def test_evaluator_import(self):
        from langchain.evaluator import ButlerEvaluator

        assert ButlerEvaluator is not None

    def test_subgraph_import(self):
        from langchain.subgraph import create_research_graph

        assert create_research_graph is not None


class TestFutureAGIIntegration:
    """Smoke tests for Future AGI integration."""

    def test_futureagi_import(self):
        from futureagi import ButlerFutureAGIClient

        assert ButlerFutureAGIClient is not None


class TestToolRegistry:
    """Smoke tests for tool registry."""

    def test_registry_import(self):
        from services.tools.registry import ToolRegistry

        assert ToolRegistry is not None

    def test_resume_import(self):
        from services.orchestrator.resume import check_approval_expired, resume_approval

        assert resume_approval is not None
        assert check_approval_expired is not None


@pytest.mark.asyncio
async def test_end_to_end_chat():
    """End-to-end chat through LangGraph."""
    from core.envelope import ButlerEnvelope, SessionIdentity
    from services.orchestrator.langgraph_runtime import ButlerLangGraphRuntime

    runtime = ButlerLangGraphRuntime()
    assert runtime.available() is True

    envelope = ButlerEnvelope(
        session_id="smoke_test",
        identity=SessionIdentity(
            tenant_id="test",
            account_id="test",
        ),
        message="hello",
    )

    async def core_runner(envelope):
        from core.envelope import OrchestratorResult

        return OrchestratorResult(
            workflow_id="test",
            session_id=envelope.session_id,
            request_id=envelope.request_id,
            content="test",
            actions=[],
        )

    result = await runtime.run(envelope, core_runner=core_runner)
    assert result is not None
