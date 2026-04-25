"""Shared helpers for Butler graph nodes."""

from __future__ import annotations

from typing import Any

from services.orchestrator.graph_state import ButlerGraphState


def append_graph_step(state: ButlerGraphState, step: str) -> ButlerGraphState:
    """Return state with an appended graph path marker."""
    path = list(state.get("graph_path", []))
    path.append(step)
    return {**state, "graph_path": path}


def merge_state(state: ButlerGraphState, step: str, **updates: Any) -> ButlerGraphState:
    """Append a path marker and merge node updates."""
    next_state = append_graph_step(state, step)
    next_state.update(updates)
    return next_state
