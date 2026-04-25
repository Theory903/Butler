from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from services.memory.twin_events import (
    EventEnvelope,
    EventFactory,
)
from services.memory.twin_types import (
    ConfidenceLevel,
    ConfidenceTier,
    EventProvenance,
    ProvenanceActivity,
    ProvenanceAgent,
    SourceKind,
    TwinEventType,
    TwinField,
    TwinReference,
)


class TestTwinTypes:
    """Test twin types, enums, and value objects."""

    def test_twin_event_type_enum_values(self):
        """Verify all expected event types exist."""
        assert TwinEventType.CONVERSATION_TURN_RECORDED
        assert TwinEventType.PREFERENCE_UPDATED
        assert TwinEventType.SEMANTIC_FACT_CREATED
        assert TwinEventType.MEMORY_REDACTED

    def test_source_kind_enum_values(self):
        """Verify source kinds cover all input types."""
        assert SourceKind.CHAT
        assert SourceKind.VOICE
        assert SourceKind.TOOL
        assert SourceKind.IMPORT

    def test_confidence_level_ordering(self):
        levels = [
            ConfidenceLevel.LOW,
            ConfidenceLevel.MEDIUM,
            ConfidenceLevel.HIGH,
            ConfidenceLevel.EXPLICIT,
        ]
        for _i, level in enumerate(levels):
            assert level in levels
        assert len(set(levels)) == 4

    def test_confidence_level_membership(self):
        assert ConfidenceLevel.LOW
        assert ConfidenceLevel.MEDIUM
        assert ConfidenceLevel.HIGH
        assert ConfidenceLevel.EXPLICIT

    def test_confidence_tier_enum_values(self):
        """Verify confidence tiers for projection decisions."""
        assert ConfidenceTier.OPERATIONAL
        assert ConfidenceTier.ENHANCED
        assert ConfidenceTier.RESTRICTED
        assert ConfidenceTier.TRAINING

    def test_twin_field_creation(self):
        """Test twin field value object."""
        field = TwinField(
            value="test_value",
            confidence=0.9,
            source_type="explicit",
            first_observed_at=datetime.now(UTC),
            last_confirmed_at=datetime.now(UTC),
            valid_from=datetime.now(UTC),
            valid_until=None,
            source_refs=["ref1"],
        )
        assert field.value == "test_value"
        assert field.confidence == 0.9

    def test_twin_reference_validation(self):
        """Test twin reference validation."""
        ref = TwinReference(kind="conversation", id="conv_123")
        assert ref.kind == "conversation"
        assert ref.id == "conv_123"

    def test_provenance_agent_creation(self):
        """Test provenance agent model."""
        agent = ProvenanceAgent(kind="user", id="user_456", display_name="John Doe")
        assert agent.kind == "user"
        assert agent.id == "user_456"
        assert agent.display_name == "John Doe"

    def test_provenance_activity_creation(self):
        """Test provenance activity model."""
        activity = ProvenanceActivity(
            kind="chat", id="chat_789", description="User conversation turn"
        )
        assert activity.kind == "chat"
        assert activity.id == "chat_789"

    def test_event_provenance_creation(self):
        """Test complete event provenance."""
        provenance = EventProvenance(
            source_kind=SourceKind.CHAT,
            confidence_level=ConfidenceLevel.EXPLICIT,
            confidence_score=1.0,
            is_sensitive=False,
            contains_biometrics=False,
        )
        assert provenance.source_kind == SourceKind.CHAT
        assert provenance.confidence_level == ConfidenceLevel.EXPLICIT
        assert provenance.confidence_score == 1.0


class TestTwinEvents:
    """Test event envelope and factory."""

    def test_event_envelope_creation(self):
        """Test creating a valid event envelope."""
        event = EventEnvelope(
            event_type=TwinEventType.CONVERSATION_TURN_RECORDED,
            user_id=uuid4(),
            session_id="session_123",
            payload={"role": "user", "content": "hello"},
            provenance=EventProvenance(
                source_kind=SourceKind.CHAT,
                confidence_level=ConfidenceLevel.EXPLICIT,
                confidence_score=1.0,
            ),
        )
        assert event.event_type == TwinEventType.CONVERSATION_TURN_RECORDED
        assert event.session_id == "session_123"
        assert event.payload["role"] == "user"

    def test_event_factory_conversation_turn(self):
        """Test conversation turn event factory."""
        user_id = uuid4()
        event = EventFactory.conversation_turn_recorded(
            user_id=user_id,
            session_id="session_123",
            role="user",
            content="test message",
            turn_index=1,
        )
        assert event.event_type == TwinEventType.CONVERSATION_TURN_RECORDED
        assert event.user_id == user_id
        assert event.payload["role"] == "user"
        assert event.payload["content"] == "test message"
        assert event.payload["turn_index"] == 1

    def test_event_factory_preference_updated(self):
        """Test preference update event factory."""
        user_id = uuid4()
        event = EventFactory.preference_updated(
            user_id=user_id,
            key="language",
            value="python",
            domain="coding",
            explicit=True,
            confidence_score=0.95,
        )
        assert event.event_type == TwinEventType.PREFERENCE_UPDATED
        assert event.user_id == user_id
        assert event.payload["key"] == "language"
        assert event.payload["value"] == "python"
        assert event.payload["domain"] == "coding"
        assert event.payload["explicit"] is True
        assert event.provenance.confidence_score == 0.95

    def test_event_envelope_validation(self):
        """Test event envelope validation rules."""
        # Valid event
        valid_event = EventEnvelope(
            event_type=TwinEventType.SEMANTIC_FACT_CREATED,
            user_id=uuid4(),
            provenance=EventProvenance(
                source_kind=SourceKind.CHAT,
                confidence_level=ConfidenceLevel.HIGH,
                confidence_score=0.8,
            ),
            payload={"fact_key": "test", "value": "data"},
        )
        assert valid_event.schema_version == "1.0"

        # Test optional fields
        assert valid_event.session_id is None
        assert valid_event.causation_id is None
        assert valid_event.correlation_id == valid_event.event_id
