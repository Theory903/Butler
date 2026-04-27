"""Graph agentic execution node."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from core.envelope import ButlerEnvelope, OrchestratorResult
from core.tracing import traced
from services.orchestrator.graph_state import ButlerGraphState
from services.orchestrator.nodes.common import merge_state

CoreRunner = Callable[[ButlerEnvelope], Awaitable[OrchestratorResult]]


def build_execute_agentic_node(
    core_runner: CoreRunner,
) -> Callable[[ButlerGraphState], Awaitable[ButlerGraphState]]:
    """Build the execution node for agentic execution."""

    @traced(span_name="butler.graph.node.execute_agentic")
    async def execute_agentic_node(state: ButlerGraphState) -> ButlerGraphState:
        result = await core_runner(state["envelope"])
        return merge_state(
            state,
            "execute_agentic",
            final_result=result,
            execution={"completed": True, "source": "agentic_node"},
        )

    return execute_agentic_node


@traced(span_name="butler.graph.node.execute_agentic")
async def execute_agentic_node(state: ButlerGraphState) -> ButlerGraphState:
    """Placeholder node for imports; runtime uses builder with injected core."""
    return merge_state(state, "execute_agentic", execution={"completed": False})
