"""Model Monitoring.

Phase I: Model monitoring using Prometheus for metrics collection.
"""

import logging
from typing import Any
from prometheus_client import Counter, Gauge, Histogram, start_http_server
from prometheus_client import CollectorRegistry

logger = logging.getLogger(__name__)


class ButlerModelMonitoring:
    """Model monitoring using Prometheus.

    This class:
    - Tracks model inference metrics
    - Monitors latency and error rates
    - Tracks token usage and costs
    - Provides Prometheus metrics endpoint
    """

    def __init__(self, port: int = 9090):
        """Initialize model monitoring.

        Args:
            port: Prometheus metrics server port
        """
        self._port = port
        self._registry = CollectorRegistry()
        self._metrics = {}

    def initialize(self) -> None:
        """Initialize Prometheus metrics server."""
        try:
            start_http_server(self._port, registry=self._registry)
            logger.info("prometheus_server_started", port=self._port)
        except Exception as e:
            logger.exception("prometheus_server_failed")

    def create_counter(self, name: str, description: str, labels: list[str] | None = None) -> Counter:
        """Create a counter metric.

        Args:
            name: Metric name
            description: Metric description
            labels: Label names

        Returns:
            Counter instance
        """
        if labels:
            counter = Counter(name, description, labels, registry=self._registry)
        else:
            counter = Counter(name, description, registry=self._registry)
        self._metrics[name] = counter
        return counter

    def create_gauge(self, name: str, description: str, labels: list[str] | None = None) -> Gauge:
        """Create a gauge metric.

        Args:
            name: Metric name
            description: Metric description
            labels: Label names

        Returns:
            Gauge instance
        """
        if labels:
            gauge = Gauge(name, description, labels, registry=self._registry)
        else:
            gauge = Gauge(name, description, registry=self._registry)
        self._metrics[name] = gauge
        return gauge

    def create_histogram(self, name: str, description: str, buckets: list[float] | None = None) -> Histogram:
        """Create a histogram metric.

        Args:
            name: Metric name
            description: Metric description
            buckets: Histogram buckets

        Returns:
            Histogram instance
        """
        histogram = Histogram(name, description, buckets=buckets, registry=self._registry)
        self._metrics[name] = histogram
        return histogram

    def get_metric(self, name: str) -> Any | None:
        """Get a metric by name.

        Args:
            name: Metric name

        Returns:
            Metric instance or None
        """
        return self._metrics.get(name)

    def track_inference(self, model: str, provider: str, latency: float, success: bool) -> None:
        """Track model inference metrics.

        Args:
            model: Model name
            provider: Provider name
            latency: Inference latency in seconds
            success: Whether inference succeeded
        """
        counter = self._metrics.get("butler_inference_total")
        if counter:
            counter.labels(model=model, provider=provider, status="success" if success else "error").inc()

        histogram = self._metrics.get("butler_inference_latency_seconds")
        if histogram:
            histogram.labels(model=model, provider=provider).observe(latency)

    def track_token_usage(self, model: str, input_tokens: int, output_tokens: int) -> None:
        """Track token usage metrics.

        Args:
            model: Model name
            input_tokens: Input token count
            output_tokens: Output token count
        """
        counter = self._metrics.get("butler_tokens_total")
        if counter:
            counter.labels(model=model, type="input").inc(input_tokens)
            counter.labels(model=model, type="output").inc(output_tokens)

    def track_cost(self, model: str, provider: str, cost_usd: float) -> None:
        """Track cost metrics.

        Args:
            model: Model name
            provider: Provider name
            cost_usd: Cost in USD
        """
        counter = self._metrics.get("butler_cost_usd_total")
        if counter:
            counter.labels(model=model, provider=provider).inc(cost_usd)
