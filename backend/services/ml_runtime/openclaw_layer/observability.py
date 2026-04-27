"""Observability: logging, metrics, and tracing for provider operations."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any
from collections import defaultdict
import json

logger = logging.getLogger(__name__)


@dataclass
class ProviderRequestMetrics:
    """Metrics for a single provider request."""
    provider: str
    model: str
    start_time: float
    end_time: float | None = None
    duration_seconds: float | None = None
    success: bool = False
    error_message: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    retry_count: int = 0
    credential_id: str | None = None
    
    def complete(self, success: bool, error_message: str | None = None) -> None:
        """Mark the request as completed."""
        self.end_time = time.time()
        self.duration_seconds = self.end_time - self.start_time
        self.success = success
        self.error_message = error_message


@dataclass
class ProviderMetrics:
    """Aggregated metrics for a provider."""
    provider: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_duration_seconds: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    avg_duration_seconds: float = 0.0
    success_rate: float = 0.0
    
    def update(self, metrics: ProviderRequestMetrics) -> None:
        """Update aggregated metrics with a single request."""
        self.total_requests += 1
        
        if metrics.success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
        
        if metrics.duration_seconds:
            self.total_duration_seconds += metrics.duration_seconds
        
        self.total_input_tokens += metrics.input_tokens
        self.total_output_tokens += metrics.output_tokens
        self.total_tokens += metrics.total_tokens
        
        # Recalculate averages
        if self.total_requests > 0:
            self.avg_duration_seconds = self.total_duration_seconds / self.total_requests
            self.success_rate = self.successful_requests / self.total_requests


class ProviderObservability:
    """Observability manager for provider operations."""
    
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._metrics: dict[str, ProviderMetrics] = defaultdict(
            lambda: ProviderMetrics(provider="")
        )
        self._request_log: list[ProviderRequestMetrics] = []
    
    def log_provider_request(
        self,
        provider: str,
        model: str,
        credential_id: str | None = None,
    ) -> ProviderRequestMetrics:
        """Log the start of a provider request."""
        if not self.enabled:
            return ProviderRequestMetrics(
                provider=provider,
                model=model,
                start_time=time.time(),
                credential_id=credential_id,
            )
        
        metrics = ProviderRequestMetrics(
            provider=provider,
            model=model,
            start_time=time.time(),
            credential_id=credential_id,
        )
        self._request_log.append(metrics)
        
        logger.info(
            f"Provider request started",
            extra={
                "provider": provider,
                "model": model,
                "credential_id": credential_id,
                "timestamp": metrics.start_time,
            }
        )
        
        return metrics
    
    def log_provider_response(
        self,
        metrics: ProviderRequestMetrics,
        success: bool,
        error_message: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Log the completion of a provider request."""
        metrics.complete(success, error_message)
        metrics.input_tokens = input_tokens
        metrics.output_tokens = output_tokens
        metrics.total_tokens = input_tokens + output_tokens
        
        if not self.enabled:
            return
        
        # Update aggregated metrics
        provider_metrics = self._metrics[metrics.provider]
        provider_metrics.provider = metrics.provider
        provider_metrics.update(metrics)
        
        log_level = logging.INFO if success else logging.ERROR
        logger.log(
            log_level,
            f"Provider request {'completed' if success else 'failed'}",
            extra={
                "provider": metrics.provider,
                "model": metrics.model,
                "success": success,
                "error_message": error_message,
                "duration_seconds": metrics.duration_seconds,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": metrics.total_tokens,
                "credential_id": metrics.credential_id,
            }
        )
    
    def track_provider_metric(
        self,
        provider: str,
        metric_name: str,
        value: float,
        tags: dict[str, Any] | None = None,
    ) -> None:
        """Track a custom metric for a provider."""
        if not self.enabled:
            return
        
        logger.info(
            f"Provider metric tracked",
            extra={
                "provider": provider,
                "metric_name": metric_name,
                "value": value,
                "tags": tags or {},
            }
        )
    
    def get_provider_metrics(self, provider: str) -> ProviderMetrics:
        """Get aggregated metrics for a provider."""
        return self._metrics.get(provider, ProviderMetrics(provider=provider))
    
    def get_all_metrics(self) -> dict[str, ProviderMetrics]:
        """Get aggregated metrics for all providers."""
        return dict(self._metrics)
    
    def get_recent_requests(
        self,
        limit: int = 100,
        provider: str | None = None,
    ) -> list[ProviderRequestMetrics]:
        """Get recent request logs."""
        requests = self._request_log
        
        if provider:
            requests = [r for r in requests if r.provider == provider]
        
        return requests[-limit:]
    
    def clear_metrics(self) -> None:
        """Clear all metrics."""
        self._metrics.clear()
        self._request_log.clear()


def log_provider_request(
    provider: str,
    model: str,
    credential_id: str | None = None,
    observability: ProviderObservability | None = None,
) -> ProviderRequestMetrics:
    """Convenience function to log a provider request start."""
    if observability is None:
        observability = ProviderObservability()
    return observability.log_provider_request(provider, model, credential_id)


def log_provider_response(
    metrics: ProviderRequestMetrics,
    success: bool,
    error_message: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    observability: ProviderObservability | None = None,
) -> None:
    """Convenience function to log a provider request completion."""
    if observability is None:
        observability = ProviderObservability()
    observability.log_provider_response(
        metrics, success, error_message, input_tokens, output_tokens
    )


def track_provider_metric(
    provider: str,
    metric_name: str,
    value: float,
    tags: dict[str, Any] | None = None,
    observability: ProviderObservability | None = None,
) -> None:
    """Convenience function to track a custom provider metric."""
    if observability is None:
        observability = ProviderObservability()
    observability.track_provider_metric(provider, metric_name, value, tags)


# Global observability instance
_default_observability = ProviderObservability()


def get_default_observability() -> ProviderObservability:
    """Get the default observability instance."""
    return _default_observability
