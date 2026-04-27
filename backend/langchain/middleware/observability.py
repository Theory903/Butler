"""Observability middleware for LangChain agents.

Integrates with Butler's metrics and OpenTelemetry for tracing.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from langchain.middleware.base import (
    ButlerBaseMiddleware,
    ButlerMiddlewareContext,
    MiddlewareResult,
)

import structlog

logger = structlog.get_logger(__name__)


class ObservabilityMiddleware(ButlerBaseMiddleware):
    """Middleware for observability and tracing.

    This middleware:
    - Tracks latency for model and tool operations
    - Integrates with Butler's ButlerMetrics
    - Integrates with OpenTelemetry tracing
    - Tracks success rates and error rates
    - Emits structured logs for observability
    - Runs at all hooks (PRE_MODEL, POST_MODEL, PRE_TOOL, POST_TOOL)

    Production integration (Phase B.6):
    - Real metrics integration with ButlerMetrics
    - OpenTelemetry span creation
    - Structured logging with correlation IDs
    - Performance tracking
    """

    def __init__(
        self,
        enabled: bool = True,
        metrics: Any = None,
        tracer: Any = None,
        track_latency: bool = True,
        track_errors: bool = True,
    ):
        """Initialize observability middleware.

        Args:
            enabled: Whether middleware is enabled
            metrics: Butler's ButlerMetrics instance
            tracer: OpenTelemetry tracer
            track_latency: Whether to track operation latency
            track_errors: Whether to track error rates
        """
        super().__init__(enabled=enabled)
        self._metrics = metrics
        self._tracer = tracer
        self._track_latency = track_latency
        self._track_errors = track_errors

        # Lazy load metrics if not provided
        if self._metrics is None:
            try:
                from core.observability import get_metrics

                self._metrics = get_metrics()
            except ImportError:
                logger.warning("metrics_unavailable")

        # Lazy load tracer if not provided
        if self._tracer is None:
            try:
                from opentelemetry import trace

                self._tracer = trace.get_tracer(__name__)
            except ImportError:
                logger.warning("tracer_unavailable")

    async def pre_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Record start time for model inference.

        Args:
            context: ButlerMiddlewareContext

        Returns:
            MiddlewareResult with timing metadata
        """
        if not self.enabled:
            return MiddlewareResult(success=True, should_continue=True)

        # Record start time
        start_time = time.monotonic()
        context.metadata["_model_start_time"] = start_time

        # Start span if tracer available
        if self._tracer:
            span = self._tracer.start_span(
                name="butler.agent.model.inference",
                attributes={
                    "tenant_id": context.tenant_id,
                    "account_id": context.account_id,
                    "session_id": context.session_id,
                    "trace_id": context.trace_id,
                    "model": context.model or "unknown",
                    "tier": context.tier or "unknown",
                },
            )
            context.metadata["_model_span"] = span

        logger.info(
            "observability_pre_model",
            tenant_id=context.tenant_id,
            session_id=context.session_id,
            model=context.model,
        )

        return MiddlewareResult(success=True, should_continue=True)

    async def post_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Record metrics after model inference.

        Args:
            context: ButlerMiddlewareContext

        Returns:
            MiddlewareResult with metrics metadata
        """
        if not self.enabled:
            return MiddlewareResult(success=True, should_continue=True)

        # Calculate latency
        if self._track_latency:
            start_time = context.metadata.get("_model_start_time")
            if start_time:
                duration_ms = (time.monotonic() - start_time) * 1000
                context.metadata["model_duration_ms"] = duration_ms

                # Record metrics if available
                if self._metrics:
                    self._metrics.record_latency(
                        operation="model_inference",
                        duration_ms=duration_ms,
                        tags={
                            "model": context.model or "unknown",
                            "tier": context.tier or "unknown",
                            "tenant_id": context.tenant_id,
                        },
                    )

        # End span if available
        span = context.metadata.get("_model_span")
        if span:
            span.end()

        # Record success/error metrics
        if self._track_errors:
            error = context.metadata.get("error")
            if error:
                if self._metrics:
                    self._metrics.record_error(
                        operation="model_inference",
                        error_type=type(error).__name__,
                        tags={
                            "model": context.model or "unknown",
                            "tenant_id": context.tenant_id,
                        },
                    )
                logger.warning(
                    "observability_post_model_error",
                    tenant_id=context.tenant_id,
                    error=str(error),
                )
            else:
                if self._metrics:
                    self._metrics.record_success(
                        operation="model_inference",
                        tags={
                            "model": context.model or "unknown",
                            "tenant_id": context.tenant_id,
                        },
                    )

        logger.info(
            "observability_post_model",
            tenant_id=context.tenant_id,
            session_id=context.session_id,
            duration_ms=context.metadata.get("model_duration_ms"),
        )

        return MiddlewareResult(success=True, should_continue=True)

    async def pre_tool(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Record start time for tool execution.

        Args:
            context: ButlerMiddlewareContext

        Returns:
            MiddlewareResult with timing metadata
        """
        if not self.enabled:
            return MiddlewareResult(success=True, should_continue=True)

        # Record start time
        start_time = time.monotonic()
        context.metadata["_tool_start_time"] = start_time

        # Start span if tracer available
        if self._tracer:
            tool_names = [tc.get("name", "unknown") for tc in context.tool_calls]
            span = self._tracer.start_span(
                name="butler.agent.tool.execution",
                attributes={
                    "tenant_id": context.tenant_id,
                    "account_id": context.account_id,
                    "session_id": context.session_id,
                    "trace_id": context.trace_id,
                    "tool_names": ",".join(tool_names),
                },
            )
            context.metadata["_tool_span"] = span

        logger.info(
            "observability_pre_tool",
            tenant_id=context.tenant_id,
            session_id=context.session_id,
            tool_count=len(context.tool_calls),
        )

        return MiddlewareResult(success=True, should_continue=True)

    async def post_tool(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Record metrics after tool execution.

        Args:
            context: ButlerMiddlewareContext

        Returns:
            MiddlewareResult with metrics metadata
        """
        if not self.enabled:
            return MiddlewareResult(success=True, should_continue=True)

        # Calculate latency
        if self._track_latency:
            start_time = context.metadata.get("_tool_start_time")
            if start_time:
                duration_ms = (time.monotonic() - start_time) * 1000
                context.metadata["tool_duration_ms"] = duration_ms

                # Record metrics if available
                if self._metrics:
                    tool_names = [tc.get("name", "unknown") for tc in context.tool_calls]
                    for tool_name in tool_names:
                        self._metrics.record_latency(
                            operation="tool_execution",
                            duration_ms=duration_ms / len(tool_names),
                            tags={
                                "tool_name": tool_name,
                                "tenant_id": context.tenant_id,
                            },
                        )

        # End span if available
        span = context.metadata.get("_tool_span")
        if span:
            span.end()

        # Record success/error metrics
        if self._track_errors:
            for result in context.tool_results:
                if not result.get("success", True):
                    tool_name = result.get("name", "unknown")
                    error = result.get("error", "Unknown error")

                    if self._metrics:
                        self._metrics.record_error(
                            operation="tool_execution",
                            error_type=type(error).__name__
                            if isinstance(error, Exception)
                            else "error",
                            tags={
                                "tool_name": tool_name,
                                "tenant_id": context.tenant_id,
                            },
                        )
                    logger.warning(
                        "observability_post_tool_error",
                        tenant_id=context.tenant_id,
                        tool_name=tool_name,
                        error=str(error),
                    )

        logger.info(
            "observability_post_tool",
            tenant_id=context.tenant_id,
            session_id=context.session_id,
            duration_ms=context.metadata.get("tool_duration_ms"),
            tool_count=len(context.tool_results),
        )

        return MiddlewareResult(success=True, should_continue=True)
