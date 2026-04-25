"""Graph planning node."""

from __future__ import annotations

from core.tracing import traced
from services.orchestrator.graph_state import ButlerGraphState
from services.orchestrator.nodes.common import merge_state


@traced(span_name="butler.graph.node.plan")
async def plan_node(state: ButlerGraphState) -> ButlerGraphState:
    """Record planning phase placeholder for graph observability."""
    return merge_state(
        state,
        "plan",
        plan={"created": True, "source": "legacy_core"},
    )
