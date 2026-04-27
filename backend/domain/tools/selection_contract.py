"""Tool Selection Contract - Domain object for tool selection decisions.

This contract enforces accountability by requiring justifications for tool
selection decisions. ToolScope proposes, LLM disposes—with explicit reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.tools.specs import ButlerToolSpec


@dataclass(frozen=True, slots=True)
class ToolSelection:
    """A selected tool with justification."""

    name: str
    reason: str
    confidence: float
    score_components: dict[str, float] = field(default_factory=dict)
    spec: ButlerToolSpec | None = None


@dataclass(frozen=True, slots=True)
class ToolRejection:
    """A rejected tool with rejection reason and stage."""

    name: str
    reason: str
    stage: str  # "policy", "cutoff", "rerank"
    score: float | None = None
    spec: ButlerToolSpec | None = None


@dataclass(frozen=True, slots=True)
class ToolSelectionContract:
    """Contract for tool selection with explicit accountability.

    This contract forces the LLM to justify choices and prevents blind execution.
    It provides full traceability of why tools were selected or rejected.
    """

    selected_tools: list[ToolSelection]
    rejected_tools: list[ToolRejection]
    retrieval_metadata: dict[str, Any] = field(default_factory=dict)
    intent_context: dict[str, Any] | None = None

    def get_selected_names(self) -> list[str]:
        """Get list of selected tool names."""
        return [tool.name for tool in self.selected_tools]

    def get_rejected_names(self) -> list[str]:
        """Get list of rejected tool names."""
        return [tool.name for tool in self.rejected_tools]

    def get_tool_count(self) -> int:
        """Get total number of selected tools."""
        return len(self.selected_tools)

    def has_tool(self, name: str) -> bool:
        """Check if a tool is selected."""
        return name in self.get_selected_names()

    def to_dict(self) -> dict[str, Any]:
        """Convert contract to dictionary for serialization."""
        return {
            "selected_tools": [
                {
                    "name": tool.name,
                    "reason": tool.reason,
                    "confidence": tool.confidence,
                    "score_components": tool.score_components,
                }
                for tool in self.selected_tools
            ],
            "rejected_tools": [
                {
                    "name": tool.name,
                    "reason": tool.reason,
                    "stage": tool.stage,
                    "score": tool.score,
                }
                for tool in self.rejected_tools
            ],
            "retrieval_metadata": self.retrieval_metadata,
            "intent_context": self.intent_context,
            "selected_count": self.get_tool_count(),
        }
