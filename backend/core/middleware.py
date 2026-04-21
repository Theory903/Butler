"""Request context middleware.

Injects request_id, measures response timing, and sets production
security headers on every response.

Phase 11 addition:
  - W3C TraceContext propagation (traceparent / tracestate headers).
  - Exposes get_trace_context() + run_with_trace_context() for background tasks
    so asyncio tasks inherit the parent span rather than starting as root spans.
"""

from __future__ import annotations

import contextvars
import time
import uuid
from typing import Any, Callable, Coroutine

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = structlog.get_logger(__name__)

# ── ContextVar for trace propagation across async boundaries ──────────────────
_trace_context_var: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "butler_trace_context", default=None
)


def get_trace_context() -> Any:
    """Return the current OTel Context (or None if OTel is not installed).

    Call this at the *start* of a background task's launch site to capture
    the parent context, then pass it to ``run_with_trace_context``.

    Example::

        ctx = get_trace_context()
        asyncio.create_task(run_with_trace_context(ctx, my_background_coro()))
    """
    return _trace_context_var.get()


async def run_with_trace_context(
    ctx: Any, coro: Coroutine
) -> Any:
    """Execute ``coro`` with ``ctx`` as the active OTel context.

    This ensures that spans created inside background tasks are children
    of the inbound HTTP request span, not orphan root spans.

    Usage::

        ctx = get_trace_context()          # capture in request handler
        task = asyncio.create_task(
            run_with_trace_context(ctx, heavy_work())
        )
    """
    if ctx is None:
        return await coro
    try:
        from opentelemetry import context as otel_context
        token = otel_context.attach(ctx)
        try:
            return await coro
        finally:
            otel_context.detach(token)
    except ImportError:
        return await coro


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware that runs on every request:

    1. Assigns / propagates X-Request-ID
    2. Extracts W3C traceparent / tracestate and sets it as the parent OTel context
    3. Injects request_id + trace_id into structlog context
    4. Measures total response time
    5. Sets security + timing headers on response
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. Request ID — honour client-provided or generate new
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        # 2. W3C TraceContext propagation
        #    Extract traceparent / tracestate from headers and establish as parent span.
        trace_id = "none"
        try:
            from opentelemetry import context as otel_context
            from opentelemetry.propagators.b3 import B3Format  # type: ignore[import]
            from opentelemetry.propagate import extract

            carrier = {
                "traceparent": request.headers.get("traceparent", ""),
                "tracestate": request.headers.get("tracestate", ""),
            }
            parent_ctx = extract(carrier)
            _token = otel_context.attach(parent_ctx)
            _trace_context_var.set(parent_ctx)

            # Extract trace-id for logging
            from opentelemetry import trace as otel_trace
            current_span = otel_trace.get_current_span()
            if current_span and current_span.get_span_context().is_valid:
                trace_id = format(current_span.get_span_context().trace_id, "032x")
        except Exception:
            _token = None  # type: ignore[assignment]
            _trace_context_var.set(None)

        # 3. Bind to structlog for this request's context
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
        )

        # 4. Process request + measure timing
        start = time.perf_counter()
        response = await call_next(request)
        duration_s = time.perf_counter() - start
        duration_ms = round(duration_s * 1000, 2)

        # Detach OTel context after response
        try:
            if _token is not None:
                from opentelemetry import context as otel_context
                otel_context.detach(_token)
        except Exception:
            pass

        # 5. Response headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"
        if trace_id != "none":
            response.headers["X-Trace-ID"] = trace_id

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"  # Modern browsers use CSP
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # 6. Log at INFO (structured)
        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        return response
 
 
class TrafficGuardMiddleware(BaseHTTPMiddleware):
    """Protects the system by rejecting traffic if cluster health is CRITICAL.

    Exemptions:
      - /api/v1/health/*
      - /admin/*
      - /.well-known/*
    """

    def __init__(self, app: ASGIApp, redis_getter: Callable[[], Coroutine[Any, Any, Any]]) -> None:
        super().__init__(app)
        self._get_redis = redis_getter
        self._last_check = 0.0
        self._cached_health: str | None = None

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        # Exemptions
        if any(p in path for p in ["/health", "/admin", "/.well-known", "/internal"]):
            return await call_next(request)

        # Check cluster health (cached for 1s)
        now = time.time()
        if now - self._last_check > 1.0 or self._cached_health is None:
            try:
                redis = await self._get_redis()
                health = await redis.get("butler:cluster:health")
                self._cached_health = health.decode() if health else "HEALTHY"
                self._last_check = now
            except Exception:
                self._cached_health = "HEALTHY"  # Fail open

        if self._cached_health == "CRITICAL":
            from core.errors import ServiceUnavailableProblem
            from fastapi.responses import JSONResponse
            
            problem = ServiceUnavailableProblem(
                detail="System under critical load. Traffic shedding in effect."
            )
            return JSONResponse(
                status_code=503,
                content=problem.dict(),
                headers={"Retry-After": "30"}
            )

        return await call_next(request)
