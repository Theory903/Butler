"""
Model Monitoring - Model Monitoring and Drift Detection

Implements model monitoring and drift detection.
Supports performance tracking, drift detection, and alerting.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class DriftType(StrEnum):
    """Drift type."""

    DATA_DRIFT = "data_drift"
    CONCEPT_DRIFT = "concept_drift"
    PERFORMANCE_DRIFT = "performance_drift"


@dataclass(frozen=True, slots=True)
class ModelMetrics:
    """Model metrics."""

    metric_id: str
    model_id: str
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    latency_ms: float
    throughput: float
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class DriftAlert:
    """Drift alert."""

    alert_id: str
    model_id: str
    drift_type: DriftType
    severity: str
    drift_score: float
    threshold: float
    detected_at: datetime
    description: str


class ModelMonitor:
    """
    Model monitoring and drift detection service.

    Features:
    - Performance tracking
    - Drift detection
    - Alerting
    - Baseline comparison
    """

    def __init__(self) -> None:
        """Initialize model monitor."""
        self._metrics: dict[str, list[ModelMetrics]] = {}  # model_id -> metrics
        self._baselines: dict[str, ModelMetrics] = {}  # model_id -> baseline
        self._alerts: list[DriftAlert] = []
        self._drift_threshold: float = 0.1
        self._monitoring_task: asyncio.Task | None = None
        self._alert_callback: Callable[[DriftAlert], Awaitable[bool]] | None = None

    def set_alert_callback(
        self,
        callback: Callable[[DriftAlert], Awaitable[bool]],
    ) -> None:
        """
        Set alert callback.

        Args:
            callback: Async function to handle alerts
        """
        self._alert_callback = callback

    def set_drift_threshold(
        self,
        threshold: float,
    ) -> None:
        """
        Set drift detection threshold.

        Args:
            threshold: Drift threshold (0.0 to 1.0)
        """
        self._drift_threshold = threshold

    async def record_metrics(
        self,
        model_id: str,
        accuracy: float,
        precision: float,
        recall: float,
        f1_score: float,
        latency_ms: float,
        throughput: float,
    ) -> ModelMetrics:
        """
        Record model metrics.

        Args:
            model_id: Model identifier
            accuracy: Accuracy
            precision: Precision
            recall: Recall
            f1_score: F1 score
            latency_ms: Latency in milliseconds
            throughput: Throughput

        Returns:
            Model metrics
        """
        metric_id = f"metric-{datetime.now(UTC).timestamp()}"

        metrics = ModelMetrics(
            metric_id=metric_id,
            model_id=model_id,
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=f1_score,
            latency_ms=latency_ms,
            throughput=throughput,
            recorded_at=datetime.now(UTC),
        )

        if model_id not in self._metrics:
            self._metrics[model_id] = []

        self._metrics[model_id].append(metrics)

        # Keep only last 1000 metrics
        if len(self._metrics[model_id]) > 1000:
            self._metrics[model_id] = self._metrics[model_id][-1000:]

        logger.debug(
            "metrics_recorded",
            metric_id=metric_id,
            model_id=model_id,
        )

        return metrics

    def set_baseline(
        self,
        model_id: str,
        accuracy: float,
        precision: float,
        recall: float,
        f1_score: float,
        latency_ms: float,
        throughput: float,
    ) -> ModelMetrics:
        """
        Set baseline metrics for a model.

        Args:
            model_id: Model identifier
            accuracy: Accuracy
            precision: Precision
            recall: Recall
            f1_score: F1 score
            latency_ms: Latency in milliseconds
            throughput: Throughput

        Returns:
            Baseline metrics
        """
        baseline = ModelMetrics(
            metric_id=f"baseline-{model_id}",
            model_id=model_id,
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=f1_score,
            latency_ms=latency_ms,
            throughput=throughput,
            recorded_at=datetime.now(UTC),
        )

        self._baselines[model_id] = baseline

        logger.info(
            "baseline_set",
            model_id=model_id,
        )

        return baseline

    async def detect_drift(
        self,
        model_id: str,
    ) -> list[DriftAlert]:
        """
        Detect drift for a model.

        Args:
            model_id: Model identifier

        Returns:
            List of drift alerts
        """
        alerts = []

        baseline = self._baselines.get(model_id)

        if not baseline:
            return alerts

        metrics = self._metrics.get(model_id, [])

        if not metrics:
            return alerts

        # Calculate current average metrics
        recent_metrics = metrics[-100:]  # Last 100 metrics

        if not recent_metrics:
            return alerts

        avg_accuracy = sum(m.accuracy for m in recent_metrics) / len(recent_metrics)
        avg_latency = sum(m.latency_ms for m in recent_metrics) / len(recent_metrics)

        # Detect performance drift
        accuracy_drift = abs(avg_accuracy - baseline.accuracy)
        latency_drift = abs(avg_latency - baseline.latency_ms) / baseline.latency_ms

        if accuracy_drift > self._drift_threshold:
            alert = DriftAlert(
                alert_id=f"alert-{datetime.now(UTC).timestamp()}",
                model_id=model_id,
                drift_type=DriftType.PERFORMANCE_DRIFT,
                severity="high" if accuracy_drift > self._drift_threshold * 2 else "medium",
                drift_score=accuracy_drift,
                threshold=self._drift_threshold,
                detected_at=datetime.now(UTC),
                description=f"Accuracy drift detected: {accuracy_drift:.3f} > {self._drift_threshold}",
            )

            alerts.append(alert)
            self._alerts.append(alert)

        if latency_drift > self._drift_threshold:
            alert = DriftAlert(
                alert_id=f"alert-{datetime.now(UTC).timestamp()}",
                model_id=model_id,
                drift_type=DriftType.PERFORMANCE_DRIFT,
                severity="high" if latency_drift > self._drift_threshold * 2 else "medium",
                drift_score=latency_drift,
                threshold=self._drift_threshold,
                detected_at=datetime.now(UTC),
                description=f"Latency drift detected: {latency_drift:.3f} > {self._drift_threshold}",
            )

            alerts.append(alert)
            self._alerts.append(alert)

        # Trigger alert callback
        if alerts and self._alert_callback:
            for alert in alerts:
                try:
                    await self._alert_callback(alert)
                except Exception as e:
                    logger.error(
                        "alert_callback_failed",
                        alert_id=alert.alert_id,
                        error=str(e),
                    )

        return alerts

    async def start_monitoring(
        self,
        interval_seconds: int = 60,
    ) -> None:
        """
        Start continuous monitoring.

        Args:
            interval_seconds: Check interval
        """
        self._monitoring_task = asyncio.create_task(self._monitoring_loop(interval_seconds))

    async def _monitoring_loop(
        self,
        interval_seconds: int,
    ) -> None:
        """
        Monitoring loop.

        Args:
            interval_seconds: Check interval
        """
        while True:
            for model_id in list(self._metrics.keys()):
                await self.detect_drift(model_id)

            await asyncio.sleep(interval_seconds)

    def stop_monitoring(self) -> None:
        """Stop continuous monitoring."""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            self._monitoring_task = None

            logger.info("monitoring_stopped")

    def get_metrics(
        self,
        model_id: str,
        limit: int = 100,
    ) -> list[ModelMetrics]:
        """
        Get metrics for a model.

        Args:
            model_id: Model identifier
            limit: Maximum number of metrics

        Returns:
            List of model metrics
        """
        metrics = self._metrics.get(model_id, [])
        return sorted(metrics, key=lambda m: m.recorded_at, reverse=True)[:limit]

    def get_baseline(self, model_id: str) -> ModelMetrics | None:
        """
        Get baseline metrics for a model.

        Args:
            model_id: Model identifier

        Returns:
            Baseline metrics or None
        """
        return self._baselines.get(model_id)

    def get_alerts(
        self,
        model_id: str | None = None,
        drift_type: DriftType | None = None,
        limit: int = 100,
    ) -> list[DriftAlert]:
        """
        Get drift alerts.

        Args:
            model_id: Filter by model
            drift_type: Filter by drift type
            limit: Maximum number of alerts

        Returns:
            List of drift alerts
        """
        alerts = self._alerts

        if model_id:
            alerts = [a for a in alerts if a.model_id == model_id]

        if drift_type:
            alerts = [a for a in alerts if a.drift_type == drift_type]

        return sorted(alerts, key=lambda a: a.detected_at, reverse=True)[:limit]

    def get_monitoring_stats(self) -> dict[str, Any]:
        """
        Get monitoring statistics.

        Returns:
            Monitoring statistics
        """
        total_models = len(self._metrics)
        total_metrics = sum(len(metrics) for metrics in self._metrics.values())
        total_alerts = len(self._alerts)

        drift_type_counts: dict[str, int] = {}
        for alert in self._alerts:
            drift_type_counts[alert.drift_type] = drift_type_counts.get(alert.drift_type, 0) + 1

        return {
            "monitored_models": total_models,
            "total_metrics": total_metrics,
            "total_alerts": total_alerts,
            "drift_threshold": self._drift_threshold,
            "drift_type_breakdown": drift_type_counts,
        }
