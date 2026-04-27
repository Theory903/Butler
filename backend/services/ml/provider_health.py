"""ML Provider Health Tracker - Phase 4.

Tracks health status for ML model providers to enable health-gated routing
and fallback chains. Integrates with MLRuntimeManager to record success/failure
events and compute provider health metrics.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import structlog

from domain.ml.runtime_health import HealthStatus, ProviderHealth

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class ProviderMetrics:
    """Rolling metrics for a single provider."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency_ms: float = 0.0
    last_success_timestamp: float = 0.0
    last_failure_timestamp: float = 0.0

    @property
    def error_rate(self) -> float:
        """Calculate error rate (0.0 to 1.0)."""
        if self.total_requests == 0:
            return 0.0
        return self.failed_requests / self.total_requests

    @property
    def average_latency_ms(self) -> float | None:
        """Calculate average latency in milliseconds."""
        if self.successful_requests == 0:
            return None
        return self.total_latency_ms / self.successful_requests


class MLProviderHealthTracker:
    """Health tracker for ML model providers.

    Responsibilities:
    - Record success/failure events for each provider
    - Compute rolling error rates and latency metrics
    - Determine health status (HEALTHY, DEGRADED, UNHEALTHY)
    - Provide ProviderHealth snapshots for routing decisions
    - Support health-gated routing and fallback chains
    """

    def __init__(
        self,
        error_threshold: float = 0.5,
        latency_threshold_ms: float = 5000.0,
        cooldown_seconds: float = 60.0,
        min_samples: int = 5,
    ) -> None:
        """Initialize the provider health tracker.

        Args:
            error_threshold: Error rate above which provider is UNHEALTHY (0.0 to 1.0)
            latency_threshold_ms: Latency above which provider is DEGRADED
            cooldown_seconds: Time before a failed provider can recover
            min_samples: Minimum samples before health status is computed
        """
        self._error_threshold = error_threshold
        self._latency_threshold_ms = latency_threshold_ms
        self._cooldown_seconds = cooldown_seconds
        self._min_samples = min_samples

        self._metrics: dict[str, ProviderMetrics] = defaultdict(ProviderMetrics)
        self._status_cache: dict[str, tuple[HealthStatus, float]] = {}

    def record_model_success(
        self,
        provider_name: str,
        latency_ms: float | None = None,
    ) -> None:
        """Record a successful inference request.

        Args:
            provider_name: Name of the provider (e.g., "anthropic", "openai")
            latency_ms: Request latency in milliseconds
        """
        metrics = self._metrics[provider_name]
        metrics.total_requests += 1
        metrics.successful_requests += 1
        metrics.last_success_timestamp = time.time()

        if latency_ms is not None:
            metrics.total_latency_ms += latency_ms

        # Invalidate status cache on new data
        if provider_name in self._status_cache:
            del self._status_cache[provider_name]

        logger.debug(
            "ml_provider_success_recorded",
            provider=provider_name,
            total_requests=metrics.total_requests,
            error_rate=metrics.error_rate,
        )

    def record_model_failure(
        self,
        provider_name: str,
        latency_ms: float | None = None,
    ) -> None:
        """Record a failed inference request.

        Args:
            provider_name: Name of the provider
            latency_ms: Request latency in milliseconds (if available)
        """
        metrics = self._metrics[provider_name]
        metrics.total_requests += 1
        metrics.failed_requests += 1
        metrics.last_failure_timestamp = time.time()

        if latency_ms is not None:
            metrics.total_latency_ms += latency_ms

        # Invalidate status cache on new data
        if provider_name in self._status_cache:
            del self._status_cache[provider_name]

        logger.warning(
            "ml_provider_failure_recorded",
            provider=provider_name,
            total_requests=metrics.total_requests,
            error_rate=metrics.error_rate,
        )

    def get_provider_health(self, provider_name: str) -> ProviderHealth:
        """Get current health status for a provider.

        Args:
            provider_name: Name of the provider

        Returns:
            ProviderHealth snapshot with current status and metrics
        """
        metrics = self._metrics.get(provider_name)

        if metrics is None or metrics.total_requests < self._min_samples:
            # Not enough data - assume healthy for cold start
            return ProviderHealth(
                provider_name=provider_name,
                status=HealthStatus.UNKNOWN,
                latency_ms=None,
                error_rate=0.0,
                last_check_timestamp=time.time(),
            )

        # Check cache first
        if provider_name in self._status_cache:
            cached_status, cached_time = self._status_cache[provider_name]
            if time.time() - cached_time < 5.0:  # Cache for 5 seconds
                return ProviderHealth(
                    provider_name=provider_name,
                    status=cached_status,
                    latency_ms=metrics.average_latency_ms,
                    error_rate=metrics.error_rate,
                    last_check_timestamp=cached_time,
                )

        # Compute health status
        status = self._compute_health_status(metrics)

        # Update cache
        self._status_cache[provider_name] = (status, time.time())

        return ProviderHealth(
            provider_name=provider_name,
            status=status,
            latency_ms=metrics.average_latency_ms,
            error_rate=metrics.error_rate,
            last_check_timestamp=time.time(),
        )

    def _compute_health_status(self, metrics: ProviderMetrics) -> HealthStatus:
        """Compute health status from metrics.

        Args:
            metrics: Provider metrics

        Returns:
            HealthStatus (HEALTHY, DEGRADED, UNHEALTHY, or UNKNOWN)
        """
        # Check if in cooldown period after recent failure
        time_since_failure = time.time() - metrics.last_failure_timestamp
        if time_since_failure < self._cooldown_seconds and metrics.failed_requests > 0:
            logger.debug(
                "ml_provider_in_cooldown",
                provider="unknown",
                cooldown_remaining=self._cooldown_seconds - time_since_failure,
            )
            return HealthStatus.UNHEALTHY

        # Check error rate
        if metrics.error_rate >= self._error_threshold:
            logger.warning(
                "ml_provider_unhealthy_error_rate",
                provider="unknown",
                error_rate=metrics.error_rate,
                threshold=self._error_threshold,
            )
            return HealthStatus.UNHEALTHY

        # Check latency
        avg_latency = metrics.average_latency_ms
        if avg_latency is not None and avg_latency >= self._latency_threshold_ms:
            logger.warning(
                "ml_provider_degraded_latency",
                provider="unknown",
                latency_ms=avg_latency,
                threshold=self._latency_threshold_ms,
            )
            return HealthStatus.DEGRADED

        # Provider is healthy
        return HealthStatus.HEALTHY

    def get_all_provider_health(self) -> dict[str, ProviderHealth]:
        """Get health status for all tracked providers.

        Returns:
            Dictionary mapping provider names to ProviderHealth snapshots
        """
        return {
            provider_name: self.get_provider_health(provider_name)
            for provider_name in self._metrics.keys()
        }

    def reset_provider(self, provider_name: str) -> None:
        """Reset metrics for a provider (e.g., after configuration change).

        Args:
            provider_name: Name of the provider to reset
        """
        if provider_name in self._metrics:
            del self._metrics[provider_name]
        if provider_name in self._status_cache:
            del self._status_cache[provider_name]

        logger.info("ml_provider_metrics_reset", provider=provider_name)

    def get_metrics_summary(self) -> dict[str, Any]:
        """Get summary of all provider metrics for monitoring.

        Returns:
            Dictionary with provider metrics summary
        """
        summary = {}
        for provider_name, metrics in self._metrics.items():
            health = self.get_provider_health(provider_name)
            summary[provider_name] = {
                "total_requests": metrics.total_requests,
                "successful_requests": metrics.successful_requests,
                "failed_requests": metrics.failed_requests,
                "error_rate": metrics.error_rate,
                "average_latency_ms": metrics.average_latency_ms,
                "status": health.status.value,
                "last_success_timestamp": metrics.last_success_timestamp,
                "last_failure_timestamp": metrics.last_failure_timestamp,
            }
        return summary
