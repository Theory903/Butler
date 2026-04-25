from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Canonical event taxonomy
# ---------------------------------------------------------------------------


class TwinEventType(StrEnum):
    """Canonical event types for Butler memory and digital twin projection.

    These events are append-only facts about what happened in the system.
    The projector consumes these events to materialize the runtime twin.
    """

    # Session / conversation lifecycle
    CONVERSATION_TURN_RECORDED = "conversation.turn.recorded"
    SESSION_SUMMARY_UPDATED = "session.summary.updated"
    EPISODE_CAPTURED = "episode.captured"

    # Semantic memory evolution
    SEMANTIC_FACT_CREATED = "semantic.fact.created"
    SEMANTIC_FACT_REINFORCED = "semantic.fact.reinforced"
    SEMANTIC_FACT_SUPERSEDED = "semantic.fact.superseded"
    SEMANTIC_FACT_CONTRADICTED = "semantic.fact.contradicted"

    # User preference / dislike / constraint memory
    PREFERENCE_UPDATED = "preference.updated"
    DISLIKE_UPDATED = "dislike.updated"
    CONSTRAINT_UPDATED = "constraint.updated"

    # Entity / graph / relationship layer
    ENTITY_RESOLVED = "entity.resolved"
    RELATIONSHIP_CREATED = "relationship.created"
    RELATIONSHIP_UPDATED = "relationship.updated"

    # Behavioral / style / personalization
    TOPIC_SIGNAL_OBSERVED = "topic.signal.observed"
    LANGUAGE_SIGNAL_OBSERVED = "language.signal.observed"
    COMMUNICATION_STYLE_OBSERVED = "communication.style.observed"
    SPELLING_PATTERN_OBSERVED = "spelling.pattern.observed"

    # Ingestion surfaces
    DOCUMENT_INGESTED = "document.ingested"
    WEB_CHUNK_INGESTED = "web_chunk.ingested"
    EMAIL_CHUNK_INGESTED = "email_chunk.ingested"
    MEETING_CHUNK_INGESTED = "meeting_chunk.ingested"

    # Multimodal / biometric
    VOICE_SIGNAL_DERIVED = "voice.signal.derived"
    FACE_SIGNAL_DERIVED = "face.signal.derived"

    # Consent / privacy / lifecycle control
    CONSENT_POLICY_UPDATED = "consent.policy.updated"
    MEMORY_REDACTED = "memory.redacted"
    MEMORY_FORGOTTEN = "memory.forgotten"
    MEMORY_RETENTION_EXPIRED = "memory.retention.expired"


# ---------------------------------------------------------------------------
# Source / confidence enums
# ---------------------------------------------------------------------------


class SourceKind(StrEnum):
    """Top-level source family that produced an event."""

    CHAT = "chat"
    VOICE = "voice"
    VISION = "vision"
    TOOL = "tool"
    IMPORT = "import"
    WEB = "web"
    DOCUMENT = "document"
    EMAIL = "email"
    MEETING = "meeting"
    SYSTEM = "system"


class ConfidenceLevel(StrEnum):
    """Epistemic confidence classification for an event."""

    EXPLICIT = "explicit"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ConfidenceTier(StrEnum):
    """Operational access/usage tier for a fact or signal.

    This is intentionally separate from ConfidenceLevel:
    - ConfidenceLevel = how sure we are
    - ConfidenceTier = how broadly the system may rely on the signal
    """

    OPERATIONAL = "operational"
    ENHANCED = "enhanced"
    RESTRICTED = "restricted"
    TRAINING = "training"


# ---------------------------------------------------------------------------
# Immutable shared twin value object
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class TwinField:
    """Immutable twin field snapshot with temporal and provenance metadata.

    This is a lightweight value object for internal composition. The richer
    persistent projection models should use Pydantic models, but this remains
    useful where immutability is desirable.
    """

    value: Any
    confidence: float
    source_type: str
    first_observed_at: datetime
    last_confirmed_at: datetime
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    source_refs: list[str] = field(default_factory=list)
    conflicts_with: list[str] = field(default_factory=list)
    superseded_by: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        if not self.source_type or not self.source_type.strip():
            raise ValueError("source_type must not be empty")
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until cannot be earlier than valid_from")


# ---------------------------------------------------------------------------
# Provenance reference types
# ---------------------------------------------------------------------------


class TwinReference(BaseModel):
    """Reference to a source object or related memory artifact."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1)
    id: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind", "id")
    @classmethod
    def _normalize_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("field must not be empty")
        return cleaned


class ProvenanceAgent(BaseModel):
    """Agent, service, human, or model that produced the event."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1)
    id: str = Field(min_length=1)
    display_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind", "id")
    @classmethod
    def _normalize_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("field must not be empty")
        return cleaned

    @field_validator("display_name")
    @classmethod
    def _normalize_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ProvenanceActivity(BaseModel):
    """The activity or workflow step that generated the event."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1)
    id: str = Field(min_length=1)
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind", "id")
    @classmethod
    def _normalize_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("field must not be empty")
        return cleaned

    @field_validator("description")
    @classmethod
    def _normalize_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class EventProvenance(BaseModel):
    """W3C-PROV-inspired provenance record for twin events."""

    model_config = ConfigDict(extra="forbid")

    source_kind: SourceKind
    source_refs: list[TwinReference] = Field(default_factory=list)
    agent: ProvenanceAgent | None = None
    activity: ProvenanceActivity | None = None
    derived_from: list[TwinReference] = Field(default_factory=list)

    confidence_level: ConfidenceLevel = ConfidenceLevel.MEDIUM
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence_tier: ConfidenceTier = ConfidenceTier.OPERATIONAL

    is_sensitive: bool = False
    contains_biometrics: bool = False

    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_provenance(self) -> EventProvenance:
        if self.contains_biometrics and not self.is_sensitive:
            self.is_sensitive = True
        return self


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def now_utc() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def normalize_confidence_score(value: Any, default: float = 0.5) -> float:
    """Clamp arbitrary numeric input into [0.0, 1.0]."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = default
    return max(0.0, min(1.0, numeric))


def unique_reference_ids(refs: list[TwinReference]) -> list[str]:
    """Return stable deduplicated ids from a reference list."""
    seen: set[str] = set()
    ordered: list[str] = []

    for ref in refs:
        ref_id = ref.id.strip()
        if not ref_id or ref_id in seen:
            continue
        seen.add(ref_id)
        ordered.append(ref_id)

    return ordered


def make_system_provenance(
    *,
    source_kind: SourceKind = SourceKind.SYSTEM,
    confidence_level: ConfidenceLevel = ConfidenceLevel.HIGH,
    confidence_score: float = 1.0,
    confidence_tier: ConfidenceTier = ConfidenceTier.OPERATIONAL,
    metadata: dict[str, Any] | None = None,
) -> EventProvenance:
    """Convenience constructor for internal/system-generated provenance."""
    return EventProvenance(
        source_kind=source_kind,
        confidence_level=confidence_level,
        confidence_score=normalize_confidence_score(confidence_score, default=1.0),
        confidence_tier=confidence_tier,
        metadata=metadata or {},
    )
