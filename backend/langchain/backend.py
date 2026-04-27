"""
LangGraphAgentBackend - Butler's LangGraph agent backend implementation.

This backend replaces HermesAgentBackend with LangGraph-based agent execution,
preserving all Butler contracts (governance, streaming, multi-tenancy).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

import structlog
from langchain_core.messages import AIMessage, HumanMessage

from domain.ml.contracts import ReasoningTier
from domain.tools.hermes_compiler import ButlerToolSpec
from langchain.agent import create_agent
from langchain.runtime import ButlerToolRuntimeManager
from langchain.streaming import LangChainEventAdapter, stream_langchain_to_butler

logger = structlog.get_logger(__name__)


@dataclass
class AgentRequest:
    """Request for agent execution."""

    message: str
    tenant_id: str
    account_id: str
    session_id: str
    trace_id: str
    user_id: str | None = None
    system_prompt: str | None = None
    preferred_model: str | None = None
    preferred_tier: ReasoningTier | None = None
    conversation_history: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class AgentResponse:
    """Response from agent execution."""

    content: str
    tool_calls: list[dict[str, Any]] | None = None
    usage: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class LangGraphAgentBackend:
    """LangGraph-based agent backend for Butler.

    This backend:
    - Uses ButlerChatModel for ML inference with Butler's provider routing
    - Uses ButlerLangChainTool for hybrid governance execution
    - Uses ButlerAgentState with Postgres checkpointing for durability
    - Maps LangGraph events to Butler's canonical stream events
    - Preserves all Butler governance and multi-tenancy contracts
    - Matches Hermes backend interface for feature parity
    """

    def __init__(
        self,
        runtime_manager: Any,
        tool_specs: list[ButlerToolSpec],
        tool_executor: Any | None = None,
        direct_implementations: dict[str, Any] | None = None,
        checkpoint_config: dict[str, Any] | None = None,
        default_tier: ReasoningTier = ReasoningTier.T2,
        stream_chunk_size: int = 64,
    ):
        """Initialize the LangGraph agent backend.

        Args:
            runtime_manager: Butler's MLRuntimeManager
            tool_specs: List of ButlerToolSpec from domain/tools/hermes_compiler.py
            tool_executor: Butler's ToolExecutor for L2/L3 governance
            direct_implementations: Dict mapping tool name to direct implementation
            checkpoint_config: Optional checkpoint configuration for Postgres
            default_tier: Default reasoning tier (matches Hermes backend)
            stream_chunk_size: Stream chunk size in characters (matches Hermes backend)
        """
        if stream_chunk_size <= 0:
            raise ValueError("stream_chunk_size must be greater than 0")

        self.runtime_manager = runtime_manager
        self.tool_specs = tool_specs
        self.tool_executor = tool_executor
        self.direct_implementations = direct_implementations or {}
        self.checkpoint_config = checkpoint_config
        self._default_tier = default_tier
        self._stream_chunk_size = stream_chunk_size

    async def run(self, request: AgentRequest) -> AgentResponse:
        """Execute agent request synchronously.

        Args:
            request: AgentRequest with message and context

        Returns:
            AgentResponse with content and metadata
        """
        logger.info(
            "langgraph_agent_run_start",
            tenant_id=request.tenant_id,
            account_id=request.account_id,
            session_id=request.session_id,
            trace_id=request.trace_id,
        )

        # Create LangGraph agent
        agent = create_agent(
            runtime_manager=self.runtime_manager,
            tool_specs=self.tool_specs,
            tenant_id=request.tenant_id,
            account_id=request.account_id,
            session_id=request.session_id,
            trace_id=request.trace_id,
            tool_executor=self.tool_executor,
            direct_implementations=self.direct_implementations,
            user_id=request.user_id,
            preferred_model=request.preferred_model,
            preferred_tier=request.preferred_tier,
            system_prompt=request.system_prompt,
            checkpoint_config=self.checkpoint_config,
        )

        # Build initial state with conversation history
        messages = []
        if request.conversation_history:
            for turn in request.conversation_history:
                if turn.get("role") == "user":
                    messages.append(HumanMessage(content=turn.get("content", "")))
                elif turn.get("role") == "assistant":
                    messages.append(AIMessage(content=turn.get("content", "")))

        # Add current message
        messages.append(HumanMessage(content=request.message))

        # Create config with context
        tool_runtime = ButlerToolRuntimeManager.from_execution_context(
            tenant_id=request.tenant_id,
            account_id=request.account_id,
            session_id=request.session_id,
            trace_id=request.trace_id,
            user_id=request.user_id,
            **(request.metadata or {}),
        )

        config = tool_runtime.to_langgraph_config()
        config["configurable"]["thread_id"] = request.session_id

        # Invoke agent
        try:
            logger.info(
                "langgraph_agent_invoking",
                tenant_id=request.tenant_id,
                session_id=request.session_id,
                message_count=len(messages),
            )
            state = await agent.ainvoke(
                {
                    "messages": messages,
                    "tool_context": tool_runtime.get_context(),
                    "needs_approval": False,
                    "retry_count": 0,
                    "last_error": None,
                },
                config=config,
            )
            logger.info(
                "langgraph_agent_invoke_success",
                tenant_id=request.tenant_id,
                session_id=request.session_id,
            )

            # Log all message types in final state for debugging
            logger.info(
                "langgraph_final_state_messages",
                session_id=request.session_id,
                messages=[
                    {
                        "type": type(m).__name__,
                        "role": getattr(m, "type", "unknown"),
                        "content_snippet": str(getattr(m, "content", "") or "")[:80],
                        "has_tool_calls": bool(
                            (hasattr(m, "tool_calls") and m.tool_calls)
                            or (
                                hasattr(m, "additional_kwargs")
                                and m.additional_kwargs.get("tool_calls")
                            )
                        ),
                    }
                    for m in state["messages"]
                ],
            )

            # Extract final response: walk backwards, pick the last AIMessage
            # with non-empty text. HumanMessage/ToolMessage are excluded.
            # qwen3 emits thinking+tool_call in one turn (content = thinking text);
            # we want the final synthesis turn after tool execution.
            content = ""
            for msg in reversed(state["messages"]):
                if not isinstance(msg, AIMessage):
                    continue
                text = str(getattr(msg, "content", "") or "").strip()
                if not text:
                    continue
                # Skip if message only has tool_calls and no synthesized text
                has_tool_calls = bool(
                    (hasattr(msg, "tool_calls") and msg.tool_calls)
                    or msg.additional_kwargs.get("tool_calls")
                )
                if has_tool_calls and not text:
                    continue
                content = text
                break

            # Extract tool calls
            tool_calls = []
            for msg in state["messages"]:
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    tool_calls.extend(msg.tool_calls)

            logger.info(
                "langgraph_agent_run_complete",
                tenant_id=request.tenant_id,
                session_id=request.session_id,
                message_count=len(state["messages"]),
                tool_call_count=len(tool_calls),
            )

            return AgentResponse(
                content=content,
                tool_calls=tool_calls,
                usage={"message_count": len(state["messages"])},
                metadata={"backend": "langgraph"},
            )

        except Exception as exc:
            logger.error(
                "langgraph_agent_run_failed",
                tenant_id=request.tenant_id,
                session_id=request.session_id,
                error=str(exc),
            )
            raise RuntimeError(f"LangGraph agent execution failed: {exc}") from exc

    async def run_streaming(
        self,
        request: AgentRequest,
    ) -> AsyncGenerator[Any]:
        """Execute agent request with streaming.

        Args:
            request: AgentRequest with message and context

        Yields:
            Butler canonical events (StreamTokenEvent, StreamFinalEvent, etc)
        """
        logger.info(
            "langgraph_agent_streaming_start",
            tenant_id=request.tenant_id,
            account_id=request.account_id,
            session_id=request.session_id,
            trace_id=request.trace_id,
        )

        # Create LangGraph agent
        agent = create_agent(
            runtime_manager=self.runtime_manager,
            tool_specs=self.tool_specs,
            tenant_id=request.tenant_id,
            account_id=request.account_id,
            session_id=request.session_id,
            trace_id=request.trace_id,
            user_id=request.user_id,
            preferred_model=request.preferred_model,
            preferred_tier=request.preferred_tier,
            system_prompt=request.system_prompt,
            checkpoint_config=self.checkpoint_config,
        )

        # Build initial state
        messages = []
        if request.conversation_history:
            for turn in request.conversation_history:
                if turn.get("role") == "user":
                    messages.append(HumanMessage(content=turn.get("content", "")))
                elif turn.get("role") == "assistant":
                    messages.append(AIMessage(content=turn.get("content", "")))

        messages.append(HumanMessage(content=request.message))

        # Create config with context
        tool_runtime = ButlerToolRuntimeManager.from_execution_context(
            tenant_id=request.tenant_id,
            account_id=request.account_id,
            session_id=request.session_id,
            trace_id=request.trace_id,
            user_id=request.user_id,
            **(request.metadata or {}),
        )

        config = tool_runtime.to_langgraph_config()
        config["configurable"]["thread_id"] = request.session_id

        # Create event adapter
        event_adapter = LangChainEventAdapter(
            account_id=request.account_id,
            session_id=request.session_id,
            trace_id=request.trace_id,
            task_id=request.trace_id,  # Use trace_id as task_id for now
        )

        try:
            # Stream LangGraph events and convert to Butler events
            langchain_stream = agent.astream_events(
                {"messages": messages, "tool_context": tool_runtime.get_context()},
                config=config,
                version="v1",
            )

            async for butler_event in stream_langchain_to_butler(langchain_stream, event_adapter):
                yield butler_event

            logger.info(
                "langgraph_agent_streaming_complete",
                tenant_id=request.tenant_id,
                session_id=request.session_id,
            )

        except Exception as exc:
            logger.error(
                "langgraph_agent_streaming_failed",
                tenant_id=request.tenant_id,
                session_id=request.session_id,
                error=str(exc),
            )
            yield event_adapter.create_error_event(
                error_type="https://butler.ai/errors/agent-streaming-failed",
                title="Agent streaming failed",
                detail=str(exc),
                status=500,
                retryable=False,
            )
