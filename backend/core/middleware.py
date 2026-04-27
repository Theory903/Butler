from __future__ import annotations

import contextvars
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = structlog.get_logger(__name__)

T = TypeVar("T")

_trace_context_var: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "butler_trace_context",
    default=None,
)

# Tenant context variable for request-scoped tenant identity
_tenant_context_var: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "butler_tenant_context",
    default=None,
)

# Runtime context variable for canonical runtime context
_runtime_context_var: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "butler_runtime_context",
    default=None,
)


def get_trace_context() -> Any:
    """Return the currently attached OTel context, if any."""
    return _trace_context_var.get()


def get_tenant_context() -> Any:
    """Return the currently attached TenantContext, if any."""
    return _tenant_context_var.get()


def get_runtime_context() -> Any:
    """Return the currently attached RuntimeContext, if any."""
    return _runtime_context_var.get()


async def run_with_trace_context[T](
    ctx: Any,
    fn: Callable[..., Awaitable[T]],
    *args: Any,
    **kwargs: Any,
) -> T:
    """Run an async callable with the supplied OTel context attached."""
    if ctx is None:
        return await fn(*args, **kwargs)

    try:
        from opentelemetry import context as otel_context

        token = otel_context.attach(ctx)
        try:
            return await fn(*args, **kwargs)
        finally:
            otel_context.detach(token)
    except ImportError:
        return await fn(*args, **kwargs)


def _extract_trace_id_from_context(ctx: Any) -> str | None:
    try:
        from opentelemetry.trace.propagation import get_current_span

        span = get_current_span(ctx)
        if span is None:
            return None
        span_context = span.get_span_context()
        if span_context.is_valid:
            return format(span_context.trace_id, "032x")
    except Exception:
        return None
    return None


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign request context, propagate trace context, and set security headers."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        trace_id: str | None = None
        otel_token: Any = None
        reset_token: Any = None

        start = time.perf_counter()

        try:
            try:
                from opentelemetry import context as otel_context
                from opentelemetry.propagate import extract

                carrier = {
                    "traceparent": request.headers.get("traceparent", ""),
                    "tracestate": request.headers.get("tracestate", ""),
                }
                parent_ctx = extract(carrier)
                otel_token = otel_context.attach(parent_ctx)
                reset_token = _trace_context_var.set(parent_ctx)
                trace_id = _extract_trace_id_from_context(parent_ctx)
            except Exception as exc:
                logger.debug("trace_context_extract_failed", error=str(exc))
                reset_token = _trace_context_var.set(None)

            structlog.contextvars.bind_contextvars(
                request_id=request_id,
                trace_id=trace_id,
                method=request.method,
                path=request.url.path,
            )

            response = await call_next(request)

        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.exception(
                "request_failed",
                duration_ms=duration_ms,
            )
            raise

        finally:
            try:
                if reset_token is not None:
                    _trace_context_var.reset(reset_token)
            except Exception:
                pass

            try:
                if otel_token is not None:
                    from opentelemetry import context as otel_context

                    otel_context.detach(otel_token)
            except Exception:
                pass

            structlog.contextvars.unbind_contextvars(
                "request_id",
                "trace_id",
                "method",
                "path",
            )

        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"
        if trace_id:
            response.headers["X-Trace-ID"] = trace_id

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )

        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        return response


class TrafficGuardMiddleware(BaseHTTPMiddleware):
    """Reject non-exempt traffic when cluster health is critical."""

    def __init__(
        self,
        app: ASGIApp,
        redis_getter: Callable[[], Awaitable[Any]],
    ) -> None:
        super().__init__(app)
        self._get_redis = redis_getter
        self._last_check = 0.0
        self._cached_health: str | None = None

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        if self._is_exempt(path):
            return await call_next(request)

        now = time.time()
        if now - self._last_check > 1.0 or self._cached_health is None:
            try:
                redis = await self._get_redis()
                health = await redis.get("butler:cluster:health")

                if isinstance(health, bytes):
                    self._cached_health = health.decode("utf-8", errors="ignore")
                elif isinstance(health, str):
                    self._cached_health = health
                else:
                    self._cached_health = "HEALTHY"

                self._last_check = now
            except Exception as exc:
                logger.warning("traffic_guard_health_check_failed", error=str(exc))
                self._cached_health = "HEALTHY"

        if self._cached_health == "CRITICAL":
            from fastapi.responses import JSONResponse

            from core.errors import ServiceUnavailableProblem

            problem = ServiceUnavailableProblem(
                detail="System under critical load. Traffic shedding in effect."
            )
            return JSONResponse(
                status_code=503,
                content=problem.to_dict(instance=path),
                headers={"Retry-After": "30"},
            )

        return await call_next(request)

    def _is_exempt(self, path: str) -> bool:
        return path.startswith(("/api/v1/health/", "/admin/", "/.well-known/", "/internal/"))


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Resolve and propagate tenant context from JWT/session.

    Creates immutable TenantContext from validated JWT.
    Sets tenant context in request.state and context variable.
    Client cannot override tenant identity - gateway sets it only.
    """

    def __init__(
        self,
        app: ASGIApp,
        tenant_resolver_getter: Callable[[], Any],
    ) -> None:
        super().__init__(app)
        self._get_tenant_resolver = tenant_resolver_getter

    async def dispatch(self, request: Request, call_next) -> Response:
        """Resolve tenant context and propagate through request."""
        # Skip tenant resolution for exempt paths (health, public endpoints)
        if self._is_exempt(request.url.path):
            return await call_next(request)

        tenant_context_token: Any = None
        tenant_context = None

        try:
            # Get JWT payload from request state (set by auth middleware)
            jwt_payload = getattr(request.state, "jwt_payload", None)

            if jwt_payload:
                # Resolve tenant context from JWT
                tenant_resolver = self._get_tenant_resolver()
                request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

                tenant_context = await tenant_resolver.resolve_from_jwt(
                    jwt_payload=jwt_payload,
                    request_id=request_id,
                )

                # Set in request state for downstream access
                request.state.tenant_context = tenant_context

                # Set in context variable for async propagation
                tenant_context_token = _tenant_context_var.set(tenant_context)

                # Bind to structlog for consistent logging
                structlog.contextvars.bind_contextvars(
                    tenant_id=tenant_context.tenant_id,
                    account_id=tenant_context.account_id,
                    plan=tenant_context.plan,
                )

            response = await call_next(request)

        except Exception as exc:
            logger.exception(
                "tenant_context_resolution_failed",
                error=str(exc),
                path=request.url.path,
            )
            # If tenant context resolution fails, reject request
            from fastapi.responses import JSONResponse

            from core.errors import ForbiddenProblem

            problem = ForbiddenProblem(detail="Failed to resolve tenant context")
            return JSONResponse(
                status_code=403,
                content=problem.to_dict(instance=request.url.path),
            )

        finally:
            # Cleanup context variable
            if tenant_context_token is not None:
                _tenant_context_var.reset(tenant_context_token)

            if tenant_context is not None:
                structlog.contextvars.unbind_contextvars(
                    "tenant_id",
                    "account_id",
                    "plan",
                )

        return response

    def _is_exempt(self, path: str) -> bool:
        """Paths exempt from tenant context resolution."""
        return path.startswith(
            ("/api/v1/health/", "/api/v1/public/", "/.well-known/", "/internal/")
        )


class RuntimeContextMiddleware(BaseHTTPMiddleware):
    """
    Create and propagate canonical RuntimeContext from request state.

    RuntimeContext is the canonical runtime context carrying tenant_id, account_id,
    session_id, request_id, trace_id, workflow_id, task_id, agent_id, channel, locale,
    timezone, permissions, roles, region, cell, environment, and metadata.

    Rule: No RuntimeContext = no tool execution, no memory access, no model call,
    no workflow execution.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Create RuntimeContext from request state and propagate through request."""
        runtime_context_token: Any = None
        runtime_context = None

        try:
            # Get tenant context from request state (set by TenantContextMiddleware)
            tenant_context = getattr(request.state, "tenant_context", None)

            # Get request_id and trace_id from request state (set by RequestContextMiddleware)
            request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
            trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))

            # Get session_id from JWT payload if available
            jwt_payload = getattr(request.state, "jwt_payload", None)
            session_id = None
            if jwt_payload and isinstance(jwt_payload, dict):
                session_id = jwt_payload.get("session_id")

            # Get user_id from JWT payload if available
            user_id = None
            if jwt_payload and isinstance(jwt_payload, dict):
                user_id = jwt_payload.get("sub")

            # Get channel from request headers or default to "api"
            channel = request.headers.get("X-Channel", "api")

            # Get locale and timezone from request headers or defaults
            locale = request.headers.get("X-Locale", "en")
            timezone = request.headers.get("X-Timezone", "UTC")

            # Get region and cell from environment or defaults
            import os

            region = os.getenv("BUTLER_REGION", "default")
            cell = os.getenv("BUTLER_CELL", "default")
            environment = os.getenv("BUTLER_ENVIRONMENT", "production")

            # Extract permissions and roles from tenant context if available
            permissions = frozenset()
            roles = frozenset()
            if tenant_context:
                permissions = getattr(tenant_context, "permissions", frozenset())
                roles = getattr(tenant_context, "roles", frozenset())

            # Create RuntimeContext
            from domain.runtime.context import RuntimeContext

            if tenant_context:
                runtime_context = RuntimeContext.create(
                    tenant_id=tenant_context.tenant_id,
                    account_id=tenant_context.account_id,
                    session_id=session_id or request_id,  # Fallback to request_id
                    request_id=request_id,
                    trace_id=trace_id,
                    user_id=user_id,
                    channel=channel,
                    locale=locale,
                    timezone=timezone,
                    permissions=permissions,
                    roles=roles,
                    region=region,
                    cell=cell,
                    environment=environment,
                )

                # Set in request state for downstream access
                request.state.runtime_context = runtime_context

                # Set in context variable for async propagation
                runtime_context_token = _runtime_context_var.set(runtime_context)

                # Bind to structlog for consistent logging
                structlog.contextvars.bind_contextvars(
                    tenant_id=runtime_context.tenant_id,
                    account_id=runtime_context.account_id,
                    session_id=runtime_context.session_id,
                )

            response = await call_next(request)

        except Exception as exc:
            logger.exception(
                "runtime_context_creation_failed",
                error=str(exc),
                path=request.url.path,
            )
            # If runtime context creation fails, reject request
            from fastapi.responses import JSONResponse

            from core.errors import ForbiddenProblem

            problem = ForbiddenProblem(detail="Failed to create runtime context")
            return JSONResponse(
                status_code=403,
                content=problem.to_dict(instance=request.url.path),
            )

        finally:
            # Cleanup context variable
            if runtime_context_token is not None:
                _runtime_context_var.reset(runtime_context_token)

            if runtime_context is not None:
                structlog.contextvars.unbind_contextvars(
                    "tenant_id",
                    "account_id",
                    "session_id",
                )

        return response
