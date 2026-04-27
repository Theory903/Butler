"""Feedback Loop Service - Learning from tool execution.

Captures execution metrics and feeds them back into the retrieval pipeline
for continuous improvement over time.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ToolFeedback:
    """Feedback data from tool execution."""

    tool: str
    used: bool
    success: bool
    latency_ms: int
    user_satisfied: bool | None
    error_type: str | None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class FeedbackService:
    """Service for collecting and processing tool execution feedback.

    Features:
    - Captures execution metrics (success, latency, satisfaction)
    - Feeds back into reranking boosts
    - Updates tool reliability scores
    - Future retrieval bias adjustment
    """

    def __init__(
        self,
        enabled: bool = True,
        feedback_window_seconds: int = 3600,
        min_samples: int = 10,
        success_decay_rate: float = 0.1,
    ):
        """Initialize feedback service.

        Args:
            enabled: Whether feedback service is enabled.
            feedback_window_seconds: Time window for feedback aggregation.
            min_samples: Minimum samples before using feedback for reranking.
            success_decay_rate: Rate at which old success rates decay.
        """
        self._enabled = enabled
        self._feedback_window_seconds = feedback_window_seconds
        self._min_samples = min_samples
        self._success_decay_rate = success_decay_rate

        # In-memory feedback storage
        self._feedback_history: defaultdict[str, list[ToolFeedback]] = defaultdict(list)
        self._tool_success_rates: dict[str, float] = {}

    async def record(self, feedback: ToolFeedback) -> None:
        """Record tool execution feedback.

        Args:
            feedback: Tool feedback data.
        """
        if not self._enabled:
            return

        # Store feedback
        self._feedback_history[feedback.tool].append(feedback)

        # Prune old feedback
        await self._prune_old_feedback(feedback.tool)

        # Update success rate
        await self._update_success_rate(feedback.tool)

        logger.info(
            "feedback_recorded",
            tool=feedback.tool,
            success=feedback.success,
            latency_ms=feedback.latency_ms,
        )

    async def get_success_rates(self) -> dict[str, float]:
        """Get current tool success rates.

        Returns:
            Dictionary mapping tool names to success rates (0.0 to 1.0).
        """
        if not self._enabled:
            return {}

        # Update all success rates
        for tool in list(self._feedback_history.keys()):
            await self._update_success_rate(tool)

        return self._tool_success_rates.copy()

    async def get_tool_feedback_summary(
        self, tool: str
    ) -> dict[str, Any]:
        """Get feedback summary for a specific tool.

        Args:
            tool: Tool name.

        Returns:
            Summary statistics for the tool.
        """
        if not self._enabled or tool not in self._feedback_history:
            return {}

        feedback_list = self._feedback_history[tool]
        if not feedback_list:
            return {}

        successful = sum(1 for f in feedback_list if f.success)
        total = len(feedback_list)
        avg_latency = sum(f.latency_ms for f in feedback_list) / total
        satisfied = sum(1 for f in feedback_list if f.user_satisfied) / total * 100

        return {
            "tool": tool,
            "total_executions": total,
            "successful_executions": successful,
            "success_rate": successful / total if total > 0 else 0.0,
            "avg_latency_ms": avg_latency,
            "user_satisfaction_rate": satisfied,
            "error_types": self._get_error_types(feedback_list),
        }

    async def _prune_old_feedback(self, tool: str) -> None:
        """Remove feedback older than the window.

        Args:
            tool: Tool name.
        """
        now = datetime.now(UTC)
        cutoff = now.timestamp() - self._feedback_window_seconds

        self._feedback_history[tool] = [
            f for f in self._feedback_history[tool]
            if f.timestamp.timestamp() > cutoff
        ]

    async def _update_success_rate(self, tool: str) -> None:
        """Update success rate for a tool.

        Args:
            tool: Tool name.
        """
        feedback_list = self._feedback_history[tool]

        if len(feedback_list) < self._min_samples:
            # Not enough samples, use default
            self._tool_success_rates[tool] = 0.5
            return

        successful = sum(1 for f in feedback_list if f.success)
        total = len(feedback_list)
        new_rate = successful / total if total > 0 else 0.5

        # Apply decay to old rate and blend with new rate
        old_rate = self._tool_success_rates.get(tool, 0.5)
        blended_rate = (1 - self._success_decay_rate) * old_rate + self._success_decay_rate * new_rate

        self._tool_success_rates[tool] = blended_rate

    def _get_error_types(self, feedback_list: list[ToolFeedback]) -> dict[str, int]:
        """Get error type distribution.

        Args:
            feedback_list: List of feedback entries.

        Returns:
            Dictionary mapping error types to counts.
        """
        error_counts = defaultdict(int)
        for f in feedback_list:
            if f.error_type:
                error_counts[f.error_type] += 1
        return dict(error_counts)

    async def reset_tool_feedback(self, tool: str) -> None:
        """Reset feedback history for a tool.

        Args:
            tool: Tool name.
        """
        if tool in self._feedback_history:
            del self._feedback_history[tool]
        if tool in self._tool_success_rates:
            del self._tool_success_rates[tool]

        logger.info("tool_feedback_reset", tool=tool)

    async def get_all_feedback_summaries(self) -> dict[str, dict[str, Any]]:
        """Get feedback summaries for all tools.

        Returns:
            Dictionary mapping tool names to summary statistics.
        """
        summaries = {}
        for tool in self._feedback_history:
            summaries[tool] = await self.get_tool_feedback_summary(tool)
        return summaries


# Singleton instance
_feedback_service: FeedbackService | None = None


def get_feedback_service(
    enabled: bool = True,
    feedback_window_seconds: int = 3600,
    min_samples: int = 10,
    success_decay_rate: float = 0.1,
) -> FeedbackService:
    """Get the singleton feedback service instance.

    Args:
        enabled: Whether feedback service is enabled.
        feedback_window_seconds: Time window for feedback aggregation.
        min_samples: Minimum samples before using feedback for reranking.
        success_decay_rate: Rate at which old success rates decay.

    Returns:
        Feedback service instance.
    """
    global _feedback_service
    if _feedback_service is None:
        _feedback_service = FeedbackService(
            enabled=enabled,
            feedback_window_seconds=feedback_window_seconds,
            min_samples=min_samples,
            success_decay_rate=success_decay_rate,
        )
    return _feedback_service
