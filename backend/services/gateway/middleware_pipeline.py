"""
Middleware Pipeline - Request/Response Processing Chain

Implements a composable middleware pipeline for request/response processing.
Supports tenant context, auth, rate limiting, logging, and custom middleware.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class MiddlewarePhase(StrEnum):
    """Middleware execution phases."""

    PRE_AUTH = "pre_auth"
    POST_AUTH = "post_auth"
    PRE_REQUEST = "pre_request"
    POST_REQUEST = "post_request"
    PRE_RESPONSE = "pre_response"
    POST_RESPONSE = "post_response"


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Request context passed through middleware pipeline."""

    request_id: str
    tenant_id: str | None
    user_id: str | None
    ip_address: str | None
    user_agent: str | None
    path: str
    method: str
    timestamp: datetime
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ResponseContext:
    """Response context passed through middleware pipeline."""

    request_id: str
    status_code: int
    duration_ms: float
    timestamp: datetime
    metadata: dict[str, Any]


class Middleware:
    """Base middleware class."""

    def __init__(
        self,
        name: str,
        phase: MiddlewarePhase,
    ) -> None:
        """Initialize middleware."""
        self._name = name
        self._phase = phase

    @property
    def name(self) -> str:
        """Get middleware name."""
        return self._name

    @property
    def phase(self) -> MiddlewarePhase:
        """Get middleware phase."""
        return self._phase

    async def process_request(
        self,
        context: RequestContext,
    ) -> RequestContext | None:
        """
        Process incoming request.

        Args:
            context: Request context

        Returns:
            Updated context or None to reject request
        """
        return context

    async def process_response(
        self,
        context: ResponseContext,
    ) -> ResponseContext:
        """
        Process outgoing response.

        Args:
            context: Response context

        Returns:
            Updated response context
        """
        return context


class MiddlewarePipeline:
    """
    Composable middleware pipeline.

    Features:
    - Phase-based middleware execution
    - Request/response processing
    - Tenant context propagation
    - Error handling
    """

    def __init__(self) -> None:
        """Initialize middleware pipeline."""
        self._middlewares: dict[MiddlewarePhase, list[Middleware]] = {
            phase: [] for phase in MiddlewarePhase
        }

    def add_middleware(
        self,
        middleware: Middleware,
    ) -> None:
        """
        Add middleware to pipeline.

        Args:
            middleware: Middleware to add
        """
        self._middlewares[middleware.phase].append(middleware)

        logger.debug(
            "middleware_added",
            name=middleware.name,
            phase=middleware.phase,
        )

    def remove_middleware(self, name: str) -> None:
        """
        Remove middleware from pipeline.

        Args:
            name: Middleware name
        """
        for phase, middlewares in self._middlewares.items():
            self._middlewares[phase] = [m for m in middlewares if m.name != name]

            logger.debug(
                "middleware_removed",
                name=name,
                phase=phase,
            )

    async def process_request(
        self,
        context: RequestContext,
        phase: MiddlewarePhase,
    ) -> RequestContext | None:
        """
        Process request through middleware for a specific phase.

        Args:
            context: Request context
            phase: Middleware phase

        Returns:
            Updated context or None to reject request
        """
        current_context: RequestContext | None = context
        for middleware in self._middlewares[phase]:
            try:
                if current_context is None:
                    return None
                current_context = await middleware.process_request(current_context)
                if current_context is None:
                    logger.warning(
                        "middleware_rejected_request",
                        middleware=middleware.name,
                        phase=phase,
                    )
                    return None
            except Exception as e:
                logger.exception(
                    "middleware_request_error",
                    middleware=middleware.name,
                    phase=phase,
                    error=str(e),
                )
                # Continue processing other middleware on error
                continue

        return current_context

    async def process_response(
        self,
        context: ResponseContext,
        phase: MiddlewarePhase,
    ) -> ResponseContext:
        """
        Process response through middleware for a specific phase.

        Args:
            context: Response context
            phase: Middleware phase

        Returns:
            Updated response context
        """
        for middleware in self._middlewares[phase]:
            try:
                context = await middleware.process_response(context)
            except Exception as e:
                logger.exception(
                    "middleware_response_error",
                    middleware=middleware.name,
                    phase=phase,
                    error=str(e),
                )
                # Continue processing other middleware on error
                continue

        return context

    async def process_full_request(
        self,
        context: RequestContext,
    ) -> RequestContext | None:
        """
        Process request through all request phases.

        Args:
            context: Request context

        Returns:
            Updated context or None to reject request
        """
        # Pre-auth phase
        context = await self.process_request(context, MiddlewarePhase.PRE_AUTH)
        if context is None:
            return None

        # Post-auth phase
        context = await self.process_request(context, MiddlewarePhase.POST_AUTH)
        if context is None:
            return None

        # Pre-request phase
        context = await self.process_request(context, MiddlewarePhase.PRE_REQUEST)
        if context is None:
            return None

        return context

    async def process_full_response(
        self,
        context: ResponseContext,
    ) -> ResponseContext:
        """
        Process response through all response phases.

        Args:
            context: Response context

        Returns:
            Updated response context
        """
        # Post-request phase
        context = await self.process_response(context, MiddlewarePhase.POST_REQUEST)

        # Pre-response phase
        context = await self.process_response(context, MiddlewarePhase.PRE_RESPONSE)

        # Post-response phase
        return await self.process_response(context, MiddlewarePhase.POST_RESPONSE)

    def get_middleware_count(self) -> int:
        """Get total number of middleware."""
        return sum(len(m) for m in self._middlewares.values())

    def get_middleware_by_phase(self) -> dict[MiddlewarePhase, list[str]]:
        """Get middleware names by phase."""
        return {
            phase: [m.name for m in middlewares] for phase, middlewares in self._middlewares.items()
        }


class LoggingMiddleware(Middleware):
    """Logging middleware for request/response tracking."""

    def __init__(self) -> None:
        """Initialize logging middleware."""
        super().__init__("logging", MiddlewarePhase.PRE_REQUEST)

    async def process_request(
        self,
        context: RequestContext,
    ) -> RequestContext | None:
        """Log incoming request."""
        logger.info(
            "request_received",
            request_id=context.request_id,
            tenant_id=context.tenant_id,
            path=context.path,
            method=context.method,
            ip_address=context.ip_address,
        )
        return context


class TenantContextMiddleware(Middleware):
    """Tenant context middleware for multi-tenancy."""

    def __init__(self) -> None:
        """Initialize tenant context middleware."""
        super().__init__("tenant_context", MiddlewarePhase.POST_AUTH)

    async def process_request(
        self,
        context: RequestContext,
    ) -> RequestContext | None:
        """Ensure tenant context is present."""
        if not context.tenant_id:
            logger.warning(
                "request_missing_tenant_id",
                request_id=context.request_id,
            )
            return None

        logger.debug(
            "tenant_context_verified",
            request_id=context.request_id,
            tenant_id=context.tenant_id,
        )

        return context


class RequestTimingMiddleware(Middleware):
    """Request timing middleware for performance tracking."""

    def __init__(self) -> None:
        """Initialize request timing middleware."""
        super().__init__("timing", MiddlewarePhase.PRE_REQUEST)

    async def process_request(
        self,
        context: RequestContext,
    ) -> RequestContext | None:
        """Record request start time."""
        metadata = dict(context.metadata)
        metadata["start_time"] = datetime.now(UTC).isoformat()

        return RequestContext(
            request_id=context.request_id,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            path=context.path,
            method=context.method,
            timestamp=context.timestamp,
            metadata=metadata,
        )


class SecurityHeadersMiddleware(Middleware):
    """Security headers middleware for response."""

    def __init__(self) -> None:
        """Initialize security headers middleware."""
        super().__init__("security_headers", MiddlewarePhase.PRE_RESPONSE)

    async def process_response(
        self,
        context: ResponseContext,
    ) -> ResponseContext:
        """Add security headers to response."""
        metadata = dict(context.metadata)
        metadata["security_headers"] = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'",
        }

        return ResponseContext(
            request_id=context.request_id,
            status_code=context.status_code,
            duration_ms=context.duration_ms,
            timestamp=context.timestamp,
            metadata=metadata,
        )
