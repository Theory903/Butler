"""Graph context node."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from core.envelope import ButlerEnvelope
from core.tracing import traced
from services.orchestrator.graph_state import ButlerGraphState
from services.orchestrator.nodes.common import merge_state

ContextProvider = Callable[[ButlerEnvelope], Awaitable[Any]]


@traced(span_name="butler.graph.node.context")
async def context_node(state: ButlerGraphState) -> ButlerGraphState:
    """Record context phase placeholder for graph observability."""
    return merge_state(
        state,
        "context",
        context={"retrieved": True, "source": "legacy_core"},
    )


def build_context_node(
    context_provider: ContextProvider | None,
) -> Callable[[ButlerGraphState], Awaitable[ButlerGraphState]]:
    """Build a graph context node using the existing memory service path."""

    @traced(span_name="butler.graph.node.context")
    async def memory_context_node(state: ButlerGraphState) -> ButlerGraphState:
        if context_provider is None:
            return await context_node(state)

        envelope = state["envelope"]
        try:
            context_pack = await context_provider(envelope)
        except Exception as exc:
            return merge_state(
                state,
                "context",
                context={
                    "retrieved": False,
                    "source": "memory_service",
                    "error": str(exc),
                },
            )

        return merge_state(
            state,
            "context",
            context={
                "retrieved": True,
                "source": "memory_service",
                "history_count": len(getattr(context_pack, "session_history", []) or []),
                "memory_count": len(getattr(context_pack, "relevant_memories", []) or []),
                "has_summary_anchor": bool(getattr(context_pack, "summary_anchor", None)),
            },
        )

    return memory_context_node
