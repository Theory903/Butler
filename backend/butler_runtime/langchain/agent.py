"""Butler Runtime LangChain Agent.

Provides LangChain-compatible agent interface for the Butler unified runtime.
"""

import logging
from typing import Any

from ..agent.loop import ButlerExecutionContext, ButlerUnifiedAgentLoop
from ..graph.compiler import ButlerGraphCompiler
from .tools import ButlerLangChainTools

import structlog

logger = structlog.get_logger(__name__)


class ButlerLangChainAgent:
    """LangChain-compatible agent interface for Butler unified runtime.

    Wraps Butler's unified agent loop to work with LangChain patterns.
    """

    def __init__(
        self,
        agent_loop: ButlerUnifiedAgentLoop,
        graph_compiler: ButlerGraphCompiler,
        langchain_tools: ButlerLangChainTools,
    ) -> None:
        """Initialize LangChain agent.

        Args:
            agent_loop: ButlerUnifiedAgentLoop instance
            graph_compiler: ButlerGraphCompiler instance
            langchain_tools: ButlerLangChainTools instance
        """
        self._agent_loop = agent_loop
        self._graph_compiler = graph_compiler
        self._langchain_tools = langchain_tools

    async def ainvoke(
        self,
        input: str,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Invoke the agent with LangChain-compatible interface.

        Args:
            input: User input
            config: Optional configuration (account_id, session_id, model, etc.)

        Returns:
            Agent response with metadata

        Note:
            This is a stub. Real implementation would use LangChain's
            AgentExecutor or similar patterns.
        """
        config = config or {}

        # Build execution context
        ctx = ButlerExecutionContext(
            account_id=config.get("account_id", "default"),
            session_id=config.get("session_id", "default"),
            user_message=input,
            model=config.get("model", "gpt-4"),
            conversation_history=config.get("conversation_history", []),
            system_message=config.get("system_message"),
            memory_context=config.get("memory_context"),
            account_tier=config.get("account_tier", "free"),
            channel=config.get("channel", "api"),
            assurance_level=config.get("assurance_level", "AAL1"),
            product_tier=config.get("product_tier"),
            industry_profile=config.get("industry_profile"),
        )

        # Run agent loop
        result = await self._agent_loop.run(ctx)

        return {
            "output": result.get("final_response"),
            "metadata": result.get("metadata", {}),
        }

    async def astream(
        self,
        input: str,
        config: dict[str, Any] | None = None,
    ):
        """Stream agent output with LangChain-compatible interface.

        Args:
            input: User input
            config: Optional configuration

        Yields:
            Agent events (tokens, tool calls, etc.)

        Note:
            This is a stub. Real implementation would stream events
            through ButlerEventSink.
        """
        config = config or {}

        # Build execution context
        ctx = ButlerExecutionContext(
            account_id=config.get("account_id", "default"),
            session_id=config.get("session_id", "default"),
            user_message=input,
            model=config.get("model", "gpt-4"),
            conversation_history=config.get("conversation_history", []),
            system_message=config.get("system_message"),
            memory_context=config.get("memory_context"),
            account_tier=config.get("account_tier", "free"),
            channel=config.get("channel", "api"),
            assurance_level=config.get("assurance_level", "AAL1"),
            product_tier=config.get("product_tier"),
            industry_profile=config.get("industry_profile"),
        )

        # Run agent loop (streaming stub)
        result = await self._agent_loop.run(ctx)
        yield {"type": "final", "content": result.get("final_response")}

    def get_tools(self) -> list[Any]:
        """Get LangChain-compatible tools.

        Returns:
            List of LangChain tools

        Note:
            This is a stub. Real implementation would return
            actual LangChain StructuredTool instances.
        """
        return self._langchain_tools.to_langchain_tools()

    def bind_tools(self, tool_names: list[str]) -> None:
        """Bind specific tools to the agent.

        Args:
            tool_names: List of tool names to bind

        Note:
            This is a stub. Real implementation would configure
            the agent loop with specific tools.
        """
        logger.debug(f"Binding tools: {tool_names}")
