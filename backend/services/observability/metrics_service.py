"""
Metrics Collection Service - Prometheus Integration

Collects and exposes application metrics for monitoring.
Implements Prometheus-compatible metrics with multi-tenant support.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class MetricType(StrEnum):
    """Metric types."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass(frozen=True, slots=True)
class Metric:
    """Metric definition."""

    name: str
    metric_type: MetricType
    value: float
    labels: dict[str, str]
    timestamp: datetime
    help_text: str | None = None


class MetricsService:
    """
    Metrics collection service.

    Features:
    - Prometheus-compatible metrics
    - Multi-tenant label support
    - In-memory storage
    - Counter, Gauge, Histogram, Summary support
    """

    def __init__(self) -> None:
        """Initialize metrics service."""
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}
        self._summaries: dict[str, list[float]] = {}
        self._metric_metadata: dict[str, dict[str, Any]] = {}

    def _make_metric_key(self, name: str, labels: dict[str, str]) -> str:
        """Generate unique key for metric with labels."""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def register_metric(
        self,
        name: str,
        metric_type: MetricType,
        help_text: str | None = None,
    ) -> None:
        """
        Register a metric definition.

        Args:
            name: Metric name
            metric_type: Type of metric
            help_text: Metric description
        """
        self._metric_metadata[name] = {
            "type": metric_type,
            "help": help_text,
        }

        # Initialize storage
        if metric_type == MetricType.COUNTER:
            self._counters[name] = 0.0
        elif metric_type == MetricType.GAUGE:
            self._gauges[name] = 0.0
        elif metric_type == MetricType.HISTOGRAM:
            self._histograms[name] = []
        elif metric_type == MetricType.SUMMARY:
            self._summaries[name] = []

        logger.debug(
            "metric_registered",
            name=name,
            metric_type=metric_type,
        )

    def increment(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Increment a counter metric.

        Args:
            name: Metric name
            value: Increment value
            labels: Metric labels
        """
        key = self._make_metric_key(name, labels or {})
        self._counters[key] = self._counters.get(key, 0.0) + value

    def decrement(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Decrement a counter metric.

        Args:
            name: Metric name
            value: Decrement value
            labels: Metric labels
        """
        key = self._make_metric_key(name, labels or {})
        self._counters[key] = self._counters.get(key, 0.0) - value

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Set a gauge metric value.

        Args:
            name: Metric name
            value: Gauge value
            labels: Metric labels
        """
        key = self._make_metric_key(name, labels or {})
        self._gauges[key] = value

    def observe(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Observe a value for histogram or summary.

        Args:
            name: Metric name
            value: Observed value
            labels: Metric labels
        """
        key = self._make_metric_key(name, labels or {})

        metric_type = self._metric_metadata.get(name, {}).get("type")
        if metric_type == MetricType.HISTOGRAM:
            if key not in self._histograms:
                self._histograms[key] = []
            self._histograms[key].append(value)
        elif metric_type == MetricType.SUMMARY:
            if key not in self._summaries:
                self._summaries[key] = []
            self._summaries[key].append(value)

    def get_metric(
        self,
        name: str,
        labels: dict[str, str] | None = None,
    ) -> float | None:
        """
        Get current metric value.

        Args:
            name: Metric name
            labels: Metric labels

        Returns:
            Metric value or None
        """
        key = self._make_metric_key(name, labels or {})

        metric_type = self._metric_metadata.get(name, {}).get("type")
        if metric_type == MetricType.COUNTER:
            return self._counters.get(key)
        if metric_type == MetricType.GAUGE:
            return self._gauges.get(key)
        if metric_type == MetricType.HISTOGRAM:
            values = self._histograms.get(key, [])
            return sum(values) / len(values) if values else 0.0
        if metric_type == MetricType.SUMMARY:
            values = self._summaries.get(key, [])
            return sum(values) / len(values) if values else 0.0

        return None

    def reset_metric(
        self,
        name: str,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Reset a metric to zero.

        Args:
            name: Metric name
            labels: Metric labels
        """
        key = self._make_metric_key(name, labels or {})

        metric_type = self._metric_metadata.get(name, {}).get("type")
        if metric_type == MetricType.COUNTER:
            self._counters[key] = 0.0
        elif metric_type == MetricType.GAUGE:
            self._gauges[key] = 0.0
        elif metric_type == MetricType.HISTOGRAM:
            self._histograms[key] = []
        elif metric_type == MetricType.SUMMARY:
            self._summaries[key] = []

    def export_prometheus(self) -> str:
        """
        Export metrics in Prometheus format.

        Returns:
            Prometheus-format metrics
        """
        lines = []

        # Export metadata
        for name, metadata in self._metric_metadata.items():
            if metadata.get("help"):
                lines.append(f"# HELP {name} {metadata['help']}")
            lines.append(f"# TYPE {name} {metadata['type']}")

        # Export counters
        for key, value in self._counters.items():
            lines.append(f"{key} {value}")

        # Export gauges
        for key, value in self._gauges.items():
            lines.append(f"{key} {value}")

        # Export histograms
        for key, values in self._histograms.items():
            if values:
                lines.append(f"{key}_count {len(values)}")
                lines.append(f"{key}_sum {sum(values)}")
                lines.append(f'{key}_bucket{{le="+Inf"}} {len(values)}')

        # Export summaries
        for key, values in self._summaries.items():
            if values:
                lines.append(f"{key}_count {len(values)}")
                lines.append(f"{key}_sum {sum(values)}")

        return "\n".join(lines)

    def get_all_metrics(self) -> list[Metric]:
        """
        Get all metrics as Metric objects.

        Returns:
            List of all metrics
        """
        metrics = []
        timestamp = datetime.now(UTC)

        # Counters
        for key, value in self._counters.items():
            name = key.split("{")[0]
            labels = self._parse_labels(key)
            metrics.append(
                Metric(
                    name=name,
                    metric_type=MetricType.COUNTER,
                    value=value,
                    labels=labels,
                    timestamp=timestamp,
                )
            )

        # Gauges
        for key, value in self._gauges.items():
            name = key.split("{")[0]
            labels = self._parse_labels(key)
            metrics.append(
                Metric(
                    name=name,
                    metric_type=MetricType.GAUGE,
                    value=value,
                    labels=labels,
                    timestamp=timestamp,
                )
            )

        # Histograms
        for key, values in self._histograms.items():
            name = key.split("{")[0]
            labels = self._parse_labels(key)
            if values:
                metrics.append(
                    Metric(
                        name=f"{name}_count",
                        metric_type=MetricType.COUNTER,
                        value=len(values),
                        labels=labels,
                        timestamp=timestamp,
                    )
                )
                metrics.append(
                    Metric(
                        name=f"{name}_sum",
                        metric_type=MetricType.COUNTER,
                        value=sum(values),
                        labels=labels,
                        timestamp=timestamp,
                    )
                )

        # Summaries
        for key, values in self._summaries.items():
            name = key.split("{")[0]
            labels = self._parse_labels(key)
            if values:
                metrics.append(
                    Metric(
                        name=f"{name}_count",
                        metric_type=MetricType.COUNTER,
                        value=len(values),
                        labels=labels,
                        timestamp=timestamp,
                    )
                )
                metrics.append(
                    Metric(
                        name=f"{name}_sum",
                        metric_type=MetricType.COUNTER,
                        value=sum(values),
                        labels=labels,
                        timestamp=timestamp,
                    )
                )

        return metrics

    def _parse_labels(self, key: str) -> dict[str, str]:
        """Parse labels from metric key."""
        if "{" not in key or "}" not in key:
            return {}

        start = key.index("{") + 1
        end = key.index("}")
        label_str = key[start:end]

        labels = {}
        for pair in label_str.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                labels[k.strip()] = v.strip()

        return labels

    def record_latency(
        self,
        name: str,
        duration_ms: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Record latency metric.

        Args:
            name: Metric name
            duration_ms: Duration in milliseconds
            labels: Metric labels
        """
        self.observe(name, duration_ms, labels)

    def record_error(
        self,
        name: str,
        error_type: str,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Record error metric.

        Args:
            name: Metric name
            error_type: Type of error
            labels: Metric labels
        """
        if labels is None:
            labels = {}
        labels["error_type"] = error_type
        self.increment(name, labels=labels)

    def record_tenant_metric(
        self,
        name: str,
        value: float,
        tenant_id: str,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Record metric with tenant label.

        Args:
            name: Metric name
            value: Metric value
            tenant_id: Tenant UUID
            labels: Additional metric labels
        """
        if labels is None:
            labels = {}
        labels["tenant_id"] = tenant_id
        self.observe(name, value, labels)
