"""
Dashboard Service - Dashboard Aggregation and Visualization

Implements dashboard aggregation for visualization.
Supports metric aggregation, time series data, and dashboard widgets.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class WidgetType(StrEnum):
    """Dashboard widget type."""

    METRIC_CARD = "metric_card"
    LINE_CHART = "line_chart"
    BAR_CHART = "bar_chart"
    PIE_CHART = "pie_chart"
    TABLE = "table"
    ALERT_LIST = "alert_list"


@dataclass(frozen=True, slots=True)
class DashboardWidget:
    """Dashboard widget."""

    widget_id: str
    widget_type: WidgetType
    title: str
    metric_name: str
    config: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TimeSeriesData:
    """Time series data point."""

    timestamp: datetime
    value: float
    tags: dict[str, str]


@dataclass(frozen=True, slots=True)
class Dashboard:
    """Dashboard definition."""

    dashboard_id: str
    name: str
    tenant_id: str
    widgets: list[DashboardWidget]
    created_at: datetime
    updated_at: datetime


class DashboardService:
    """
    Dashboard service for visualization.

    Features:
    - Dashboard management
    - Widget configuration
    - Time series aggregation
    - Real-time updates
    """

    def __init__(self) -> None:
        """Initialize dashboard service."""
        self._dashboards: dict[str, Dashboard] = {}
        self._time_series_data: dict[str, list[TimeSeriesData]] = {}  # metric_name -> data
        self._subscribers: dict[str, list[Callable[[Dashboard], Awaitable[None]]]] = {}

    def create_dashboard(
        self,
        dashboard_id: str,
        name: str,
        tenant_id: str,
        widgets: list[DashboardWidget],
    ) -> Dashboard:
        """
        Create a dashboard.

        Args:
            dashboard_id: Dashboard identifier
            name: Dashboard name
            tenant_id: Tenant identifier
            widgets: Dashboard widgets

        Returns:
            Dashboard
        """
        now = datetime.now(UTC)

        dashboard = Dashboard(
            dashboard_id=dashboard_id,
            name=name,
            tenant_id=tenant_id,
            widgets=widgets,
            created_at=now,
            updated_at=now,
        )

        self._dashboards[dashboard_id] = dashboard

        logger.info(
            "dashboard_created",
            dashboard_id=dashboard_id,
            name=name,
            tenant_id=tenant_id,
        )

        return dashboard

    def get_dashboard(self, dashboard_id: str) -> Dashboard | None:
        """
        Get a dashboard.

        Args:
            dashboard_id: Dashboard identifier

        Returns:
            Dashboard or None
        """
        return self._dashboards.get(dashboard_id)

    def list_dashboards(
        self,
        tenant_id: str | None = None,
    ) -> list[Dashboard]:
        """
        List dashboards.

        Args:
            tenant_id: Filter by tenant

        Returns:
            List of dashboards
        """
        dashboards = list(self._dashboards.values())

        if tenant_id:
            dashboards = [d for d in dashboards if d.tenant_id == tenant_id]

        return sorted(dashboards, key=lambda d: d.created_at, reverse=True)

    def update_dashboard(
        self,
        dashboard_id: str,
        name: str | None = None,
        widgets: list[DashboardWidget] | None = None,
    ) -> Dashboard | None:
        """
        Update a dashboard.

        Args:
            dashboard_id: Dashboard identifier
            name: New name
            widgets: New widgets

        Returns:
            Updated dashboard or None
        """
        dashboard = self._dashboards.get(dashboard_id)

        if not dashboard:
            return None

        updated_dashboard = Dashboard(
            dashboard_id=dashboard.dashboard_id,
            name=name or dashboard.name,
            tenant_id=dashboard.tenant_id,
            widgets=widgets or dashboard.widgets,
            created_at=dashboard.created_at,
            updated_at=datetime.now(UTC),
        )

        self._dashboards[dashboard_id] = updated_dashboard

        logger.info(
            "dashboard_updated",
            dashboard_id=dashboard_id,
        )

        return updated_dashboard

    def delete_dashboard(self, dashboard_id: str) -> bool:
        """
        Delete a dashboard.

        Args:
            dashboard_id: Dashboard identifier

        Returns:
            True if deleted
        """
        if dashboard_id in self._dashboards:
            del self._dashboards[dashboard_id]

            logger.info(
                "dashboard_deleted",
                dashboard_id=dashboard_id,
            )

            return True
        return False

    def add_time_series_data(
        self,
        metric_name: str,
        value: float,
        tags: dict[str, str] | None = None,
    ) -> TimeSeriesData:
        """
        Add time series data point.

        Args:
            metric_name: Metric name
            value: Metric value
            tags: Optional tags

        Returns:
            Time series data point
        """
        data_point = TimeSeriesData(
            timestamp=datetime.now(UTC),
            value=value,
            tags=tags or {},
        )

        if metric_name not in self._time_series_data:
            self._time_series_data[metric_name] = []

        self._time_series_data[metric_name].append(data_point)

        # Keep only last 1000 points
        if len(self._time_series_data[metric_name]) > 1000:
            self._time_series_data[metric_name] = self._time_series_data[metric_name][-1000:]

        return data_point

    def get_time_series_data(
        self,
        metric_name: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[TimeSeriesData]:
        """
        Get time series data for a metric.

        Args:
            metric_name: Metric name
            start_time: Start time filter
            end_time: End time filter
            limit: Maximum number of points

        Returns:
            List of time series data points
        """
        data = self._time_series_data.get(metric_name, [])

        if start_time:
            data = [d for d in data if d.timestamp >= start_time]

        if end_time:
            data = [d for d in data if d.timestamp <= end_time]

        return sorted(data, key=lambda d: d.timestamp, reverse=True)[:limit]

    def aggregate_widget_data(
        self,
        widget: DashboardWidget,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Aggregate data for a widget.

        Args:
            widget: Dashboard widget
            start_time: Start time
            end_time: End time

        Returns:
            Aggregated widget data
        """
        data = self.get_time_series_data(
            widget.metric_name,
            start_time=start_time,
            end_time=end_time,
        )

        if not data:
            return {
                "widget_id": widget.widget_id,
                "widget_type": widget.widget_type,
                "title": widget.title,
                "data": [],
                "summary": {},
            }

        values = [d.value for d in data]

        summary = {
            "count": len(values),
            "sum": sum(values),
            "avg": sum(values) / len(values) if values else 0,
            "min": min(values) if values else 0,
            "max": max(values) if values else 0,
        }

        time_series = [
            {
                "timestamp": d.timestamp.isoformat(),
                "value": d.value,
                "tags": d.tags,
            }
            for d in sorted(data, key=lambda d: d.timestamp)
        ]

        return {
            "widget_id": widget.widget_id,
            "widget_type": widget.widget_type,
            "title": widget.title,
            "data": time_series,
            "summary": summary,
        }

    def get_dashboard_data(
        self,
        dashboard_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Get data for a dashboard.

        Args:
            dashboard_id: Dashboard identifier
            start_time: Start time
            end_time: End time

        Returns:
            Dashboard data
        """
        dashboard = self._dashboards.get(dashboard_id)

        if not dashboard:
            return {}

        widgets_data = {}

        for widget in dashboard.widgets:
            widgets_data[widget.widget_id] = self.aggregate_widget_data(
                widget,
                start_time=start_time,
                end_time=end_time,
            )

        return {
            "dashboard_id": dashboard.dashboard_id,
            "name": dashboard.name,
            "tenant_id": dashboard.tenant_id,
            "widgets": widgets_data,
            "updated_at": dashboard.updated_at.isoformat(),
        }

    def subscribe_to_dashboard_updates(
        self,
        dashboard_id: str,
        handler: Callable[[Dashboard], Awaitable[None]],
    ) -> str:
        """
        Subscribe to dashboard updates.

        Args:
            dashboard_id: Dashboard identifier
            handler: Update handler

        Returns:
            Subscription ID
        """
        subscription_id = f"sub-{datetime.now(UTC).timestamp()}"

        if dashboard_id not in self._subscribers:
            self._subscribers[dashboard_id] = []

        self._subscribers[dashboard_id].append(handler)

        logger.info(
            "dashboard_subscription_created",
            subscription_id=subscription_id,
            dashboard_id=dashboard_id,
        )

        return subscription_id

    async def notify_dashboard_update(self, dashboard_id: str) -> None:
        """
        Notify subscribers of dashboard update.

        Args:
            dashboard_id: Dashboard identifier
        """
        dashboard = self._dashboards.get(dashboard_id)

        if not dashboard:
            return

        for handler in self._subscribers.get(dashboard_id, []):
            try:
                await handler(dashboard)
            except Exception as e:
                logger.error(
                    "dashboard_subscriber_handler_failed",
                    dashboard_id=dashboard_id,
                    error=str(e),
                )

    def cleanup_old_data(self, retention_seconds: int = 86400) -> int:
        """
        Clean up old time series data.

        Args:
            retention_seconds: Retention period in seconds

        Returns:
            Number of data points cleaned up
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=retention_seconds)
        total_cleaned = 0

        for metric_name in list(self._time_series_data.keys()):
            initial_count = len(self._time_series_data[metric_name])
            self._time_series_data[metric_name] = [
                d for d in self._time_series_data[metric_name] if d.timestamp > cutoff
            ]
            cleaned = initial_count - len(self._time_series_data[metric_name])
            total_cleaned += cleaned

        if total_cleaned > 0:
            logger.info(
                "old_data_cleaned",
                count=total_cleaned,
            )

        return total_cleaned

    def get_dashboard_stats(self) -> dict[str, Any]:
        """
        Get dashboard statistics.

        Returns:
            Dashboard statistics
        """
        total_dashboards = len(self._dashboards)
        total_widgets = sum(len(d.widgets) for d in self._dashboards.values())

        widget_type_counts: dict[str, int] = {}
        for dashboard in self._dashboards.values():
            for widget in dashboard.widgets:
                widget_type_counts[widget.widget_type] = (
                    widget_type_counts.get(widget.widget_type, 0) + 1
                )

        return {
            "total_dashboards": total_dashboards,
            "total_widgets": total_widgets,
            "widget_type_breakdown": widget_type_counts,
            "metrics_tracked": len(self._time_series_data),
        }
