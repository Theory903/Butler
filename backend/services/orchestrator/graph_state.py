"""Checkpoint-safe state for Butler graph execution."""

from __future__ import annotations

from typing import Any, TypedDict

from core.envelope import ButlerEnvelope, ButlerEvent, OrchestratorResult, ToolCall


class ButlerGraphState(TypedDict, total=False):
    """Canonical state shape for LangGraph checkpointing.

    This state is fully serializable and can be persisted to PostgresSaver
    for durable execution and resume-after-interrupt workflows.
    """

    # Request input
    envelope: ButlerEnvelope

    # Execution
    messages: list[dict[str, Any]]  # LangChain message format
    tool_calls: list[ToolCall]
    tool_results: list[dict[str, Any]]

    # Context
    memory_context: dict[str, Any]
    search_results: dict[str, Any] | None  # EvidencePack or None

    # Control
    graph_path: list[str]
    events: list[ButlerEvent]
    requires_approval: bool
    approvals: list[dict[str, Any]]

    # Output
    final_result: OrchestratorResult | None
    response: str | None

    # Checkpoint metadata for interrupt/resume
    _interrupt_resume: dict[str, Any] | None
