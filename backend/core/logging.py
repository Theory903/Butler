"""Structured logging with OpenTelemetry trace context injection.

Every log entry automatically includes trace_id and span_id so logs
can be correlated with distributed traces in Grafana/Loki.
"""

from __future__ import annotations

import logging
import sys

import structlog
from opentelemetry import trace


def add_trace_context(
    logger: logging.Logger,  # noqa: ARG001
    method_name: str,  # noqa: ARG001
    event_dict: dict,
) -> dict:
    """Inject OpenTelemetry trace context into every log entry."""
    span = trace.get_current_span()
    if span and span.is_recording():
        ctx = span.get_span_context()
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict


def setup_logging(service_name: str, environment: str) -> None:
    """Configure structlog with JSON output + OTel trace context.

    Call once at application startup in lifespan handler.
    """
    log_level = logging.DEBUG if environment == "development" else logging.INFO

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        add_trace_context,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
    ]

    if environment == "development":
        # Pretty-print in dev
        renderer = structlog.dev.ConsoleRenderer()
    else:
        # JSON in production
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Bind service-level context that appears on every log entry
    structlog.contextvars.bind_contextvars(
        service=service_name,
        environment=environment,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a named structlog logger."""
    return structlog.get_logger(name)
