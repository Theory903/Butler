from __future__ import annotations

from uuid import uuid4

import pytest
import structlog.contextvars
from pydantic import ValidationError

from core.logging import setup_logging
from services.memory.twin_events import EventEnvelope, EventFactory, TwinEventType
from services.memory.twin_types import ConfidenceLevel, EventProvenance, SourceKind


@pytest.fixture(autouse=True, scope="session")
def configure_logging():
    setup_logging(service_name="test-memory", environment="development")


@pytest.fixture(autouse=True)
def setup_log():
    # Initialize structlog contextvars if needed
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()


class TestHardenedEvents:
    """Tests for hardened event validation and context propagation."""

    def test_causation_self_referential_check(self):
        """Verify that an event cannot be its own cause."""
        event_id = uuid4()
        user_id = uuid4()

        # This should fail validation
        with pytest.raises(ValidationError) as excinfo:
            EventEnvelope(
                event_id=event_id,
                event_type=TwinEventType.SEMANTIC_FACT_CREATED,
                user_id=user_id,
                causation_id=event_id,
                provenance=EventProvenance(
                    source_kind=SourceKind.SYSTEM,
                    confidence_level=ConfidenceLevel.EXPLICIT,
                    confidence_score=1.0,
                ),
                payload={"test": "data"},
            )
        assert "causation_id cannot be the same as event_id" in str(excinfo.value)

    def test_causal_event_requires_explicit_correlation(self):
        """Verify that causal events (with causation_id) must have explicit correlation_id."""
        causation_id = uuid4()
        user_id = uuid4()

        with pytest.raises(ValidationError) as excinfo:
            EventEnvelope(
                event_type=TwinEventType.SEMANTIC_FACT_CREATED,
                user_id=user_id,
                causation_id=causation_id,
                provenance=EventProvenance(
                    source_kind=SourceKind.SYSTEM,
                    confidence_level=ConfidenceLevel.EXPLICIT,
                    confidence_score=1.0,
                ),
                payload={"test": "data"},
            )
        assert "Causal events must have an explicit correlation_id root" in str(excinfo.value)

    def test_root_correlation_auto_assignment(self):
        """Verify that root events (no causation_id) auto-assign correlation_id to event_id."""
        user_id = uuid4()
        event = EventEnvelope(
            event_type=TwinEventType.SEMANTIC_FACT_CREATED,
            user_id=user_id,
            provenance=EventProvenance(
                source_kind=SourceKind.SYSTEM,
                confidence_level=ConfidenceLevel.EXPLICIT,
                confidence_score=1.0,
            ),
            payload={"test": "data"},
        )
        assert event.causation_id is None
        assert event.correlation_id == event.event_id

    def test_explicit_correlation_not_overwritten(self):
        """Verify that explicit correlation_id is preserved."""
        causation_id = uuid4()
        correlation_id = uuid4()
        user_id = uuid4()

        event = EventEnvelope(
            event_type=TwinEventType.SEMANTIC_FACT_CREATED,
            user_id=user_id,
            causation_id=causation_id,
            correlation_id=correlation_id,
            provenance=EventProvenance(
                source_kind=SourceKind.SYSTEM,
                confidence_level=ConfidenceLevel.EXPLICIT,
                confidence_score=1.0,
            ),
            payload={"test": "data"},
        )

        assert event.causation_id == causation_id
        assert event.correlation_id == correlation_id

    def test_factory_implicit_trace_propagation(self):
        """Verify that EventFactory extracts trace_id from structlog context."""
        trace_id_str = str(uuid4())
        request_id = "req_123"
        span_id = "span_456"

        # Set context
        structlog.contextvars.bind_contextvars(
            trace_id=trace_id_str, request_id=request_id, span_id=span_id
        )

        # Verify context is set
        assert structlog.contextvars.get_contextvars().get("trace_id") == trace_id_str

        event = EventFactory.preference_updated(
            user_id=uuid4(), key="theme", value="dark", domain="ui"
        )

        # Correlation ID should match trace_id
        assert str(event.correlation_id) == trace_id_str

        # Metadata should be enriched
        assert event.metadata.get("ctx_trace_id") == trace_id_str
        assert event.metadata.get("ctx_request_id") == request_id
        assert event.metadata.get("ctx_span_id") == span_id

    def test_factory_manual_ids_override_context(self):
        """Verify that manual IDs passed to factory override context."""
        ctx_trace_id = str(uuid4())
        manual_correlation_id = uuid4()

        structlog.contextvars.bind_contextvars(trace_id=ctx_trace_id)

        event = EventFactory.preference_updated(
            user_id=uuid4(),
            key="theme",
            value="dark",
            domain="ui",
            correlation_id=manual_correlation_id,
        )

        assert event.correlation_id == manual_correlation_id
        # Metadata still gets context enrichment
        assert event.metadata.get("ctx_trace_id") == ctx_trace_id
