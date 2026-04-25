"""Graph agentic execution node."""

from __future__ import annotations

from services.orchestrator.graph_state import ButlerGraphState
from services.orchestrator.nodes.common import merge_state


async def execute_agentic_node(state: ButlerGraphState) -> ButlerGraphState:
    """Placeholder for future agentic-native graph execution."""
    return merge_state(state, "execute_agentic")
