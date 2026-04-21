"""Butler Observability — Phase 9.

Extends the original setup_observability() stub with:
  ButlerTracer        — OTel span management with graceful no-op fallback
  ButlerMetrics       — Prometheus counter/histogram/gauge registry
  ObservabilityMiddleware — ASGI auto-instrumentation for all HTTP

Semantic conventions (opentelemetry-specification §resource):
  service.name              = "butler"
  service.version           = {BUTLER_VERSION env var}
  butler.account_id         = {account_id}
  butler.session_id         = {session_id}
  butler.tool.name          = {tool_name}
  butler.tool.risk_tier     = {L0..L3}
  butler.memory.tier        = {HOT|WARM|COLD|GRAPH|STRUCT}
  butler.model.tier         = {T0..T3}
  butler.model.provider     = {anthropic|openai|local}

Prometheus metrics:
  butler_http_requests_total{method,path,status}
  butler_http_latency_seconds{method,path}        (histogram)
  butler_tool_calls_total{tool_name,risk_tier,success}
  butler_llm_tokens_total{provider,model,type}    (input|output|cache)
  butler_circuit_breaker_state{service}           (0=closed,1=half_open,2=open)
  butler_memory_writes_total{tier}
  butler_cron_jobs_active                         (gauge)
  butler_acp_requests_pending                     (gauge)

Design rule: observe-and-continue — no observability call ever raises
or breaks the hot path. All emitters are wrapped in try/except.

Governed by: docs/00-governance/transplant-constitution.md §8
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Any, Generator

import structlog

logger = structlog.get_logger(__name__)

_BUTLER_VERSION = os.environ.get("BUTLER_VERSION", "dev")
_SERVICE_NAME   = "butler"


# ── Original setup_observability (kept intact) ─────────────────────────────────

def setup_observability(app, service_name: str, otel_endpoint: str | None):
    """Configure full OTel stack with Butler semantic conventions.

    Original Phase 0 stub — kept for startup wiring in main.py.
    Phase 9 extends with ButlerTracer / ButlerMetrics for service-layer use.
    """
    if not otel_endpoint:
        return  # Skip in dev/test without collector

    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        # Traces
        trace_provider = TracerProvider()
        trace_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=otel_endpoint))
        )
        trace.set_tracer_provider(trace_provider)

        # Metrics
        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=otel_endpoint),
            export_interval_millis=15000,
        )
        meter_provider = MeterProvider(metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)

        # Auto-instrument FastAPI, SQLAlchemy, Redis
        FastAPIInstrumentor.instrument_app(app)
        SQLAlchemyInstrumentor().instrument()
        RedisInstrumentor().instrument()

        logger.info("observability_setup_complete", endpoint=otel_endpoint)

    except ImportError as exc:
        logger.warning("observability_sdk_missing", error=str(exc))


# ── ButlerTracer ───────────────────────────────────────────────────────────────

class ButlerTracer:
    """Butler OTel tracer — service-layer span management.

    Graceful no-op when opentelemetry-sdk is not installed.

    Usage:
        tracer = ButlerTracer.get()
        with tracer.span("tool.execute", attrs={"butler.tool.name": "web_search"}) as span:
            ...
    """

    _instance: "ButlerTracer | None" = None

    def __init__(self) -> None:
        self._tracer = self._init_tracer()

    @classmethod
    def get(cls) -> "ButlerTracer":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Force re-initialisation (useful in tests)."""
        cls._instance = None

    def _init_tracer(self):
        try:
            from opentelemetry import trace

            # Re-use provider if already set by setup_observability()
            trace.get_tracer_provider()
            tracer = trace.get_tracer(_SERVICE_NAME, _BUTLER_VERSION)
            logger.debug("butler_tracer_ready")
            return tracer
        except ImportError:
            logger.debug("otel_sdk_not_installed_noop_tracer")
            return None

    @contextmanager
    def span(
        self,
        name: str,
        attrs: dict[str, Any] | None = None,
        account_id: str | None = None,
        session_id: str | None = None,
    ) -> Generator:
        """Context manager wrapping work in an OTel span.

        Always safe — yields None (no-op) when OTel is unavailable.
        """
        if self._tracer is None:
            yield None
            return

        try:
            with self._tracer.start_as_current_span(name) as span:
                merged = dict(attrs or {})
                if account_id:
                    merged["butler.account_id"] = account_id
                if session_id:
                    merged["butler.session_id"] = session_id
                for k, v in merged.items():
                    span.set_attribute(k, str(v))
                
                # Context propagation for log correlation
                trace_id = self.get_current_trace_id()
                with structlog.contextvars.bound_contextvars(trace_id=trace_id):
                    yield span
        except Exception as e:
            # ONLY catch internal OTel failures. Application errors from 'yield'
            # are propagated naturally because they are not caught here (re-raised by 'with').
            # We catch here ONLY if start_as_current_span or the setup logic fails.
            logger.debug("otel_span_internal_error", error=str(e))
            # DO NOT yield again here. Let the exception propagate.
            raise

    def record_error(self, exc: Exception) -> None:
        """Record an exception on the current active span."""
        if self._tracer is None:
            return
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            if span.is_recording():
                span.record_exception(exc)
        except Exception:
            pass

    @property
    def is_available(self) -> bool:
        return self._tracer is not None

    def get_current_trace_id(self) -> str | None:
        """Get hex string of current trace id. Safe for log correlation."""
        if self._tracer is None:
            return None
        try:
            from opentelemetry import trace
            span_context = trace.get_current_span().get_span_context()
            if span_context.is_valid:
                return format(span_context.trace_id, "032x")
        except Exception:
            pass
        return None


# ── ButlerMetrics ──────────────────────────────────────────────────────────────

class ButlerMetrics:
    """Butler Prometheus metrics registry.

    Graceful no-op when prometheus_client is not installed.

    Usage:
        m = ButlerMetrics.get()
        m.record_tool_call("web_search", "L0", success=True)
        m.record_http_request("GET", "/api/v1/chat", 200, 0.123)
    """

    _instance: "ButlerMetrics | None" = None

    def __init__(self) -> None:
        self._available = self._init_metrics()

    @classmethod
    def get(cls) -> "ButlerMetrics":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def _init_metrics(self) -> bool:
        try:
            from prometheus_client import Counter, Gauge, Histogram

            self._http_requests = Counter(
                "butler_http_requests_total",
                "Total HTTP requests handled by Butler",
                ["method", "path", "status"],
            )
            self._http_latency = Histogram(
                "butler_http_latency_seconds",
                "HTTP request latency in seconds",
                ["method", "path"],
                buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
            )
            self._tool_calls = Counter(
                "butler_tool_calls_total",
                "Total tool invocations",
                ["tool_name", "risk_tier", "success"],
            )
            self._llm_tokens = Counter(
                "butler_llm_tokens_total",
                "Total LLM tokens consumed",
                ["provider", "model", "type"],
            )
            self._circuit_breaker = Gauge(
                "butler_circuit_breaker_state",
                "Circuit breaker state per service (0=closed, 1=half_open, 2=open)",
                ["service"],
            )
            self._memory_writes = Counter(
                "butler_memory_writes_total",
                "Total memory write operations by tier",
                ["tier"],
            )
            self._cron_active = Gauge(
                "butler_cron_jobs_active",
                "Number of active cron jobs across all accounts",
            )
            self._acp_pending = Gauge(
                "butler_acp_requests_pending",
                "Number of pending ACP approval requests",
            )
            self.GAUGE_CLUSTER_HEALTH = Gauge(
                "butler_cluster_health_value",
                "Current global cluster health (0=Critical, 1=Degraded, 2=Healthy, -1=NoNodes)",
            )
            # Node Health & Resource Metrics
            self._node_cpu = Gauge(
                "butler_node_cpu_percent",
                "Current CPU usage percentage of the node",
                ["node_id"],
            )
            self._node_mem = Gauge(
                "butler_node_memory_percent",
                "Current Memory usage percentage of the node",
                ["node_id"],
            )
            self._node_status = Gauge(
                "butler_node_status_value",
                "Current node health status (0=Healthy, 1=Degraded, 2=Unhealthy)",
                ["node_id"],
            )
            self._load_shed_events = Counter(
                "butler_load_shed_events_total",
                "Total number of load shedding events (rejections or throttling)",
                ["node_id", "service", "reason"],
            )
            # Gateway edge counters — read by /internal/metrics/summary
            self._rate_limit_hits = Counter(
                "butler_gateway_rate_limit_hits_total",
                "Total requests rejected by edge rate limiter",
                ["endpoint"],
            )
            self._idempotency_replays = Counter(
                "butler_gateway_idempotency_replays_total",
                "Total idempotency cache hits (request replayed from cache)",
                ["endpoint"],
            )
            self._auth_failures = Counter(
                "butler_gateway_auth_failures_total",
                "Total JWT / auth rejections at the edge",
                ["reason"],
            )
            self._active_streams = Gauge(
                "butler_gateway_active_streams",
                "Number of currently open SSE / WebSocket streams",
            )
            logger.info("prometheus_metrics_initialized")
            return True
        except ImportError:
            logger.debug("prometheus_client_not_installed_metrics_noop")
            return False

    # ── Public helpers ────────────────────────────────────────────────────────

    def record_http_request(
        self, method: str, path: str, status: int, latency_s: float
    ) -> None:
        if not self._available:
            return
        try:
            self._http_requests.labels(method=method, path=path, status=str(status)).inc()
            self._http_latency.labels(method=method, path=path).observe(latency_s)
        except Exception:
            pass

    def record_tool_call(self, tool_name: str, risk_tier: str, success: bool) -> None:
        if not self._available:
            return
        try:
            self._tool_calls.labels(
                tool_name=tool_name,
                risk_tier=risk_tier,
                success=str(success).lower(),
            ).inc()
        except Exception:
            pass

    def record_llm_tokens(
        self,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_tokens: int = 0,
    ) -> None:
        if not self._available:
            return
        try:
            if input_tokens:
                self._llm_tokens.labels(provider=provider, model=model, type="input").inc(input_tokens)
            if output_tokens:
                self._llm_tokens.labels(provider=provider, model=model, type="output").inc(output_tokens)
            if cache_tokens:
                self._llm_tokens.labels(provider=provider, model=model, type="cache").inc(cache_tokens)
        except Exception:
            pass

    def set_circuit_breaker_state(self, service: str, state: str) -> None:
        """Record circuit breaker state as gauge: closed=0, half_open=1, open=2."""
        if not self._available:
            return
        _map = {"closed": 0, "half_open": 1, "open": 2}
        try:
            self._circuit_breaker.labels(service=service).set(_map.get(state, 0))
        except Exception:
            pass

    def record_memory_write(self, tier: str) -> None:
        if not self._available:
            return
        try:
            self._memory_writes.labels(tier=tier).inc()
        except Exception:
            pass

    def set_cron_active(self, count: int) -> None:
        if not self._available:
            return
        try:
            self._cron_active.set(count)
        except Exception:
            pass

    def set_acp_pending(self, count: int) -> None:
        if not self._available:
            return
        try:
            self._acp_pending.set(count)
        except Exception:
            pass

    def record_node_resource(self, node_id: str, cpu: float, mem: float, status: str) -> None:
        if not self._available:
            return
        try:
            self._node_cpu.labels(node_id=node_id).set(cpu)
            self._node_mem.labels(node_id=node_id).set(mem)
            _status_map = {"HEALTHY": 0, "DEGRADED": 1, "UNHEALTHY": 2, "STARTING": 0}
            self._node_status.labels(node_id=node_id).set(_status_map.get(status, 2))
        except Exception:
            pass

    def record_load_shed(self, node_id: str, service: str, reason: str) -> None:
        if not self._available:
            return
        try:
            self._load_shed_events.labels(node_id=node_id, service=service, reason=reason).inc()
        except Exception:
            pass

    # ── Gateway edge metrics ───────────────────────────────────────────────────

    def inc_rate_limit_hit(self, endpoint: str = "unknown") -> None:
        """Increment when a request is rejected by the edge rate limiter."""
        if not self._available:
            return
        try:
            self._rate_limit_hits.labels(endpoint=endpoint).inc()
        except Exception:
            pass

    def inc_idempotency_replay(self, endpoint: str = "unknown") -> None:
        """Increment when a cached idempotent response is replayed."""
        if not self._available:
            return
        try:
            self._idempotency_replays.labels(endpoint=endpoint).inc()
        except Exception:
            pass

    def inc_auth_failure(self, reason: str = "invalid_token") -> None:
        """Increment on every JWT / auth rejection at the edge."""
        if not self._available:
            return
        try:
            self._auth_failures.labels(reason=reason).inc()
        except Exception:
            pass

    def inc_active_streams(self) -> None:
        """Increment when a new SSE / WebSocket stream opens."""
        if not self._available:
            return
        try:
            self._active_streams.inc()
        except Exception:
            pass

    def dec_active_streams(self) -> None:
        """Decrement when an SSE / WebSocket stream closes."""
        if not self._available:
            return
        try:
            self._active_streams.dec()
        except Exception:
            pass

    def get_gateway_snapshot(self) -> dict:
        """Return a point-in-time snapshot of gateway counters for /internal/metrics/summary.

        Reads _value directly from prometheus_client label maps.
        Safe to call even when prometheus_client is unavailable — returns zeros.
        """
        if not self._available:
            return {
                "rate_limit_hits": 0,
                "idempotency_replays": 0,
                "auth_failures": 0,
                "active_streams": 0,
            }
        try:
            def _sum_counter(counter) -> int:
                """Sum all label combinations of a Counter."""
                total = 0
                for metric in counter.collect():
                    for sample in metric.samples:
                        if sample.name.endswith("_total"):
                            total += int(sample.value)
                return total

            def _read_gauge(gauge) -> int:
                for metric in gauge.collect():
                    for sample in metric.samples:
                        return int(sample.value)
                return 0

            return {
                "rate_limit_hits": _sum_counter(self._rate_limit_hits),
                "idempotency_replays": _sum_counter(self._idempotency_replays),
                "auth_failures": _sum_counter(self._auth_failures),
                "active_streams": _read_gauge(self._active_streams),
            }
        except Exception:
            return {
                "rate_limit_hits": 0,
                "idempotency_replays": 0,
                "auth_failures": 0,
                "active_streams": 0,
            }

    @property
    def is_available(self) -> bool:
        return self._available


# ── Observability ASGI Middleware ─────────────────────────────────────────────

class ObservabilityMiddleware:
    """ASGI middleware: auto-instruments every HTTP request.

    Emits per-request:
      - OTel span ("http.request GET /path")
      - Prometheus http_requests_total + http_latency_seconds
      - structlog structured log line at INFO level

    Usage in main.py:
        app.add_middleware(ObservabilityMiddleware)
    """

    def __init__(self, app) -> None:
        self._app    = app
        self._tracer = ButlerTracer.get()
        self._metrics = ButlerMetrics.get()

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        method = scope.get("method", "UNKNOWN")
        path   = scope.get("path", "/")
        start  = time.monotonic()
        status = [200]

        async def _wrapped_send(message):
            if message.get("type") == "http.response.start":
                status[0] = message.get("status", 200)
            await send(message)

        span_name = f"http.request {method} {path}"
        with self._tracer.span(span_name, attrs={"http.method": method, "http.route": path}):
            try:
                await self._app(scope, receive, _wrapped_send)
            finally:
                latency = time.monotonic() - start
                self._metrics.record_http_request(
                    method=method,
                    path=path,
                    status=status[0],
                    latency_s=latency,
                )
                logger.info(
                    "http_request",
                    method=method,
                    path=path,
                    status=status[0],
                    latency_ms=round(latency * 1000, 1),
                )


# ── Convenience accessors ─────────────────────────────────────────────────────

def get_tracer() -> ButlerTracer:
    return ButlerTracer.get()


def get_metrics() -> ButlerMetrics:
    return ButlerMetrics.get()
