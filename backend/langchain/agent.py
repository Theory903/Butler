"""LangGraph Agent Builder — ButlerChatModel with ButlerAgentState.

Creates LangGraph agents using Butler's components:
- ``ButlerChatModel``       for ML inference via Butler's provider routing
- ``ButlerAgentState``      for durable checkpointed state
- ``ButlerLangChainTool``   for hybrid governance execution

Production node sequence:
    intake → plan → safety → call_model → tools → memory_writeback → END
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import structlog
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from domain.memory.contracts import MemoryServiceContract
from domain.tools.hermes_compiler import ButlerToolSpec
from langchain.middleware.base import ButlerMiddlewareContext, MiddlewareOrder
from langchain.middleware.registry import ButlerMiddlewareRegistry
from langchain.models import ChatModelFactory
from langchain.runtime import ButlerToolContext
from langchain.tools import ButlerToolFactory

logger = structlog.get_logger(__name__)

# BM25 is optional: absent if langchain-community is not installed.
try:
    from langchain_community.retrievers import BM25Retriever
    from langchain_core.documents import Document as _LCDocument
    _BM25_AVAILABLE = True
except ImportError:
    _BM25_AVAILABLE = False
    BM25Retriever = None  # type: ignore[assignment,misc]
    _LCDocument = None   # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tool_call_get(tc: Any, key: str, default: Any = None) -> Any:
    """Safely extract a value from a tool call dict or object."""
    if isinstance(tc, dict):
        return tc.get(key, default)
    return getattr(tc, key, default)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class ButlerAgentState(TypedDict):
    """State for Butler's LangGraph agent (checkpointed via Postgres)."""

    messages: Sequence[BaseMessage]
    tool_context: ButlerToolContext | None
    needs_approval: bool
    retry_count: int
    last_error: str | None


# ---------------------------------------------------------------------------
# DI factory
# ---------------------------------------------------------------------------


def create_agent_from_di(
    tenant_id: str,
    account_id: str,
    session_id: str,
    trace_id: str,
    user_id: str | None = None,
    preferred_model: str | None = None,
    preferred_tier: Any | None = None,
    system_prompt: str | None = None,
    checkpoint_config: dict[str, Any] | None = None,
    middleware_registry: ButlerMiddlewareRegistry | None = None,
    memory_service: MemoryServiceContract | None = None,
) -> Any:
    """Create a LangGraph agent wired from Butler's DI container.

    Wires the following from ``DependencyRegistry``:
    - ``MLRuntimeManager``  via ``get_ml_runtime()``
    - ``ButlerToolSpec``    via ``get_tool_specs()``
    - Checkpointer config   via ``get_checkpoint_config()``

    ``tool_executor`` and ``memory_service`` are request-scoped and must be
    supplied by the caller (e.g. via FastAPI ``Depends()``).

    Returns:
        Compiled LangGraph ``StateGraph``.
    """
    from core.deps import DependencyRegistry

    registry = DependencyRegistry()
    runtime_manager = registry.get_ml_runtime()
    tool_specs = registry.get_tool_specs()

    # tool_executor is request-scoped — callers must inject it.
    # TODO: wire tool_executor from DI once the scope boundary is resolved.
    tool_executor: Any = None

    effective_checkpoint = checkpoint_config or registry.get_checkpoint_config()

    builder = ButlerAgentBuilder(
        runtime_manager=runtime_manager,
        tool_specs=tool_specs,
        tool_executor=tool_executor,
        middleware_registry=middleware_registry,
        memory_service=memory_service,
    )

    kwargs: dict[str, Any] = dict(
        tenant_id=tenant_id,
        account_id=account_id,
        session_id=session_id,
        trace_id=trace_id,
        user_id=user_id,
        preferred_model=preferred_model,
        preferred_tier=preferred_tier,
        system_prompt=system_prompt,
    )

    if effective_checkpoint:
        return builder.create_agent_with_checkpointing(
            **kwargs,
            checkpoint_config=effective_checkpoint,
        )
    return builder.create_agent(**kwargs)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class ButlerAgentBuilder:
    """Builder for LangGraph agents using Butler components.

    Thread-safety: instances are **not** safe for concurrent use; create one
    builder per request or ensure external synchronisation.  The builder
    **never** mutates its own attributes during graph construction — all
    per-invocation overrides are passed explicitly through the internal
    ``_build_graph`` method.
    """

    def __init__(
        self,
        runtime_manager: Any,
        tool_specs: list[ButlerToolSpec],
        tool_executor: Any | None = None,
        direct_implementations: dict[str, Any] | None = None,
        middleware_registry: ButlerMiddlewareRegistry | None = None,
        memory_service: MemoryServiceContract | None = None,
    ) -> None:
        self.runtime_manager = runtime_manager
        self.tool_specs = tool_specs
        self.tool_executor = tool_executor
        self.direct_implementations: dict[str, Any] = direct_implementations or {}
        self.middleware_registry = middleware_registry
        self.memory_service = memory_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_agent(
        self,
        tenant_id: str,
        account_id: str,
        session_id: str,
        trace_id: str,
        user_id: str | None = None,
        preferred_model: str | None = None,
        preferred_tier: Any | None = None,
        system_prompt: str | None = None,
    ) -> StateGraph:
        """Build an **uncompiled** LangGraph ``StateGraph``.

        Compilation (with or without checkpointing) is performed by
        ``create_agent_with_checkpointing``.
        """
        return self._build_graph(
            tenant_id=tenant_id,
            account_id=account_id,
            session_id=session_id,
            trace_id=trace_id,
            user_id=user_id,
            preferred_model=preferred_model,
            preferred_tier=preferred_tier,
            system_prompt=system_prompt,
            middleware_registry=self.middleware_registry,
            memory_service=self.memory_service,
        )

    def create_agent_with_checkpointing(
        self,
        tenant_id: str,
        account_id: str,
        session_id: str,
        trace_id: str,
        user_id: str | None = None,
        preferred_model: str | None = None,
        preferred_tier: Any | None = None,
        system_prompt: str | None = None,
        checkpoint_config: dict[str, Any] | None = None,
        middleware_registry: ButlerMiddlewareRegistry | None = None,
        memory_service: MemoryServiceContract | None = None,
    ) -> Any:
        """Build and compile a LangGraph agent with Postgres checkpointing.

        ``middleware_registry`` and ``memory_service`` override the builder's
        own defaults **only for this call** — the builder itself is never
        mutated, so concurrent or sequential calls are safe.

        Returns:
            Compiled LangGraph ``StateGraph``.
        """
        effective_middleware = middleware_registry if middleware_registry is not None else self.middleware_registry
        effective_memory = memory_service if memory_service is not None else self.memory_service

        logger.info("agent_creation_started", tenant_id=tenant_id, session_id=session_id)
        workflow = self._build_graph(
            tenant_id=tenant_id,
            account_id=account_id,
            session_id=session_id,
            trace_id=trace_id,
            user_id=user_id,
            preferred_model=preferred_model,
            preferred_tier=preferred_tier,
            system_prompt=system_prompt,
            middleware_registry=effective_middleware,
            memory_service=effective_memory,
        )
        logger.info("agent_creation_completed", tenant_id=tenant_id, session_id=session_id)

        return self._compile(workflow, checkpoint_config)

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_graph(
        self,
        tenant_id: str,
        account_id: str,
        session_id: str,
        trace_id: str,
        user_id: str | None,
        preferred_model: str | None,
        preferred_tier: Any | None,
        system_prompt: str | None,
        middleware_registry: ButlerMiddlewareRegistry | None,
        memory_service: MemoryServiceContract | None,
    ) -> StateGraph:
        """Core graph construction.  Never mutates ``self``."""
        # ── Tool context ────────────────────────────────────────────────
        tool_context = ButlerToolContext(
            tenant_id=tenant_id,
            account_id=account_id,
            session_id=session_id,
            trace_id=trace_id,
            user_id=user_id,
        )

        # ── LLM ─────────────────────────────────────────────────────────
        llm = ChatModelFactory.create(
            runtime_manager=self.runtime_manager,
            tenant_id=tenant_id,
            preferred_model=preferred_model,
            preferred_tier=preferred_tier,
        )

        # ── Tools ────────────────────────────────────────────────────────
        tools = ButlerToolFactory.create_tools_from_specs(
            specs=self.tool_specs,
            tool_context=tool_context,
            tool_executor=self.tool_executor,
            direct_implementations=self.direct_implementations,
        )

        # ── Bind tools to LLM ───────────────────────────────────────────
        try:
            llm_with_tools = llm.bind_tools(tools)
        except Exception as exc:
            logger.error(
                "agent_bind_tools_failed",
                session_id=session_id,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            raise

        # ── BM25 tool retriever (optional) ──────────────────────────────
        tool_retriever = self._build_tool_retriever(tools, session_id=session_id)

        # ── ToolNode ─────────────────────────────────────────────────────
        original_tool_node = ToolNode(tools)

        # ── Node definitions ─────────────────────────────────────────────
        # All nodes are defined as closures over the locals above.

        async def intake_node(state: ButlerAgentState, config: RunnableConfig) -> dict[str, Any]:
            logger.info("agent_intake", tenant_id=tenant_id, session_id=session_id)
            return {"needs_approval": False, "retry_count": 0, "last_error": None}

        async def plan_node(state: ButlerAgentState, config: RunnableConfig) -> dict[str, Any]:
            logger.debug("agent_plan", session_id=session_id)
            return {}

        async def safety_node(state: ButlerAgentState, config: RunnableConfig) -> dict[str, Any]:
            logger.debug("agent_safety", session_id=session_id)
            return {}

        async def call_model_node(
            state: ButlerAgentState, config: RunnableConfig
        ) -> dict[str, Any]:
            import time

            messages: list[BaseMessage] = list(state["messages"])
            start_time = time.monotonic()

            # Load memory context (prepend summary anchor, does not re-store history).
            if memory_service is not None:
                try:
                    context_pack = await memory_service.build_context(
                        account_id=account_id,
                        query="",
                        session_id=session_id,
                    )
                    if context_pack.summary_anchor:
                        messages = [SystemMessage(content=context_pack.summary_anchor)] + messages
                except Exception as exc:
                    logger.warning("memory_context_load_failed", session_id=session_id, error=str(exc))

            # Add system prompt if not already present.
            if system_prompt and not any(m.type == "system" for m in messages):
                messages = [SystemMessage(content=system_prompt)] + messages

            # Build middleware context.
            middleware_context = ButlerMiddlewareContext(
                tenant_id=tenant_id,
                account_id=account_id,
                session_id=session_id,
                trace_id=trace_id,
                user_id=user_id,
                model=preferred_model,
                tier=str(preferred_tier) if preferred_tier else None,
                messages=[{"role": m.type, "content": m.content} for m in messages],
            )

            # PRE_MODEL middleware.
            if middleware_registry is not None:
                pre_result = await middleware_registry.execute(
                    middleware_context, MiddlewareOrder.PRE_MODEL
                )
                if not pre_result.should_continue:
                    # Do not modify state — leave messages unchanged.
                    return {}

                if pre_result.modified_input and "messages" in pre_result.modified_input:
                    messages = [
                        HumanMessage(content=m["content"])
                        if m["role"] == "human"
                        else AIMessage(content=m["content"])
                        if m["role"] == "ai"
                        else m
                        for m in pre_result.modified_input["messages"]
                    ]

            # Select tools for this turn.
            invoke_llm = self._select_llm_for_turn(
                messages=messages,
                llm=llm,
                llm_with_tools=llm_with_tools,
                tool_retriever=tool_retriever,
                tools=tools,
                session_id=session_id,
            )

            response = await invoke_llm.ainvoke(messages, config)
            duration_ms = (time.monotonic() - start_time) * 1000

            logger.debug(
                "agent_llm_response",
                session_id=session_id,
                has_tool_calls=bool(getattr(response, "tool_calls", None)),
                tool_call_count=len(getattr(response, "tool_calls", []) or []),
            )

            # Persist only the latest user turn to avoid re-storing history.
            if memory_service is not None:
                await self._store_latest_turn(
                    memory_service=memory_service,
                    messages=messages,
                    response=response,
                    account_id=account_id,
                    session_id=session_id,
                    tenant_id=tenant_id,
                )

            # Update middleware context and run POST_MODEL.
            middleware_context.duration_ms = duration_ms
            middleware_context.messages = [
                {"role": m.type, "content": m.content}
                for m in list(messages) + [response]
            ]
            middleware_context.tool_calls = [
                {"name": _tool_call_get(tc, "name"), "args": _tool_call_get(tc, "args")}
                for tc in (getattr(response, "tool_calls", []) or [])
            ]

            if middleware_registry is not None:
                post_result = await middleware_registry.execute(
                    middleware_context, MiddlewareOrder.POST_MODEL
                )
                if not post_result.should_continue:
                    # Do not modify state.
                    return {}

            return {"messages": list(state["messages"]) + [response]}

        async def tools_node_with_middleware(
            state: ButlerAgentState, config: RunnableConfig
        ) -> dict[str, Any]:
            import time

            start_time = time.monotonic()

            tool_calls_snapshot = [
                {"name": _tool_call_get(tc, "name"), "args": _tool_call_get(tc, "args")}
                for m in state["messages"]
                if hasattr(m, "tool_calls") and m.tool_calls
                for tc in m.tool_calls
            ]
            middleware_context = ButlerMiddlewareContext(
                tenant_id=tenant_id,
                account_id=account_id,
                session_id=session_id,
                trace_id=trace_id,
                user_id=user_id,
                messages=[{"role": m.type, "content": m.content} for m in state["messages"]],
                tool_calls=tool_calls_snapshot,
            )

            if middleware_registry is not None:
                pre_result = await middleware_registry.execute(
                    middleware_context, MiddlewareOrder.PRE_TOOL
                )
                if not pre_result.should_continue:
                    return {}  # Leave state unchanged.

            tool_result = await original_tool_node.ainvoke(state, config)
            duration_ms = (time.monotonic() - start_time) * 1000

            middleware_context.duration_ms = duration_ms
            middleware_context.tool_results = [
                {"name": m.name, "content": m.content}
                for m in tool_result.get("messages", [])
                if isinstance(m, ToolMessage)
            ]

            if middleware_registry is not None:
                post_result = await middleware_registry.execute(
                    middleware_context, MiddlewareOrder.POST_TOOL
                )
                if not post_result.should_continue:
                    return {}  # Leave state unchanged.

            return tool_result

        async def memory_writeback_node(
            state: ButlerAgentState, config: RunnableConfig
        ) -> dict[str, Any]:
            """Placeholder for future async/batched memory writeback.

            In-turn persistence is handled in ``call_model_node`` via
            ``memory_service.store_turn``.  This node exists as an extension
            point for cross-session consolidation (e.g. episodic compression).
            """
            return {}

        # ── Routing ──────────────────────────────────────────────────────

        def route_after_intake(state: ButlerAgentState) -> str:
            return "plan"

        def route_after_plan(state: ButlerAgentState) -> str:
            return "safety"

        def route_after_safety(state: ButlerAgentState) -> str:
            return "call_model"

        def route_after_model(state: ButlerAgentState) -> str:
            messages = state["messages"]
            last = messages[-1] if messages else None
            if isinstance(last, AIMessage):
                has_tool_calls = bool(
                    (getattr(last, "tool_calls", None))
                    or last.additional_kwargs.get("tool_calls")
                )
                if has_tool_calls:
                    return "tools"
            return "memory_writeback"

        def route_after_tools(state: ButlerAgentState) -> str:
            if state["retry_count"] >= 3:
                logger.warning(
                    "agent_retry_limit_exceeded",
                    session_id=session_id,
                    retry_count=state["retry_count"],
                )
                return "memory_writeback"
            return "call_model"

        # ── Assemble graph ───────────────────────────────────────────────
        workflow = StateGraph(ButlerAgentState)

        workflow.add_node("intake", intake_node)
        workflow.add_node("plan", plan_node)
        workflow.add_node("safety", safety_node)
        workflow.add_node("call_model", call_model_node)
        workflow.add_node("tools", tools_node_with_middleware)
        workflow.add_node("memory_writeback", memory_writeback_node)

        workflow.set_entry_point("intake")

        workflow.add_conditional_edges("intake", route_after_intake)
        workflow.add_conditional_edges("plan", route_after_plan)
        workflow.add_conditional_edges("safety", route_after_safety)
        workflow.add_conditional_edges("call_model", route_after_model)
        workflow.add_conditional_edges("tools", route_after_tools)
        workflow.add_edge("memory_writeback", END)

        logger.info("agent_workflow_built", session_id=session_id)
        return workflow

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_tool_retriever(
        tools: list[Any], *, session_id: str
    ) -> Any | None:
        """Build a BM25 retriever for dynamic tool selection, if available."""
        if not _BM25_AVAILABLE or not tools:
            return None

        tool_docs = [
            _LCDocument(
                page_content=(
                    f"{getattr(t, 'name', '')} "
                    f"{getattr(t, 'description', '') or ''}"
                ).strip(),
                metadata={"index": idx},
            )
            for idx, t in enumerate(tools)
        ]

        try:
            retriever = BM25Retriever.from_documents(tool_docs)
            retriever.k = min(8, len(tools))
            logger.info(
                "agent_tool_retriever_ready",
                session_id=session_id,
                total_tools=len(tools),
                top_k=retriever.k,
            )
            return retriever
        except Exception as exc:
            logger.warning(
                "agent_tool_retriever_init_failed",
                session_id=session_id,
                error=str(exc),
            )
            return None

    @staticmethod
    def _select_llm_for_turn(
        *,
        messages: list[BaseMessage],
        llm: Any,
        llm_with_tools: Any,
        tool_retriever: Any | None,
        tools: list[Any],
        session_id: str,
    ) -> Any:
        """Return the appropriate LLM variant for this turn.

        - After a ``ToolMessage``: use bare LLM to force text synthesis.
        - Otherwise: use BM25 to select top-K relevant tools, or full tool LLM.
        """
        last = messages[-1] if messages else None
        if last is not None and getattr(last, "type", None) == "tool":
            return llm

        if tool_retriever is None:
            return llm_with_tools

        latest_human_text = next(
            (
                str(getattr(m, "content", "") or "")
                for m in reversed(messages)
                if getattr(m, "type", None) == "human"
            ),
            "",
        )

        if not latest_human_text.strip():
            return llm_with_tools

        try:
            retrieved = tool_retriever.invoke(latest_human_text)
            indices = [
                d.metadata["index"]
                for d in retrieved
                if isinstance(d.metadata.get("index"), int)
            ]
            selected = [tools[i] for i in indices if 0 <= i < len(tools)]
            if selected:
                logger.debug(
                    "agent_tools_selected",
                    session_id=session_id,
                    selected=[getattr(t, "name", "") for t in selected],
                )
                return llm.bind_tools(selected)
        except Exception as exc:
            logger.warning(
                "agent_tool_retrieval_failed",
                session_id=session_id,
                error=str(exc),
            )

        return llm_with_tools

    @staticmethod
    async def _store_latest_turn(
        *,
        memory_service: MemoryServiceContract,
        messages: list[BaseMessage],
        response: Any,
        account_id: str,
        session_id: str,
        tenant_id: str,
    ) -> None:
        """Persist only the **latest** user turn and the assistant response.

        Iterates in reverse to find the most recent human message, avoiding
        re-storage of prior conversation history on every turn.
        """
        try:
            latest_human = next(
                (m for m in reversed(messages) if m.type == "human"), None
            )
            if latest_human:
                await memory_service.store_turn(
                    account_id=account_id,
                    session_id=session_id,
                    role="user",
                    content=latest_human.content,
                    tenant_id=tenant_id,
                )
            if getattr(response, "content", None):
                await memory_service.store_turn(
                    account_id=account_id,
                    session_id=session_id,
                    role="assistant",
                    content=response.content,
                    tenant_id=tenant_id,
                )
        except Exception as exc:
            logger.warning(
                "memory_store_turn_failed",
                session_id=session_id,
                error=str(exc),
            )

    @staticmethod
    def _compile(workflow: StateGraph, checkpoint_config: dict[str, Any] | None) -> Any:
        """Compile *workflow* with the best available checkpointer."""
        if checkpoint_config:
            connection_string = checkpoint_config.get("connection_string", "")
            if connection_string:
                try:
                    from services.orchestrator.checkpointer import build_postgres_checkpointer

                    checkpointer = build_postgres_checkpointer(connection_string)
                    if checkpointer:
                        logger.info("agent_postgres_checkpoint_enabled")
                        return workflow.compile(checkpointer=checkpointer)
                except Exception as exc:
                    logger.warning(
                        "postgres_checkpointer_init_failed",
                        error=str(exc),
                    )

            logger.warning("postgres_checkpoint_not_available", fallback="memory")

        from langgraph.checkpoint.memory import MemorySaver

        return workflow.compile(checkpointer=MemorySaver())


# ---------------------------------------------------------------------------
# Module-level convenience factory
# ---------------------------------------------------------------------------


def create_agent(
    runtime_manager: Any,
    tool_specs: list[ButlerToolSpec],
    tenant_id: str,
    account_id: str,
    session_id: str,
    trace_id: str,
    tool_executor: Any | None = None,
    direct_implementations: dict[str, Any] | None = None,
    user_id: str | None = None,
    preferred_model: str | None = None,
    preferred_tier: Any | None = None,
    system_prompt: str | None = None,
    checkpoint_config: dict[str, Any] | None = None,
    middleware_registry: ButlerMiddlewareRegistry | None = None,
    memory_service: MemoryServiceContract | None = None,
) -> Any:
    """Convenience factory — creates a compiled Butler LangGraph agent.

    Returns:
        Compiled LangGraph ``StateGraph``.
    """
    builder = ButlerAgentBuilder(
        runtime_manager=runtime_manager,
        tool_specs=tool_specs,
        tool_executor=tool_executor,
        direct_implementations=direct_implementations,
        middleware_registry=middleware_registry,
        memory_service=memory_service,
    )

    kwargs: dict[str, Any] = dict(
        tenant_id=tenant_id,
        account_id=account_id,
        session_id=session_id,
        trace_id=trace_id,
        user_id=user_id,
        preferred_model=preferred_model,
        preferred_tier=preferred_tier,
        system_prompt=system_prompt,
    )

    if checkpoint_config:
        return builder.create_agent_with_checkpointing(
            **kwargs,
            checkpoint_config=checkpoint_config,
            middleware_registry=middleware_registry,
            memory_service=memory_service,
        )
    return builder.create_agent(**kwargs)