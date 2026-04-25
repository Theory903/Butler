from __future__ import annotations

import os
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_BUTLER_VERSION = os.environ.get("BUTLER_VERSION", "dev")
_SERVICE_NAME = "butler"

AttributeValue = str | bool | int | float
_OTEL_INITIALIZED = False


def _safe_attr_value(value: Any) -> AttributeValue | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        return value
    return str(value)


def _safe_set_span_attributes(span: Any, attrs: dict[str, Any] | None) -> None:
    if not attrs:
        return
    for key, value in attrs.items():
        if not key:
            continue
        safe_value = _safe_attr_value(value)
        if safe_value is None:
            continue
        try:
            span.set_attribute(key, safe_value)
        except Exception:
            logger.debug("span_attribute_set_failed", key=key)


def _resolve_http_route(scope: dict[str, Any]) -> str:
    """Prefer low-cardinality route template when available."""
    route = scope.get("route")
    if route is not None:
        path = getattr(route, "path", None)
        if isinstance(path, str) and path.strip():
            return path
    path = scope.get("path", "/")
    return path if isinstance(path, str) and path else "/"


def setup_observability(app: Any, service_name: str, otel_endpoint: str | None) -> None:
    """Configure OpenTelemetry + optional auto-instrumentation.

    Safe to call multiple times. Later calls become no-ops after successful init.
    """
    global _OTEL_INITIALIZED

    if _OTEL_INITIALIZED:
        logger.debug("observability_already_initialized")
        return

    if not otel_endpoint:
        logger.info("observability_disabled_no_endpoint")
        return

    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create(
            {
                "service.name": service_name or _SERVICE_NAME,
                "service.version": _BUTLER_VERSION,
            }
        )

        trace_provider = TracerProvider(resource=resource)
        trace_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=otel_endpoint),
            )
        )
        trace.set_tracer_provider(trace_provider)

        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=otel_endpoint),
            export_interval_millis=15000,
        )
        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[metric_reader],
        )
        metrics.set_meter_provider(meter_provider)

        try:
            FastAPIInstrumentor.instrument_app(app)
        except Exception as exc:
            logger.warning("fastapi_instrumentation_failed", error=str(exc))

        try:
            SQLAlchemyInstrumentor().instrument()
        except Exception as exc:
            logger.warning("sqlalchemy_instrumentation_failed", error=str(exc))

        try:
            RedisInstrumentor().instrument()
        except Exception as exc:
            logger.warning("redis_instrumentation_failed", error=str(exc))

        _OTEL_INITIALIZED = True
        logger.info("observability_setup_complete", endpoint=otel_endpoint, service=service_name)

    except ImportError as exc:
        logger.warning("observability_sdk_missing", error=str(exc))
    except Exception as exc:
        logger.exception("observability_setup_failed", error=str(exc))


class ButlerTracer:
    """Service-layer tracing helper with graceful no-op fallback."""

    _instance: ButlerTracer | None = None

    def __init__(self) -> None:
        self._tracer = self._init_tracer()

    @classmethod
    def get(cls) -> ButlerTracer:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def _init_tracer(self) -> Any | None:
        try:
            from opentelemetry import trace

            tracer = trace.get_tracer(_SERVICE_NAME, _BUTLER_VERSION)
            logger.debug("butler_tracer_ready")
            return tracer
        except ImportError:
            logger.debug("otel_sdk_not_installed_noop_tracer")
            return None
        except Exception as exc:
            logger.warning("butler_tracer_init_failed", error=str(exc))
            return None

    @contextmanager
    def span(
        self,
        name: str,
        attrs: dict[str, Any] | None = None,
        account_id: str | None = None,
        session_id: str | None = None,
    ) -> Generator[Any | None]:
        """Wrap work in a span. Never breaks the hot path."""
        if self._tracer is None:
            yield None
            return

        try:
            from opentelemetry.trace import Status, StatusCode

            with self._tracer.start_as_current_span(name) as span:
                merged = dict(attrs or {})
                if account_id:
                    merged["butler.account_id"] = account_id
                if session_id:
                    merged["butler.session_id"] = session_id

                _safe_set_span_attributes(span, merged)

                trace_id = self.get_current_trace_id()
                if trace_id:
                    with structlog.contextvars.bound_contextvars(trace_id=trace_id):
                        try:
                            yield span
                            span.set_status(Status(StatusCode.OK))
                        except Exception as exc:
                            span.record_exception(exc)
                            span.set_status(Status(StatusCode.ERROR, str(exc)))
                            raise
                else:
                    try:
                        yield span
                        span.set_status(Status(StatusCode.OK))
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        raise
        except Exception:
            raise

    def record_error(self, exc: Exception) -> None:
        if self._tracer is None:
            return
        try:
            from opentelemetry import trace
            from opentelemetry.trace import Status, StatusCode

            span = trace.get_current_span()
            if span is not None and span.is_recording():
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
        except Exception:
            pass

    @property
    def is_available(self) -> bool:
        return self._tracer is not None

    def get_current_trace_id(self) -> str | None:
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


class ButlerMetrics:
    """Prometheus metrics registry with no-op safety."""

    _instance: ButlerMetrics | None = None

    def __init__(self) -> None:
        self._available = self._init_metrics()

    @classmethod
    def get(cls) -> ButlerMetrics:
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
                "Circuit breaker state per service (0=closed,1=half_open,2=open)",
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
                "Cluster health (0=Critical,1=Degraded,2=Healthy,-1=NoNodes)",
            )
            self._node_cpu = Gauge(
                "butler_node_cpu_percent",
                "Current CPU usage percentage of the node",
                ["node_id"],
            )
            self._node_mem = Gauge(
                "butler_node_memory_percent",
                "Current memory usage percentage of the node",
                ["node_id"],
            )
            self._node_status = Gauge(
                "butler_node_status_value",
                "Current node health status (0=Healthy,1=Degraded,2=Unhealthy)",
                ["node_id"],
            )
            self._load_shed_events = Counter(
                "butler_load_shed_events_total",
                "Total number of load shedding events",
                ["node_id", "service", "reason"],
            )
            self._rate_limit_hits = Counter(
                "butler_gateway_rate_limit_hits_total",
                "Total requests rejected by edge rate limiter",
                ["endpoint"],
            )
            self._idempotency_replays = Counter(
                "butler_gateway_idempotency_replays_total",
                "Total idempotency cache hits",
                ["endpoint"],
            )
            self._auth_failures = Counter(
                "butler_gateway_auth_failures_total",
                "Total JWT/auth rejections at the edge",
                ["reason"],
            )
            self._active_streams = Gauge(
                "butler_gateway_active_streams",
                "Number of currently open SSE/WebSocket streams",
            )
            logger.info("prometheus_metrics_initialized")
            return True
        except ImportError:
            logger.debug("prometheus_client_not_installed_metrics_noop")
            return False
        except ValueError as exc:
            logger.warning("prometheus_metrics_already_registered", error=str(exc))
            return False

    def record_http_request(self, method: str, path: str, status: int, latency_s: float) -> None:
        if not self._available:
            return
        try:
            self._http_requests.labels(method=method, path=path, status=str(status)).inc()
            self._http_latency.labels(method=method, path=path).observe(max(latency_s, 0.0))
        except Exception:
            pass

    def record_tool_call(self, tool_name: str, risk_tier: str, success: bool) -> None:
        if not self._available:
            return
        with suppress(Exception):
            self._tool_calls.labels(
                tool_name=tool_name,
                risk_tier=risk_tier,
                success=str(success).lower(),
            ).inc()

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
            if input_tokens > 0:
                self._llm_tokens.labels(provider=provider, model=model, type="input").inc(
                    input_tokens
                )
            if output_tokens > 0:
                self._llm_tokens.labels(provider=provider, model=model, type="output").inc(
                    output_tokens
                )
            if cache_tokens > 0:
                self._llm_tokens.labels(provider=provider, model=model, type="cache").inc(
                    cache_tokens
                )
        except Exception:
            pass

    def set_circuit_breaker_state(self, service: str, state: str) -> None:
        if not self._available:
            return
        state_map = {"closed": 0, "half_open": 1, "open": 2}
        with suppress(Exception):
            self._circuit_breaker.labels(service=service).set(state_map.get(state, 0))

    def record_memory_write(self, tier: str) -> None:
        if not self._available:
            return
        with suppress(Exception):
            self._memory_writes.labels(tier=tier).inc()

    def inc_counter(
        self,
        name: str,
        *,
        tags: dict[str, object] | None = None,
        value: int = 1,
    ) -> None:
        """Compatibility shim for legacy call sites that still emit generic counters."""
        if value == 0 or not self._available:
            return

        normalized_tags = {str(key): str(tag_value) for key, tag_value in (tags or {}).items()}

        try:
            if name == "memory.consent.scrubbed_bytes":
                self._memory_writes.labels(tier="SCRUBBED_BYTES").inc(max(value, 0))
                return

            if name.startswith("memory.consent."):
                tier = name.removeprefix("memory.consent.").upper()
                self._memory_writes.labels(tier=tier).inc(max(value, 0))
                return

            if name.startswith("gateway.transport."):
                reason = normalized_tags.get("reason", name.removeprefix("gateway.transport."))
                self._auth_failures.labels(reason=reason).inc(max(value, 0))
                return

            if name.startswith(("realtime.mux.", "mcp.memory.")):
                # These are best-effort internal counters. Keep the compatibility
                # surface non-throwing even when no dedicated metric exists yet.
                return
        except Exception:
            pass

    def set_cron_active(self, count: int) -> None:
        if not self._available:
            return
        with suppress(Exception):
            self._cron_active.set(max(count, 0))

    def set_acp_pending(self, count: int) -> None:
        if not self._available:
            return
        with suppress(Exception):
            self._acp_pending.set(max(count, 0))

    def record_node_resource(self, node_id: str, cpu: float, mem: float, status: str) -> None:
        if not self._available:
            return
        try:
            self._node_cpu.labels(node_id=node_id).set(cpu)
            self._node_mem.labels(node_id=node_id).set(mem)
            status_map = {"HEALTHY": 0, "DEGRADED": 1, "UNHEALTHY": 2, "STARTING": 0}
            self._node_status.labels(node_id=node_id).set(status_map.get(status, 2))
        except Exception:
            pass

    def record_load_shed(
        self,
        node_id: str | None = None,
        service: str | None = None,
        reason: str = "unknown",
        *,
        component: str | None = None,
    ) -> None:
        if not self._available:
            return
        resolved_node_id = node_id or "unknown"
        resolved_service = service or component or "unknown"
        with suppress(Exception):
            self._load_shed_events.labels(
                node_id=resolved_node_id,
                service=resolved_service,
                reason=reason,
            ).inc()

    def inc_rate_limit_hit(self, endpoint: str = "unknown") -> None:
        if not self._available:
            return
        with suppress(Exception):
            self._rate_limit_hits.labels(endpoint=endpoint).inc()

    def inc_idempotency_replay(self, endpoint: str = "unknown") -> None:
        if not self._available:
            return
        with suppress(Exception):
            self._idempotency_replays.labels(endpoint=endpoint).inc()

    def inc_auth_failure(self, reason: str = "invalid_token") -> None:
        if not self._available:
            return
        with suppress(Exception):
            self._auth_failures.labels(reason=reason).inc()

    def inc_active_streams(self) -> None:
        if not self._available:
            return
        with suppress(Exception):
            self._active_streams.inc()

    def dec_active_streams(self) -> None:
        if not self._available:
            return
        with suppress(Exception):
            self._active_streams.dec()

    def get_gateway_snapshot(self) -> dict[str, int]:
        if not self._available:
            return {
                "rate_limit_hits": 0,
                "idempotency_replays": 0,
                "auth_failures": 0,
                "active_streams": 0,
            }

        try:

            def _sum_counter(counter: Any) -> int:
                total = 0
                for metric in counter.collect():
                    for sample in metric.samples:
                        if sample.name.endswith("_total"):
                            total += int(sample.value)
                return total

            def _read_gauge(gauge: Any) -> int:
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


class ObservabilityMiddleware:
    """ASGI middleware for request spans, metrics, and structured logs."""

    def __init__(self, app: Any) -> None:
        self._app = app
        self._tracer = ButlerTracer.get()
        self._metrics = ButlerMetrics.get()

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        method = scope.get("method", "UNKNOWN")
        route = _resolve_http_route(scope)
        raw_path = scope.get("path", "/")
        start = time.monotonic()
        status_code = 500

        async def _wrapped_send(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 200))
            await send(message)

        span_name = f"http.request {method} {route}"

        try:
            with self._tracer.span(
                span_name,
                attrs={
                    "http.method": method,
                    "http.route": route,
                    "url.path": raw_path,
                },
            ) as span:
                await self._app(scope, receive, _wrapped_send)

                if span is not None:
                    with suppress(Exception):
                        span.set_attribute("http.status_code", status_code)
        except Exception as exc:
            self._tracer.record_error(exc)
            raise
        finally:
            latency = time.monotonic() - start

            self._metrics.record_http_request(
                method=method,
                path=route,
                status=status_code,
                latency_s=latency,
            )

            logger.info(
                "http_request",
                method=method,
                route=route,
                path=raw_path,
                status=status_code,
                latency_ms=round(latency * 1000, 1),
                trace_id=self._tracer.get_current_trace_id(),
            )


def get_tracer() -> ButlerTracer:
    return ButlerTracer.get()


def get_metrics() -> ButlerMetrics:
    return ButlerMetrics.get()
