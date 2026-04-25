"""Graph render node."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from core.envelope import ButlerEvent, EventType
from core.tracing import traced
from services.orchestrator.graph_state import ButlerGraphState


@traced(span_name="butler.graph.node.render")
async def render_node(state: ButlerGraphState) -> ButlerGraphState:
    """Finalize graph output and attach graph metadata to the result."""
    final_result = state.get("final_result")

    graph_path = [*state.get("graph_path", []), "render"]

    if final_result is not None:
        graph_event = ButlerEvent(
            type=EventType.RESPONSE_RENDERED,
            payload={
                "graph_path": graph_path,
                "node_count": len(graph_path),
            },
            trace_id=str(uuid4()),
            timestamp=datetime.now(UTC),
        )
        existing_events = list(final_result.events) if final_result.events else []
        final_result.events = [*existing_events, graph_event]

        final_result.metadata = {
            **final_result.metadata,
            "graph_runtime": True,
            "graph_path": graph_path,
            "graph_context": state.get("context", {}),
        }

    return {**state, "graph_path": graph_path, "final_result": final_result}
