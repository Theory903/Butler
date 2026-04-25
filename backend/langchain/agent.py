"""
LangGraph Agent Builder - ButlerChatModel with ButlerAgentState.

This module creates LangGraph agents using Butler's components:
- ButlerChatModel for ML inference with Butler's provider routing
- ButlerAgentState for durable checkpointed state
- ButlerLangChainTool for hybrid governance execution

Production node sequence:
intake → plan → safety → call_model → tools → memory_writeback → END
"""

from __future__ import annotations

from typing import Any, Sequence
from typing_extensions import TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

import structlog

from langchain.models import ButlerChatModel, ChatModelFactory
from langchain.runtime import ButlerToolContext
from langchain.tools import ButlerLangChainTool, ButlerToolFactory
from langchain.middleware.base import (
    ButlerMiddlewareContext,
    MiddlewareOrder,
)
from langchain.middleware.registry import ButlerMiddlewareRegistry
from langchain.memory import ButlerMemoryAdapter
from domain.tools.hermes_compiler import ButlerToolSpec
from domain.memory.contracts import MemoryServiceContract

logger = structlog.get_logger(__name__)


# DI integration for Phase A.6
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
    """Create a LangGraph agent using Butler's DI container.

    This factory method wires all dependencies from DependencyRegistry:
    - MLRuntimeManager from get_ml_runtime()
    - ToolExecutor from get_tools_service()
    - ButlerToolSpec from get_tool_specs()
    - MemoryService from get_memory_service() if provided
    - Checkpointer from get_checkpoint_config()

    Args:
        tenant_id: Tenant UUID for multi-tenant isolation
        account_id: Account UUID
        session_id: Session UUID
        trace_id: Trace UUID
        user_id: Optional user UUID
        preferred_model: Optional specific model name
        preferred_tier: Optional reasoning tier
        system_prompt: Optional system prompt
        checkpoint_config: Optional checkpoint configuration (overrides DI)
        middleware_registry: Optional middleware registry (overrides DI)
        memory_service: Optional memory service (overrides DI)

    Returns:
        Compiled LangGraph StateGraph
    """
    from core.deps import DependencyRegistry

    registry = DependencyRegistry()

    # Get dependencies from DI container
    runtime_manager = registry.get_ml_runtime()
    tool_specs = registry.get_tool_specs()

    # ToolExecutor and MemoryService are request-scoped, passed in
    # In production, these would be obtained via FastAPI Depends()
    tool_executor = None  # Will be injected by caller
    if memory_service is None:
        # MemoryService is request-scoped, caller must provide
        pass

    # Use provided checkpoint config or get from DI
    if checkpoint_config is None:
        checkpoint_config = registry.get_checkpoint_config()

    # Create builder with DI-wired dependencies
    builder = ButlerAgentBuilder(
        runtime_manager=runtime_manager,
        tool_specs=tool_specs,
        tool_executor=tool_executor,
        middleware_registry=middleware_registry,
        memory_service=memory_service,
    )

    # Create agent with checkpointing if config available
    if checkpoint_config:
        return builder.create_agent_with_checkpointing(
            tenant_id=tenant_id,
            account_id=account_id,
            session_id=session_id,
            trace_id=trace_id,
            user_id=user_id,
            preferred_model=preferred_model,
            preferred_tier=preferred_tier,
            system_prompt=system_prompt,
            checkpoint_config=checkpoint_config,
            middleware_registry=middleware_registry,
            memory_service=memory_service,
        )
    else:
        return builder.create_agent(
            tenant_id=tenant_id,
            account_id=account_id,
            session_id=session_id,
            trace_id=trace_id,
            user_id=user_id,
            preferred_model=preferred_model,
            preferred_tier=preferred_tier,
            system_prompt=system_prompt,
        )


class ButlerAgentState(TypedDict):
    """State for Butler's LangGraph agent.

    This state is checkpointed via langgraph-checkpoint-postgres for durability.
    """

    messages: Sequence[BaseMessage]
    tool_context: ButlerToolContext | None
    # Production fields
    needs_approval: bool
    retry_count: int
    last_error: str | None


class ButlerAgentBuilder:
    """Builder for creating LangGraph agents with Butler components.

    This builder:
    - Creates ButlerChatModel from MLRuntimeManager
    - Builds ButlerLangChainTool from ButlerToolSpec
    - Assembles LangGraph agent with ButlerAgentState
    - Configures Postgres checkpointing for durability
    """

    def __init__(
        self,
        runtime_manager: Any,
        tool_specs: list[ButlerToolSpec],
        tool_executor: Any | None = None,
        direct_implementations: dict[str, Any] | None = None,
        middleware_registry: ButlerMiddlewareRegistry | None = None,
        memory_service: MemoryServiceContract | None = None,
    ):
        """Initialize the agent builder.

        Args:
            runtime_manager: Butler's MLRuntimeManager
            tool_specs: List of ButlerToolSpec from domain/tools/hermes_compiler.py
            tool_executor: Butler's ToolExecutor for L2/L3 governance
            direct_implementations: Dict mapping tool name to direct implementation
            middleware_registry: Optional middleware registry for agent execution
            memory_service: Optional Butler MemoryService for 4-tier memory integration
        """
        self.runtime_manager = runtime_manager
        self.tool_specs = tool_specs
        self.tool_executor = tool_executor
        self.direct_implementations = direct_implementations or {}
        self.middleware_registry = middleware_registry
        self.memory_service = memory_service

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
        """Create a LangGraph agent with Butler components.

        Args:
            tenant_id: Tenant UUID for multi-tenant isolation
            account_id: Account UUID
            session_id: Session UUID
            trace_id: Trace UUID
            user_id: Optional user UUID
            preferred_model: Optional specific model name
            preferred_tier: Optional reasoning tier
            system_prompt: Optional system prompt

        Returns:
            Compiled LangGraph StateGraph
        """
        # Create tool context
        logger.info("agent_creating_tool_context", session_id=session_id)
        tool_context = ButlerToolContext(
            tenant_id=tenant_id,
            account_id=account_id,
            session_id=session_id,
            trace_id=trace_id,
            user_id=user_id,
        )

        # Create ButlerChatModel (already wired to MLRuntimeManager via contract)
        logger.info("agent_creating_llm", session_id=session_id)
        llm = ChatModelFactory.create(
            runtime_manager=self.runtime_manager,
            tenant_id=tenant_id,
            preferred_model=preferred_model,
            preferred_tier=preferred_tier,
        )

        # Create LangChain tools from ButlerToolSpec
        logger.info("agent_creating_tools", session_id=session_id)
        tools = ButlerToolFactory.create_tools_from_specs(
            specs=self.tool_specs,
            tool_context=tool_context,
            tool_executor=self.tool_executor,
            direct_implementations=self.direct_implementations,
        )

        # Bind tools to LLM using custom tool-aware wrapper
        logger.info("agent_binding_tools", session_id=session_id)
        try:
            llm_with_tools = llm.bind_tools(tools)
            logger.info("agent_tools_bound_successfully", session_id=session_id)
        except Exception as exc:
            import traceback
            logger.error(
                "agent_bind_tools_failed",
                session_id=session_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
                traceback=traceback.format_exc(),
            )
            raise

        # Build BM25 tool retriever for dynamic tool selection (LangChain pattern).
        # Avoids sending all 40+ tool schemas every call (saves provider TPM tokens).
        # We retrieve only the top-K most relevant tools per user query.
        from langchain_community.retrievers import BM25Retriever
        from langchain_core.documents import Document

        tool_docs = [
            Document(
                page_content=f"{getattr(t, 'name', '')} {getattr(t, 'description', '') or ''}",
                metadata={"index": idx},
            )
            for idx, t in enumerate(tools)
        ]
        tool_retriever: BM25Retriever | None = None
        if tool_docs:
            try:
                tool_retriever = BM25Retriever.from_documents(tool_docs)
                tool_retriever.k = min(8, len(tools))
                logger.info(
                    "agent_tool_retriever_ready",
                    session_id=session_id,
                    total_tools=len(tools),
                    top_k=tool_retriever.k,
                )
            except Exception as exc:
                logger.warning(
                    "agent_tool_retriever_init_failed",
                    session_id=session_id,
                    error=str(exc),
                )
                tool_retriever = None

        # Create original tool node
        logger.info("agent_creating_tool_node", session_id=session_id)
        original_tool_node = ToolNode(tools)
        logger.info("agent_tool_node_created", session_id=session_id)

        # === Production Nodes ===

        async def intake_node(
            state: ButlerAgentState,
            config: RunnableConfig,
        ) -> dict[str, Any]:
            """Intake: mark request received, initialize state."""
            logger.info("agent_intake", tenant_id=tenant_id, session_id=session_id, trace_id=trace_id)
            return {
                "needs_approval": False,
                "retry_count": 0,
                "last_error": None,
            }

        async def plan_node(
            state: ButlerAgentState,
            config: RunnableConfig,
        ) -> dict[str, Any]:
            """Plan: record planning phase for observability."""
            logger.info("agent_plan", session_id=session_id)
            return {}  # Placeholder - actual planning logic in planner service

        async def safety_node(
            state: ButlerAgentState,
            config: RunnableConfig,
        ) -> dict[str, Any]:
            """Safety: check content guard, PII, policy before model call."""
            logger.info("agent_safety", session_id=session_id)
            # Placeholder - actual safety checks via services/security/
            return {}

        async def call_model_node(
            state: ButlerAgentState,
            config: RunnableConfig,
        ) -> dict[str, Any]:
            """Call the LLM with current state."""
            import time

            messages = state["messages"]
            start_time = time.monotonic()

            # Load memory context if memory service is available
            if self.memory_service:
                try:
                    context_pack = await self.memory_service.build_context(
                        account_id=account_id,
                        query="",
                        session_id=session_id,
                    )
                    # Prepend context to messages
                    if context_pack.summary_anchor:
                        messages = [SystemMessage(content=context_pack.summary_anchor)] + list(messages)
                except Exception as exc:
                    logger.warning("memory_context_load_failed", error=str(exc))

            # Create middleware context
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

            # Execute PRE_MODEL middleware
            if self.middleware_registry:
                pre_result = await self.middleware_registry.execute(
                    middleware_context, MiddlewareOrder.PRE_MODEL
                )
                if not pre_result.should_continue:
                    return {"messages": list(state["messages"]) + messages}

                # Apply modified messages if any
                if pre_result.modified_input and "messages" in pre_result.modified_input:
                    messages = [
                        HumanMessage(content=m["content"]) if m["role"] == "human"
                        else AIMessage(content=m["content"]) if m["role"] == "ai"
                        else m
                        for m in pre_result.modified_input["messages"]
                    ]

            # Add system prompt if provided
            if system_prompt and not any(m.type == "system" for m in messages):
                messages = [SystemMessage(content=system_prompt)] + list(messages)

            # === Dynamic tool selection (LangChain BM25 retriever pattern) ===
            # Pick only the top-K tools relevant to the latest user message,
            # so we never blow past provider TPM limits with 40+ tool schemas.
            invoke_llm = llm_with_tools
            if tool_retriever is not None:
                latest_user_text = ""
                for m in reversed(messages):
                    if getattr(m, "type", None) == "human":
                        latest_user_text = str(getattr(m, "content", "") or "")
                        break
                if latest_user_text.strip():
                    try:
                        retrieved_docs = await tool_retriever.ainvoke(latest_user_text)
                        selected_indices = [
                            d.metadata["index"]
                            for d in retrieved_docs
                            if "index" in d.metadata
                        ]
                        selected_tools = [
                            tools[i] for i in selected_indices if 0 <= i < len(tools)
                        ]
                        if selected_tools:
                            invoke_llm = llm.bind_tools(selected_tools)
                            logger.info(
                                "agent_tools_selected",
                                session_id=session_id,
                                selected=[getattr(t, "name", "") for t in selected_tools],
                                total_available=len(tools),
                            )
                    except Exception as exc:
                        logger.warning(
                            "agent_tool_retrieval_failed",
                            session_id=session_id,
                            error=str(exc),
                        )

            response = await invoke_llm.ainvoke(messages, config)

            # Store conversation turn in memory if available
            if self.memory_service:
                try:
                    # Store user message
                    for msg in messages:
                        if msg.type == "human":
                            await self.memory_service.store_turn(
                                account_id=account_id,
                                session_id=session_id,
                                role="user",
                                content=msg.content,
                                tenant_id=tenant_id,
                            )
                    # Store assistant response
                    await self.memory_service.store_turn(
                        account_id=account_id,
                        session_id=session_id,
                        role="assistant",
                        content=response.content,
                        tenant_id=tenant_id,
                    )
                except Exception as exc:
                    logger.warning("memory_store_turn_failed", error=str(exc))

            # Update middleware context with response
            duration_ms = (time.monotonic() - start_time) * 1000
            middleware_context.duration_ms = duration_ms
            middleware_context.messages = [
                {"role": m.type, "content": m.content} for m in list(messages) + [response]
            ]
            middleware_context.tool_calls = (
                [{"name": tc.name, "args": tc.args} for tc in response.tool_calls]
                if hasattr(response, "tool_calls") and response.tool_calls
                else []
            )

            # Execute POST_MODEL middleware
            if self.middleware_registry:
                post_result = await self.middleware_registry.execute(
                    middleware_context, MiddlewareOrder.POST_MODEL
                )
                if not post_result.should_continue:
                    return {"messages": list(state["messages"]) + list(messages)}

            # Append the response to the messages list
            return {"messages": list(state["messages"]) + [response]}

        async def tools_node_with_middleware(
            state: ButlerAgentState,
            config: RunnableConfig,
        ) -> dict[str, Any]:
            """Execute tools with middleware."""
            import time

            start_time = time.monotonic()

            # Create middleware context
            middleware_context = ButlerMiddlewareContext(
                tenant_id=tenant_id,
                account_id=account_id,
                session_id=session_id,
                trace_id=trace_id,
                user_id=user_id,
                messages=[{"role": m.type, "content": m.content} for m in state["messages"]],
                tool_calls=[
                    {"name": tc.name, "args": tc.args}
                    for m in state["messages"]
                    if hasattr(m, "tool_calls") and m.tool_calls
                    for tc in m.tool_calls
                ],
            )

            # Execute PRE_TOOL middleware
            if self.middleware_registry:
                pre_result = await self.middleware_registry.execute(
                    middleware_context, MiddlewareOrder.PRE_TOOL
                )
                if not pre_result.should_continue:
                    return {"messages": state["messages"]}

            # Execute the actual tool node
            tool_result = await original_tool_node(state, config)

            # Update middleware context with tool results
            duration_ms = (time.monotonic() - start_time) * 1000
            middleware_context.duration_ms = duration_ms
            middleware_context.tool_results = [
                {"name": m.name, "content": m.content}
                for m in tool_result["messages"]
                if isinstance(m, ToolMessage)
            ]

            # Execute POST_TOOL middleware
            if self.middleware_registry:
                post_result = await self.middleware_registry.execute(
                    middleware_context, MiddlewareOrder.POST_TOOL
                )
                if not post_result.should_continue:
                    return {"messages": state["messages"]}

            return tool_result

        async def memory_writeback_node(
            state: ButlerAgentState,
            config: RunnableConfig,
        ) -> dict[str, Any]:
            """Memory writeback: persist conversation to memory tiers."""
            logger.info("agent_memory_writeback", session_id=session_id)
            # Already handled in call_model via memory_service.store_turn
            return {}

        # === Conditional Edges ===

        def route_after_intake(state: ButlerAgentState) -> str:
            """Route after intake: go to planning."""
            return "plan"

        def route_after_plan(state: ButlerAgentState) -> str:
            """Route after planning: go to safety check."""
            return "safety"

        def route_after_safety(state: ButlerAgentState) -> str:
            """Route after safety: go to model call."""
            return "call_model"

        def route_after_model(state: ButlerAgentState) -> str:
            """Route after model call: check for tool calls or approval needed."""
            messages = state["messages"]
            last_message = messages[-1] if messages else None

            if last_message and isinstance(last_message, AIMessage):
                if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                    return "tools"
            return "memory_writeback"

        def route_after_tools(state: ButlerAgentState) -> str:
            """Route after tools: go back to model or end on error."""
            if state["retry_count"] >= 3:
                logger.warning("agent_retry_limit_exceeded", retry_count=state["retry_count"])
                return "memory_writeback"
            return "call_model"

        # === Build the Graph ===
        logger.info("agent_building_graph", session_id=session_id)
        workflow = StateGraph(ButlerAgentState)

        # Add nodes (production sequence)
        logger.info("agent_adding_nodes", session_id=session_id)
        workflow.add_node("intake", intake_node)
        workflow.add_node("plan", plan_node)
        workflow.add_node("safety", safety_node)
        workflow.add_node("call_model", call_model_node)
        workflow.add_node("tools", tools_node_with_middleware)
        workflow.add_node("memory_writeback", memory_writeback_node)

        # Set entry point
        logger.info("agent_setting_entry_point", session_id=session_id)
        workflow.set_entry_point("intake")

        # Add conditional edges
        logger.info("agent_adding_conditional_edges", session_id=session_id)
        workflow.add_conditional_edges("intake", route_after_intake)
        workflow.add_conditional_edges("plan", route_after_plan)
        workflow.add_conditional_edges("safety", route_after_safety)
        workflow.add_conditional_edges("call_model", route_after_model)
        workflow.add_conditional_edges("tools", route_after_tools)
        workflow.add_edge("memory_writeback", END)

        # Return uncompiled workflow - compilation happens in create_agent_with_checkpointing
        logger.info("agent_workflow_built", session_id=session_id)
        return workflow

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
        """Create a LangGraph agent with Postgres checkpointing.

        Args:
            tenant_id: Tenant UUID for multi-tenant isolation
            account_id: Account UUID
            session_id: Session UUID
            trace_id: Trace UUID
            user_id: Optional user UUID
            preferred_model: Optional specific model name
            preferred_tier: Optional reasoning tier
            system_prompt: Optional system prompt
            checkpoint_config: Optional checkpoint configuration
            middleware_registry: Optional middleware registry for agent execution
            memory_service: Optional Butler MemoryService for 4-tier memory integration

        Returns:
            Compiled LangGraph StateGraph with checkpointing
        """
        # Temporarily set middleware registry if provided
        original_registry = self.middleware_registry
        self.middleware_registry = middleware_registry or self.middleware_registry

        # Temporarily set memory service if provided
        original_memory = self.memory_service
        self.memory_service = memory_service or self.memory_service

        # Create the base agent
        logger.info(
            "agent_creation_started",
            tenant_id=tenant_id,
            session_id=session_id,
        )
        workflow = self.create_agent(
            tenant_id=tenant_id,
            account_id=account_id,
            session_id=session_id,
            trace_id=trace_id,
            user_id=user_id,
            preferred_model=preferred_model,
            preferred_tier=preferred_tier,
            system_prompt=system_prompt,
        )
        logger.info(
            "agent_creation_completed",
            tenant_id=tenant_id,
            session_id=session_id,
        )

        # Restore original registry and memory
        self.middleware_registry = original_registry
        self.memory_service = original_memory

        # Add checkpointing if configured
        if checkpoint_config:
            # Use Butler's checkpointer builder for multi-tenant isolation
            from services.orchestrator.checkpointer import build_postgres_checkpointer

            connection_string = checkpoint_config.get("connection_string", "")
            checkpointer = build_postgres_checkpointer(connection_string)

            if checkpointer:
                logger.info(
                    "agent_postgres_checkpoint_enabled",
                    tenant_id=tenant_id,
                    session_id=session_id,
                )
                return workflow.compile(checkpointer=checkpointer)
            else:
                logger.warning(
                    "postgres_checkpoint_not_available",
                    message="Falling back to memory checkpointing",
                )
                from langgraph.checkpoint.memory import MemorySaver

                return workflow.compile(checkpointer=MemorySaver())
        else:
            # Use memory checkpointing by default
            from langgraph.checkpoint.memory import MemorySaver

            return workflow.compile(checkpointer=MemorySaver())


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
    """Convenience function to create a Butler LangGraph agent.

    Args:
        runtime_manager: Butler's MLRuntimeManager
        tool_specs: List of ButlerToolSpec from domain/tools/hermes_compiler.py
        tenant_id: Tenant UUID for multi-tenant isolation
        account_id: Account UUID
        session_id: Session UUID
        trace_id: Trace UUID
        tool_executor: Butler's ToolExecutor for L2/L3 governance
        direct_implementations: Dict mapping tool name to direct implementation
        user_id: Optional user UUID
        preferred_model: Optional specific model name
        preferred_tier: Optional reasoning tier
        system_prompt: Optional system prompt
        checkpoint_config: Optional checkpoint configuration
        middleware_registry: Optional middleware registry for agent execution
        memory_service: Optional Butler MemoryService for 4-tier memory integration

    Returns:
        Compiled LangGraph StateGraph
    """
    builder = ButlerAgentBuilder(
        runtime_manager=runtime_manager,
        tool_specs=tool_specs,
        tool_executor=tool_executor,
        direct_implementations=direct_implementations,
        middleware_registry=middleware_registry,
        memory_service=memory_service,
    )

    if checkpoint_config:
        return builder.create_agent_with_checkpointing(
            tenant_id=tenant_id,
            account_id=account_id,
            session_id=session_id,
            trace_id=trace_id,
            user_id=user_id,
            preferred_model=preferred_model,
            preferred_tier=preferred_tier,
            system_prompt=system_prompt,
            checkpoint_config=checkpoint_config,
            middleware_registry=middleware_registry,
            memory_service=memory_service,
        )
    else:
        return builder.create_agent(
            tenant_id=tenant_id,
            account_id=account_id,
            session_id=session_id,
            trace_id=trace_id,
            user_id=user_id,
            preferred_model=preferred_model,
            preferred_tier=preferred_tier,
            system_prompt=system_prompt,
        )
