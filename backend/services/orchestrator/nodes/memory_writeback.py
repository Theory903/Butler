"""Graph memory writeback node."""

from __future__ import annotations

from core.tracing import traced
from services.orchestrator.graph_state import ButlerGraphState
from services.orchestrator.nodes.common import merge_state


@traced(span_name="butler.graph.node.memory_writeback")
async def memory_writeback_node(state: ButlerGraphState) -> ButlerGraphState:
    """Record memory writeback phase for graph observability."""
    return merge_state(
        state,
        "memory_writeback",
        memory_writes=list(state.get("memory_writes", [])),
    )
