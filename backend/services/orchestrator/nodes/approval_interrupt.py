"""Graph approval interrupt node — uses LangGraph interrupt for approval pause."""

from __future__ import annotations

from core.tracing import traced
from services.orchestrator.graph_state import ButlerGraphState
from services.orchestrator.nodes.common import merge_state

try:
    from langgraph.types import interrupt
except ImportError:
    interrupt = None  # Fallback when LangGraph unavailable


@traced(span_name="butler.graph.node.approval_interrupt")
async def approval_interrupt_node(state: ButlerGraphState) -> ButlerGraphState:
    """Check for pending approvals and use LangGraph interrupt if needed."""
    approvals = list(state.get("approvals", []))
    final_result = state.get("final_result")

    if final_result is not None and final_result.requires_approval:
        approvals.append(
            {
                "approval_id": final_result.approval_id,
                "workflow_id": final_result.workflow_id,
            }
        )

        if interrupt is not None:
            interrupted_value = interrupt(
                {
                    "type": "approval_required",
                    "approval_id": final_result.approval_id,
                    "description": final_result.content,
                }
            )
            state["_interrupt_resume"] = interrupted_value

    return merge_state(state, "approval_interrupt", approvals=approvals)
