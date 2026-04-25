"""
Real-Time Analytics Pipeline

Implements real-time analytics pipeline for metrics aggregation.
Supports streaming data processing, windowed aggregations, and real-time insights.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class AggregationType(StrEnum):
    """Aggregation type."""

    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    COUNT = "count"
    PERCENTILE = "percentile"


class WindowType(StrEnum):
    """Window type."""

    TUMBLING = "tumbling"
    SLIDING = "sliding"
    SESSION = "session"


@dataclass(frozen=True, slots=True)
class MetricEvent:
    """Metric event."""

    event_id: str
    metric_name: str
    value: float
    tags: dict[str, str]
    timestamp: datetime
    tenant_id: str


@dataclass(frozen=True, slots=True)
class AggregationWindow:
    """Aggregation window."""

    window_id: str
    metric_name: str
    aggregation_type: AggregationType
    window_type: WindowType
    window_size_seconds: int
    start_time: datetime
    end_time: datetime
    value: float


class AnalyticsPipeline:
    """
    Real-time analytics pipeline.

    Features:
    - Streaming data ingestion
    - Windowed aggregations
    - Real-time metrics
    - Tenant isolation
    """

    def __init__(self) -> None:
        """Initialize analytics pipeline."""
        self._events: list[MetricEvent] = []
        self._windows: dict[str, list[AggregationWindow]] = {}  # metric_name -> windows
        self._aggregations: dict[str, Any] = defaultdict(list)  # metric_name -> values
        self._subscribers: dict[str, list[Callable[[MetricEvent], Awaitable[None]]]] = {}

    async def ingest_event(
        self,
        event: MetricEvent,
    ) -> None:
        """
        Ingest a metric event.

        Args:
            event: Metric event
        """
        self._events.append(event)
        self._aggregations[event.metric_name].append(event.value)

        # Notify subscribers
        await self._notify_subscribers(event)

        logger.debug(
            "event_ingested",
            metric_name=event.metric_name,
            value=event.value,
        )

    async def create_aggregation(
        self,
        metric_name: str,
        aggregation_type: AggregationType,
        window_type: WindowType,
        window_size_seconds: int,
    ) -> AggregationWindow:
        """
        Create an aggregation window.

        Args:
            metric_name: Metric name
            aggregation_type: Aggregation type
            window_type: Window type
            window_size_seconds: Window size in seconds

        Returns:
            Aggregation window
        """
        now = datetime.now(UTC)

        window = AggregationWindow(
            window_id=f"{metric_name}-{now.timestamp()}",
            metric_name=metric_name,
            aggregation_type=aggregation_type,
            window_type=window_type,
            window_size_seconds=window_size_seconds,
            start_time=now,
            end_time=now + timedelta(seconds=window_size_seconds),
            value=0.0,
        )

        if metric_name not in self._windows:
            self._windows[metric_name] = []

        self._windows[metric_name].append(window)

        logger.info(
            "aggregation_created",
            metric_name=metric_name,
            aggregation_type=aggregation_type,
            window_size_seconds=window_size_seconds,
        )

        return window

    async def compute_aggregation(
        self,
        metric_name: str,
        aggregation_type: AggregationType,
    ) -> float | None:
        """
        Compute aggregation for a metric.

        Args:
            metric_name: Metric name
            aggregation_type: Aggregation type

        Returns:
            Aggregated value or None
        """
        values = self._aggregations.get(metric_name, [])

        if not values:
            return None

        if aggregation_type == AggregationType.SUM:
            return sum(values)
        if aggregation_type == AggregationType.AVG:
            return sum(values) / len(values)
        if aggregation_type == AggregationType.MIN:
            return min(values)
        if aggregation_type == AggregationType.MAX:
            return max(values)
        if aggregation_type == AggregationType.COUNT:
            return len(values)
        if aggregation_type == AggregationType.PERCENTILE:
            # Compute 95th percentile
            sorted_values = sorted(values)
            index = int(len(sorted_values) * 0.95)
            return sorted_values[index] if sorted_values else 0.0

        return None

    async def get_metric_stats(
        self,
        metric_name: str,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Get statistics for a metric.

        Args:
            metric_name: Metric name
            tenant_id: Optional tenant filter

        Returns:
            Metric statistics
        """
        events = [e for e in self._events if e.metric_name == metric_name]

        if tenant_id:
            events = [e for e in events if e.tenant_id == tenant_id]

        if not events:
            return {}

        values = [e.value for e in events]

        return {
            "metric_name": metric_name,
            "count": len(values),
            "sum": sum(values),
            "avg": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "first_event": min(e.timestamp for e in events),
            "last_event": max(e.timestamp for e in events),
        }

    async def subscribe_to_events(
        self,
        metric_name: str | None = None,
        handler: Callable[[MetricEvent], Awaitable[None]] | None = None,
    ) -> str:
        """
        Subscribe to metric events.

        Args:
            metric_name: Metric name to filter (None for all)
            handler: Event handler

        Returns:
            Subscription ID
        """
        subscription_id = f"sub-{datetime.now(UTC).timestamp()}"
        subscription_key = metric_name or "*"

        if subscription_key not in self._subscribers:
            self._subscribers[subscription_key] = []

        if handler:
            self._subscribers[subscription_key].append(handler)

        logger.info(
            "analytics_subscription_created",
            subscription_id=subscription_id,
            metric_name=metric_name or "*",
        )

        return subscription_id

    async def _notify_subscribers(self, event: MetricEvent) -> None:
        """Notify subscribers of an event."""
        # Notify wildcard subscribers
        for handler in self._subscribers.get("*", []):
            try:
                await handler(event)
            except Exception as e:
                logger.error(
                    "analytics_subscriber_handler_failed",
                    metric_name=event.metric_name,
                    error=str(e),
                )

        # Notify metric-specific subscribers
        for handler in self._subscribers.get(event.metric_name, []):
            try:
                await handler(event)
            except Exception as e:
                logger.error(
                    "analytics_subscriber_handler_failed",
                    metric_name=event.metric_name,
                    error=str(e),
                )

    def cleanup_old_events(self, retention_seconds: int = 3600) -> int:
        """
        Clean up old events.

        Args:
            retention_seconds: Retention period in seconds

        Returns:
            Number of events cleaned up
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=retention_seconds)
        initial_count = len(self._events)

        self._events = [e for e in self._events if e.timestamp > cutoff]

        cleaned = initial_count - len(self._events)

        if cleaned > 0:
            logger.info(
                "old_events_cleaned",
                count=cleaned,
            )

        return cleaned

    def get_pipeline_stats(self) -> dict[str, Any]:
        """
        Get pipeline statistics.

        Returns:
            Pipeline statistics
        """
        total_events = len(self._events)
        total_windows = sum(len(windows) for windows in self._windows.values())

        metric_counts: dict[str, int] = {}
        for event in self._events:
            metric_counts[event.metric_name] = metric_counts.get(event.metric_name, 0) + 1

        return {
            "total_events": total_events,
            "total_windows": total_windows,
            "metric_breakdown": metric_counts,
            "total_subscriptions": len(self._subscribers),
        }
