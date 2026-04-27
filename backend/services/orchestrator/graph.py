"""Butler orchestrator graph compiler."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from core.envelope import ButlerEnvelope, OrchestratorResult
from services.orchestrator.graph_state import ButlerGraphState
from services.orchestrator.nodes import (
    approval_interrupt_node,
    intake_node,
    memory_writeback_node,
    plan_node,
    render_node,
    safety_node,
)
from services.orchestrator.nodes.context import ContextProvider, build_context_node
from services.orchestrator.nodes.execute_agentic import (
    build_execute_agentic_node,
)
from services.orchestrator.nodes.execute_deterministic import (
    build_execute_deterministic_node,
)

try:  # Optional dependency. Butler still boots without LangGraph installed.
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover - exercised when optional dep is absent.
    END = START = None
    StateGraph = None


CoreRunner = Callable[[ButlerEnvelope], Awaitable[OrchestratorResult]]


GRAPH_NODE_ORDER = (
    "intake",
    "safety",
    "context",
    "plan",
    "execute",
    "approval_interrupt",
    "memory_writeback",
    "render",
)


def langgraph_available() -> bool:
    """Return whether LangGraph graph primitives are importable."""
    return StateGraph is not None and START is not None and END is not None


def compile_butler_graph(
    *,
    core_runner: CoreRunner,
    context_provider: ContextProvider | None = None,
    checkpointer: object | None = None,
) -> object:
    """Compile the Butler graph with named production phases."""
    if not langgraph_available():
        raise RuntimeError("LangGraph runtime is unavailable")

    graph = StateGraph(ButlerGraphState)
    graph.add_node("intake", intake_node)
    graph.add_node("safety", safety_node)
    graph.add_node("context", build_context_node(context_provider))
    graph.add_node("plan", plan_node)
    graph.add_node("execute_deterministic", build_execute_deterministic_node(core_runner))
    graph.add_node("execute_agentic", build_execute_agentic_node(core_runner))
    graph.add_node("approval_interrupt", approval_interrupt_node)
    graph.add_node("memory_writeback", memory_writeback_node)
    graph.add_node("render", render_node)

    # Linear flow with conditional execution branch
    graph.add_edge(START, "intake")
    graph.add_edge("intake", "safety")
    graph.add_edge("safety", "context")
    graph.add_edge("context", "plan")

    # Conditional: plan → deterministic or agentic
    def route_execution(state: ButlerGraphState) -> str:
        """Route to deterministic or agentic execution based on plan mode."""
        plan = state.get("plan", {})
        mode = plan.get("mode", "deterministic")
        return "execute_deterministic" if mode == "deterministic" else "execute_agentic"

    graph.add_conditional_edges("plan", route_execution)

    # For now, only deterministic execution is fully implemented
    # Agentic execution node will be added in Phase 2
    graph.add_edge("execute_deterministic", "approval_interrupt")
    graph.add_edge("execute_agentic", "approval_interrupt")
    graph.add_edge("approval_interrupt", "memory_writeback")
    graph.add_edge("memory_writeback", "render")
    graph.add_edge("render", END)

    if checkpointer is None:
        return graph.compile()
    return graph.compile(checkpointer=checkpointer)


async def run_fallback_graph(
    *,
    envelope: ButlerEnvelope,
    core_runner: CoreRunner,
    context_provider: ContextProvider | None = None,
) -> ButlerGraphState:
    """Run the same named phases without LangGraph installed."""
    state: ButlerGraphState = {"envelope": envelope, "graph_path": []}
    state = await intake_node(state)
    state = await safety_node(state)
    state = await build_context_node(context_provider)(state)
    state = await plan_node(state)

    # Route based on plan mode
    plan = state.get("plan", {})
    mode = plan.get("mode", "deterministic")
    if mode == "deterministic":
        state = await build_execute_deterministic_node(core_runner)(state)
    else:
        state = await build_execute_agentic_node(core_runner)(state)

    state = await approval_interrupt_node(state)
    state = await memory_writeback_node(state)
    return await render_node(state)
