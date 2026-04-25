"""
Distributed Tracing Service - OpenTelemetry Integration

Provides distributed tracing for request flows across services.
Implements OpenTelemetry-compatible tracing with multi-tenant support.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class SpanKind(StrEnum):
    """Span kinds."""

    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"
    INTERNAL = "internal"


class SpanStatus(StrEnum):
    """Span status."""

    OK = "ok"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class Span:
    """Trace span."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    operation_name: str
    start_time: datetime
    end_time: datetime | None
    duration_ms: float | None
    kind: SpanKind
    status: SpanStatus
    tags: dict[str, Any]
    logs: list[dict[str, Any]]
    tenant_id: str | None


@dataclass(frozen=True, slots=True)
class TraceContext:
    """Trace context for propagation."""

    trace_id: str
    span_id: str
    sampled: bool
    tenant_id: str | None = None


class TracingService:
    """
    Distributed tracing service.

    Features:
    - OpenTelemetry-compatible tracing
    - Multi-tenant trace isolation
    - Span context propagation
    - In-memory storage
    """

    def __init__(self) -> None:
        """Initialize tracing service."""
        self._active_spans: dict[str, Span] = {}
        self._completed_spans: list[Span] = []
        self._max_completed_spans = 10000

    def _generate_id(self) -> str:
        """Generate random span/trace ID."""
        import uuid

        return uuid.uuid4().hex

    def start_span(
        self,
        operation_name: str,
        parent_span_id: str | None = None,
        kind: SpanKind = SpanKind.INTERNAL,
        tenant_id: str | None = None,
        tags: dict[str, Any] | None = None,
    ) -> str:
        """
        Start a new span.

        Args:
            operation_name: Name of the operation
            parent_span_id: Parent span ID
            kind: Span kind
            tenant_id: Tenant UUID
            tags: Span tags

        Returns:
            Span ID
        """
        trace_id = parent_span_id.split("-")[0] if parent_span_id else self._generate_id()
        span_id = f"{trace_id}-{self._generate_id()}"

        span = Span(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            start_time=datetime.now(UTC),
            end_time=None,
            duration_ms=None,
            kind=kind,
            status=SpanStatus.OK,
            tags=tags or {},
            logs=[],
            tenant_id=tenant_id,
        )

        self._active_spans[span_id] = span

        logger.debug(
            "span_started",
            span_id=span_id,
            operation_name=operation_name,
            trace_id=trace_id,
        )

        return span_id

    def end_span(
        self,
        span_id: str,
        status: SpanStatus = SpanStatus.OK,
        tags: dict[str, Any] | None = None,
    ) -> None:
        """
        End a span.

        Args:
            span_id: Span ID
            status: Span status
            tags: Additional tags to add
        """
        if span_id not in self._active_spans:
            return

        span = self._active_spans[span_id]
        end_time = datetime.now(UTC)
        duration_ms = (end_time - span.start_time).total_seconds() * 1000

        completed_span = Span(
            trace_id=span.trace_id,
            span_id=span.span_id,
            parent_span_id=span.parent_span_id,
            operation_name=span.operation_name,
            start_time=span.start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            kind=span.kind,
            status=status,
            tags={**span.tags, **(tags or {})},
            logs=span.logs,
            tenant_id=span.tenant_id,
        )

        # Move to completed spans
        del self._active_spans[span_id]
        self._completed_spans.append(completed_span)

        # Trim completed spans if over limit
        if len(self._completed_spans) > self._max_completed_spans:
            self._completed_spans = self._completed_spans[-self._max_completed_spans :]

        logger.debug(
            "span_ended",
            span_id=span_id,
            operation_name=span.operation_name,
            duration_ms=duration_ms,
            status=status,
        )

    def add_span_tag(
        self,
        span_id: str,
        key: str,
        value: Any,
    ) -> None:
        """
        Add a tag to a span.

        Args:
            span_id: Span ID
            key: Tag key
            value: Tag value
        """
        if span_id in self._active_spans:
            span = self._active_spans[span_id]
            # Create new span with updated tags (immutable)
            self._active_spans[span_id] = Span(
                trace_id=span.trace_id,
                span_id=span.span_id,
                parent_span_id=span.parent_span_id,
                operation_name=span.operation_name,
                start_time=span.start_time,
                end_time=span.end_time,
                duration_ms=span.duration_ms,
                kind=span.kind,
                status=span.status,
                tags={**span.tags, key: str(value)},
                logs=span.logs,
                tenant_id=span.tenant_id,
            )

    def add_span_log(
        self,
        span_id: str,
        log_entry: dict[str, Any],
    ) -> None:
        """
        Add a log entry to a span.

        Args:
            span_id: Span ID
            log_entry: Log entry
        """
        if span_id in self._active_spans:
            span = self._active_spans[span_id]
            log_entry["timestamp"] = datetime.now(UTC).isoformat()
            self._active_spans[span_id] = Span(
                trace_id=span.trace_id,
                span_id=span.span_id,
                parent_span_id=span.parent_span_id,
                operation_name=span.operation_name,
                start_time=span.start_time,
                end_time=span.end_time,
                duration_ms=span.duration_ms,
                kind=span.kind,
                status=span.status,
                tags=span.tags,
                logs=[*span.logs, log_entry],
                tenant_id=span.tenant_id,
            )

    def get_trace(self, trace_id: str) -> list[Span]:
        """
        Get all spans for a trace.

        Args:
            trace_id: Trace ID

        Returns:
            List of spans in the trace
        """
        spans = [span for span in self._completed_spans if span.trace_id == trace_id]

        # Also check active spans
        for span in self._active_spans.values():
            if span.trace_id == trace_id:
                spans.append(span)

        return sorted(spans, key=lambda s: s.start_time)

    def get_tenant_traces(
        self,
        tenant_id: str,
        limit: int = 100,
    ) -> list[Span]:
        """
        Get traces for a tenant.

        Args:
            tenant_id: Tenant UUID
            limit: Maximum number of spans to return

        Returns:
            List of spans for the tenant
        """
        spans = [span for span in self._completed_spans if span.tenant_id == tenant_id]

        return sorted(spans, key=lambda s: s.start_time, reverse=True)[:limit]

    def get_trace_context(
        self,
        span_id: str,
    ) -> TraceContext | None:
        """
        Get trace context for propagation.

        Args:
            span_id: Span ID

        Returns:
            Trace context or None
        """
        span = self._active_spans.get(span_id)
        if not span:
            return None

        return TraceContext(
            trace_id=span.trace_id,
            span_id=span.span_id,
            sampled=True,
            tenant_id=span.tenant_id,
        )

    def from_trace_context(
        self,
        context: TraceContext,
    ) -> str:
        """
        Create a new span from trace context.

        Args:
            context: Trace context

        Returns:
            New span ID
        """
        return self.start_span(
            operation_name="child_operation",
            parent_span_id=context.span_id,
            tenant_id=context.tenant_id,
        )

    def export_traces(
        self,
        trace_id: str | None = None,
        tenant_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Export traces in OpenTelemetry format.

        Args:
            trace_id: Specific trace ID to export
            tenant_id: Tenant ID to filter by

        Returns:
            List of exported traces
        """
        spans_to_export = self._completed_spans

        if trace_id:
            spans_to_export = [s for s in spans_to_export if s.trace_id == trace_id]

        if tenant_id:
            spans_to_export = [s for s in spans_to_export if s.tenant_id == tenant_id]

        exported = []
        for span in spans_to_export:
            exported.append(
                {
                    "traceID": span.trace_id,
                    "spanID": span.span_id,
                    "parentSpanID": span.parent_span_id,
                    "operationName": span.operation_name,
                    "startTime": span.start_time.isoformat(),
                    "endTime": span.end_time.isoformat() if span.end_time else None,
                    "duration": span.duration_ms,
                    "kind": span.kind,
                    "status": span.status,
                    "tags": span.tags,
                    "logs": span.logs,
                    "tenantID": span.tenant_id,
                }
            )

        return exported

    def trace_operation(
        self,
        operation_name: str,
        tenant_id: str | None = None,
        kind: SpanKind = SpanKind.INTERNAL,
    ):
        """
        Context manager for tracing an operation.

        Args:
            operation_name: Name of the operation
            tenant_id: Tenant UUID
            kind: Span kind

        Returns:
            Context manager
        """
        from contextlib import contextmanager

        @contextmanager
        def _trace_context():
            span_id = self.start_span(
                operation_name=operation_name,
                kind=kind,
                tenant_id=tenant_id,
            )
            try:
                yield span_id
                self.end_span(span_id, status=SpanStatus.OK)
            except Exception as e:
                self.add_span_log(span_id, {"error": str(e)})
                self.end_span(span_id, status=SpanStatus.ERROR)
                raise

        return _trace_context()

    def get_active_span_count(self) -> int:
        """Get count of active spans."""
        return len(self._active_spans)

    def get_completed_span_count(self) -> int:
        """Get count of completed spans."""
        return len(self._completed_spans)

    def clear_completed_spans(self) -> None:
        """Clear all completed spans."""
        self._completed_spans = []
        logger.info("completed_spans_cleared")
