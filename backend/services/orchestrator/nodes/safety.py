"""Graph safety node."""

from __future__ import annotations

from core.tracing import traced
from services.orchestrator.graph_state import ButlerGraphState
from services.orchestrator.nodes.common import merge_state


@traced(span_name="butler.graph.node.safety")
async def safety_node(state: ButlerGraphState) -> ButlerGraphState:
    """Record safety phase placeholder for graph observability."""
    return merge_state(
        state,
        "safety",
        safety={"checked": True, "source": "legacy_core"},
    )
