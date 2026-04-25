from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from services.memory.twin_types import (
    ConfidenceLevel,
    EventProvenance,
    ProvenanceActivity,
    ProvenanceAgent,
    SourceKind,
    TwinEventType,
    TwinReference,
)

_DEFAULT_SCHEMA_VERSION = "1.0"


class EventEnvelope(BaseModel):
    """Canonical immutable Butler memory/twin event envelope."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    event_type: TwinEventType
    user_id: UUID
    session_id: str | None = None

    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    causation_id: UUID | None = None
    correlation_id: UUID | None = None

    provenance: EventProvenance
    payload: dict[str, Any] = Field(default_factory=dict)
    schema_version: str = Field(default=_DEFAULT_SCHEMA_VERSION)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("session_id", "schema_version")
    @classmethod
    def _normalize_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("occurred_at", "recorded_at")
    @classmethod
    def _ensure_tzaware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @field_validator("payload", "metadata")
    @classmethod
    def _ensure_dicts(cls, value: dict[str, Any]) -> dict[str, Any]:
        return dict(value or {})

    @model_validator(mode="after")
    def _validate_temporal_order(self) -> EventEnvelope:
        if self.recorded_at < self.occurred_at:
            raise ValueError("recorded_at must be greater than or equal to occurred_at")
        return self

    @model_validator(mode="after")
    def _validate_causation_chain(self) -> EventEnvelope:
        if self.causation_id == self.event_id:
            raise ValueError("causation_id cannot be the same as event_id")

        if self.causation_id is None:
            # Root event case: must be its own correlation root
            if self.correlation_id is None:
                object.__setattr__(self, "correlation_id", self.event_id)
            elif self.correlation_id != self.event_id:
                # We allow external roots (e.g. from an external trace) but we log it
                # For Butler internal events, we expect correlation == event if it's the root.
                pass
        else:
            # Causal event case: MUST have a correlation root from the parent
            if self.correlation_id is None:
                raise ValueError("Causal events must have an explicit correlation_id root")

            if self.correlation_id == self.event_id:
                raise ValueError("Causal events cannot be their own correlation root")

        return self


class EventFactory:
    """Factory helpers for canonical Butler twin events.

    Design rules:
    - one stable constructor per event type
    - provenance always explicit and structured
    - correlation/causation propagation supported everywhere
    - context-aware provenance extraction (trace_id -> correlation_id)
    - idempotency key can be attached consistently
    """

    @staticmethod
    def conversation_turn_recorded(
        *,
        user_id: UUID,
        session_id: str,
        role: str,
        content: str,
        turn_index: int,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        clean_session_id = EventFactory._required_clean(session_id, "session_id")
        return EventFactory._build_event(
            event_type=TwinEventType.CONVERSATION_TURN_RECORDED,
            user_id=user_id,
            session_id=clean_session_id,
            provenance=EventFactory._chat_provenance(
                source_refs=source_refs,
                explicit=True,
                confidence_score=1.0,
            ),
            payload={
                "role": EventFactory._required_clean(role, "role"),
                "content": EventFactory._required_clean(content, "content"),
                "turn_index": int(turn_index),
                "session_id": clean_session_id,
            },
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def session_summary_updated(
        *,
        user_id: UUID,
        session_id: str,
        summary: str,
        summary_type: str = "anchored",
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        clean_session_id = EventFactory._required_clean(session_id, "session_id")
        return EventFactory._build_event(
            event_type=TwinEventType.SESSION_SUMMARY_UPDATED,
            user_id=user_id,
            session_id=clean_session_id,
            provenance=EventFactory._system_provenance(
                source_kind=SourceKind.SYSTEM,
                source_refs=source_refs,
                confidence_level=ConfidenceLevel.HIGH,
                confidence_score=0.95,
                activity_kind="session_summary_update",
                activity_description="Anchored session summary updated",
            ),
            payload={
                "session_id": clean_session_id,
                "summary": EventFactory._required_clean(summary, "summary"),
                "summary_type": EventFactory._required_clean(summary_type, "summary_type"),
            },
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def episode_captured(
        *,
        user_id: UUID,
        session_id: str | None,
        goal: str | None = None,
        outcome: str | None = None,
        project: str | None = None,
        lessons: list[str] | None = None,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        payload: dict[str, Any] = {
            "goal": EventFactory._clean_optional(goal),
            "outcome": EventFactory._clean_optional(outcome),
            "project": EventFactory._clean_optional(project),
            "lessons": [item.strip() for item in (lessons or []) if item and item.strip()],
        }
        if session_id:
            payload["session_id"] = EventFactory._required_clean(session_id, "session_id")

        return EventFactory._build_event(
            event_type=TwinEventType.EPISODE_CAPTURED,
            user_id=user_id,
            session_id=EventFactory._clean_optional(session_id),
            provenance=EventFactory._system_provenance(
                source_kind=SourceKind.SYSTEM,
                source_refs=source_refs,
                confidence_level=ConfidenceLevel.HIGH,
                confidence_score=0.9,
                activity_kind="episode_capture",
                activity_description="Session distilled into episode memory",
            ),
            payload=payload,
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def semantic_fact_created(
        *,
        user_id: UUID,
        fact_key: str,
        value: Any,
        explicit: bool = False,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
        source_kind: SourceKind = SourceKind.SYSTEM,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        confidence_score: float = 0.75,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        payload: dict[str, Any] = {
            "fact_key": EventFactory._required_clean(fact_key, "fact_key"),
            "value": value,
        }
        if valid_from is not None:
            payload["valid_from"] = EventFactory._normalize_dt(valid_from).isoformat()
        if valid_until is not None:
            payload["valid_until"] = EventFactory._normalize_dt(valid_until).isoformat()

        return EventFactory._build_event(
            event_type=TwinEventType.SEMANTIC_FACT_CREATED,
            user_id=user_id,
            session_id=session_id,
            provenance=EventFactory._generic_provenance(
                source_kind=source_kind,
                source_refs=source_refs,
                confidence_level=(ConfidenceLevel.EXPLICIT if explicit else ConfidenceLevel.HIGH),
                confidence_score=confidence_score,
            ),
            payload=payload,
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def semantic_fact_reinforced(
        *,
        user_id: UUID,
        fact_key: str,
        source_kind: SourceKind = SourceKind.SYSTEM,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        confidence_score: float = 0.8,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        return EventFactory._build_event(
            event_type=TwinEventType.SEMANTIC_FACT_REINFORCED,
            user_id=user_id,
            session_id=session_id,
            provenance=EventFactory._generic_provenance(
                source_kind=source_kind,
                source_refs=source_refs,
                confidence_level=ConfidenceLevel.HIGH,
                confidence_score=confidence_score,
            ),
            payload={"fact_key": EventFactory._required_clean(fact_key, "fact_key")},
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def semantic_fact_superseded(
        *,
        user_id: UUID,
        fact_key: str,
        new_value: Any,
        reason: str | None = None,
        source_kind: SourceKind = SourceKind.SYSTEM,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        confidence_score: float = 0.85,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        payload = {
            "fact_key": EventFactory._required_clean(fact_key, "fact_key"),
            "new_value": new_value,
            "reason": EventFactory._clean_optional(reason),
        }

        return EventFactory._build_event(
            event_type=TwinEventType.SEMANTIC_FACT_SUPERSEDED,
            user_id=user_id,
            session_id=session_id,
            provenance=EventFactory._generic_provenance(
                source_kind=source_kind,
                source_refs=source_refs,
                confidence_level=ConfidenceLevel.HIGH,
                confidence_score=confidence_score,
            ),
            payload=payload,
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def semantic_fact_contradicted(
        *,
        user_id: UUID,
        fact_key: str,
        reason: str | None = None,
        source_kind: SourceKind = SourceKind.SYSTEM,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        confidence_score: float = 0.75,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        return EventFactory._build_event(
            event_type=TwinEventType.SEMANTIC_FACT_CONTRADICTED,
            user_id=user_id,
            session_id=session_id,
            provenance=EventFactory._generic_provenance(
                source_kind=source_kind,
                source_refs=source_refs,
                confidence_level=ConfidenceLevel.MEDIUM,
                confidence_score=confidence_score,
            ),
            payload={
                "fact_key": EventFactory._required_clean(fact_key, "fact_key"),
                "reason": EventFactory._clean_optional(reason),
            },
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def preference_updated(
        *,
        user_id: UUID,
        key: str,
        value: Any,
        domain: str | None = None,
        explicit: bool = True,
        confidence_score: float = 0.9,
        source_kind: SourceKind = SourceKind.CHAT,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        return EventFactory._build_event(
            event_type=TwinEventType.PREFERENCE_UPDATED,
            user_id=user_id,
            session_id=session_id,
            provenance=EventFactory._generic_provenance(
                source_kind=source_kind,
                source_refs=source_refs,
                confidence_level=(ConfidenceLevel.EXPLICIT if explicit else ConfidenceLevel.HIGH),
                confidence_score=confidence_score,
            ),
            payload={
                "key": EventFactory._required_clean(key, "key"),
                "value": value,
                "domain": EventFactory._required_clean((domain or "general"), "domain"),
                "explicit": explicit,
            },
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def dislike_updated(
        *,
        user_id: UUID,
        key: str,
        value: Any = True,
        explicit: bool = True,
        reason: str | None = None,
        confidence_score: float = 0.9,
        source_kind: SourceKind = SourceKind.CHAT,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        return EventFactory._build_event(
            event_type=TwinEventType.DISLIKE_UPDATED,
            user_id=user_id,
            session_id=session_id,
            provenance=EventFactory._generic_provenance(
                source_kind=source_kind,
                source_refs=source_refs,
                confidence_level=(ConfidenceLevel.EXPLICIT if explicit else ConfidenceLevel.HIGH),
                confidence_score=confidence_score,
            ),
            payload={
                "key": EventFactory._required_clean(key, "key"),
                "value": value,
                "reason": EventFactory._clean_optional(reason),
                "explicit": explicit,
            },
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def constraint_updated(
        *,
        user_id: UUID,
        key: str,
        value: Any,
        explicit: bool = True,
        constraint_type: str = "soft",
        reason: str | None = None,
        confidence_score: float = 0.95,
        source_kind: SourceKind = SourceKind.CHAT,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        return EventFactory._build_event(
            event_type=TwinEventType.CONSTRAINT_UPDATED,
            user_id=user_id,
            session_id=session_id,
            provenance=EventFactory._generic_provenance(
                source_kind=source_kind,
                source_refs=source_refs,
                confidence_level=(ConfidenceLevel.EXPLICIT if explicit else ConfidenceLevel.HIGH),
                confidence_score=confidence_score,
            ),
            payload={
                "key": EventFactory._required_clean(key, "key"),
                "value": value,
                "explicit": explicit,
                "type": EventFactory._required_clean(constraint_type, "constraint_type"),
                "reason": EventFactory._clean_optional(reason),
            },
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def entity_resolved(
        *,
        user_id: UUID,
        entity_id: str,
        entity_type: str,
        canonical_name: str,
        alias: str | None = None,
        summary: str | None = None,
        confidence_score: float = 0.8,
        source_kind: SourceKind = SourceKind.SYSTEM,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        payload = {
            "entity_id": EventFactory._required_clean(entity_id, "entity_id"),
            "entity_type": EventFactory._required_clean(entity_type, "entity_type"),
            "canonical_name": EventFactory._required_clean(canonical_name, "canonical_name"),
            "alias": EventFactory._clean_optional(alias),
            "summary": EventFactory._clean_optional(summary),
        }

        return EventFactory._build_event(
            event_type=TwinEventType.ENTITY_RESOLVED,
            user_id=user_id,
            session_id=session_id,
            provenance=EventFactory._generic_provenance(
                source_kind=source_kind,
                source_refs=source_refs,
                confidence_level=ConfidenceLevel.HIGH,
                confidence_score=confidence_score,
            ),
            payload=payload,
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def relationship_created(
        *,
        user_id: UUID,
        source_entity_id: str,
        target_entity_id: str,
        relation_type: str,
        strength: float = 0.7,
        confidence_score: float = 0.85,
        source_kind: SourceKind = SourceKind.SYSTEM,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        return EventFactory._relationship_event(
            event_type=TwinEventType.RELATIONSHIP_CREATED,
            user_id=user_id,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            relation_type=relation_type,
            strength=strength,
            confidence_score=confidence_score,
            source_kind=source_kind,
            source_refs=source_refs,
            metadata=metadata,
            session_id=session_id,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def relationship_updated(
        *,
        user_id: UUID,
        source_entity_id: str,
        target_entity_id: str,
        relation_type: str,
        strength: float = 0.7,
        confidence_score: float = 0.85,
        source_kind: SourceKind = SourceKind.SYSTEM,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        return EventFactory._relationship_event(
            event_type=TwinEventType.RELATIONSHIP_UPDATED,
            user_id=user_id,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            relation_type=relation_type,
            strength=strength,
            confidence_score=confidence_score,
            source_kind=source_kind,
            source_refs=source_refs,
            metadata=metadata,
            session_id=session_id,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def topic_signal_observed(
        *,
        user_id: UUID,
        topic: str,
        strength: float = 0.5,
        confidence_score: float = 0.75,
        source_kind: SourceKind = SourceKind.CHAT,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        return EventFactory._build_event(
            event_type=TwinEventType.TOPIC_SIGNAL_OBSERVED,
            user_id=user_id,
            session_id=session_id,
            provenance=EventFactory._generic_provenance(
                source_kind=source_kind,
                source_refs=source_refs,
                confidence_level=ConfidenceLevel.HIGH,
                confidence_score=confidence_score,
            ),
            payload={
                "topic": EventFactory._required_clean(topic, "topic").lower(),
                "strength": EventFactory._clamp_float(strength),
            },
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def language_signal_observed(
        *,
        user_id: UUID,
        language: str,
        code_switching: bool = False,
        transliteration_usage: bool = False,
        confidence_score: float = 0.8,
        source_kind: SourceKind = SourceKind.CHAT,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        return EventFactory._build_event(
            event_type=TwinEventType.LANGUAGE_SIGNAL_OBSERVED,
            user_id=user_id,
            session_id=session_id,
            provenance=EventFactory._generic_provenance(
                source_kind=source_kind,
                source_refs=source_refs,
                confidence_level=ConfidenceLevel.HIGH,
                confidence_score=confidence_score,
            ),
            payload={
                "language": EventFactory._required_clean(language, "language").lower(),
                "code_switching": bool(code_switching),
                "transliteration_usage": bool(transliteration_usage),
            },
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def communication_style_observed(
        *,
        user_id: UUID,
        preferred_length: str | None = None,
        preferred_tone: str | None = None,
        prefers_bullets: bool | None = None,
        prefers_prose: bool | None = None,
        correction_sensitivity: float | None = None,
        typo_tolerance: float | None = None,
        confidence_score: float = 0.8,
        source_kind: SourceKind = SourceKind.CHAT,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        payload: dict[str, Any] = {}
        if preferred_length is not None:
            payload["preferred_length"] = EventFactory._required_clean(
                preferred_length, "preferred_length"
            )
        if preferred_tone is not None:
            payload["preferred_tone"] = EventFactory._required_clean(
                preferred_tone, "preferred_tone"
            )
        if prefers_bullets is not None:
            payload["prefers_bullets"] = bool(prefers_bullets)
        if prefers_prose is not None:
            payload["prefers_prose"] = bool(prefers_prose)
        if correction_sensitivity is not None:
            payload["correction_sensitivity"] = EventFactory._clamp_float(correction_sensitivity)
        if typo_tolerance is not None:
            payload["typo_tolerance"] = EventFactory._clamp_float(typo_tolerance)

        return EventFactory._build_event(
            event_type=TwinEventType.COMMUNICATION_STYLE_OBSERVED,
            user_id=user_id,
            session_id=session_id,
            provenance=EventFactory._generic_provenance(
                source_kind=source_kind,
                source_refs=source_refs,
                confidence_level=ConfidenceLevel.HIGH,
                confidence_score=confidence_score,
            ),
            payload=payload,
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def document_ingested(
        *,
        user_id: UUID,
        document_id: str,
        title: str | None = None,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        confidence_score: float = 0.95,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        return EventFactory._ingestion_event(
            event_type=TwinEventType.DOCUMENT_INGESTED,
            user_id=user_id,
            object_id=document_id,
            title=title,
            source_kind=SourceKind.DOCUMENT,
            source_refs=source_refs,
            metadata=metadata,
            confidence_score=confidence_score,
            session_id=session_id,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            object_key="document_id",
        )

    @staticmethod
    def web_chunk_ingested(
        *,
        user_id: UUID,
        chunk_id: str,
        title: str | None = None,
        url: str | None = None,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        confidence_score: float = 0.8,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        payload: dict[str, Any] = {
            "chunk_id": EventFactory._required_clean(chunk_id, "chunk_id"),
            "title": EventFactory._clean_optional(title),
            "url": EventFactory._clean_optional(url),
        }
        return EventFactory._build_event(
            event_type=TwinEventType.WEB_CHUNK_INGESTED,
            user_id=user_id,
            session_id=session_id,
            provenance=EventFactory._generic_provenance(
                source_kind=SourceKind.WEB,
                source_refs=source_refs,
                confidence_level=ConfidenceLevel.MEDIUM,
                confidence_score=confidence_score,
            ),
            payload=payload,
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def email_chunk_ingested(
        *,
        user_id: UUID,
        chunk_id: str,
        subject: str | None = None,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        confidence_score: float = 0.85,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        payload = {
            "chunk_id": EventFactory._required_clean(chunk_id, "chunk_id"),
            "subject": EventFactory._clean_optional(subject),
        }
        return EventFactory._build_event(
            event_type=TwinEventType.EMAIL_CHUNK_INGESTED,
            user_id=user_id,
            session_id=session_id,
            provenance=EventFactory._generic_provenance(
                source_kind=SourceKind.EMAIL,
                source_refs=source_refs,
                confidence_level=ConfidenceLevel.HIGH,
                confidence_score=confidence_score,
            ),
            payload=payload,
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def meeting_chunk_ingested(
        *,
        user_id: UUID,
        chunk_id: str,
        title: str | None = None,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        confidence_score: float = 0.85,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        payload = {
            "chunk_id": EventFactory._required_clean(chunk_id, "chunk_id"),
            "title": EventFactory._clean_optional(title),
        }
        return EventFactory._build_event(
            event_type=TwinEventType.MEETING_CHUNK_INGESTED,
            user_id=user_id,
            session_id=session_id,
            provenance=EventFactory._generic_provenance(
                source_kind=SourceKind.MEETING,
                source_refs=source_refs,
                confidence_level=ConfidenceLevel.HIGH,
                confidence_score=confidence_score,
            ),
            payload=payload,
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def voice_signal_derived(
        *,
        user_id: UUID,
        voice_embedding_ref: str | None = None,
        speech_style: dict[str, Any] | None = None,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        confidence_score: float = 0.8,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        payload: dict[str, Any] = {
            "voice_embedding_ref": EventFactory._clean_optional(voice_embedding_ref),
            "speech_style": dict(speech_style or {}),
        }
        return EventFactory._build_event(
            event_type=TwinEventType.VOICE_SIGNAL_DERIVED,
            user_id=user_id,
            session_id=session_id,
            provenance=EventFactory._generic_provenance(
                source_kind=SourceKind.VOICE,
                source_refs=source_refs,
                confidence_level=ConfidenceLevel.MEDIUM,
                confidence_score=confidence_score,
                contains_biometrics=True,
            ),
            payload=payload,
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def face_signal_derived(
        *,
        user_id: UUID,
        face_embedding_ref: str | None = None,
        visual_identity: dict[str, Any] | None = None,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        confidence_score: float = 0.8,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        payload: dict[str, Any] = {
            "face_embedding_ref": EventFactory._clean_optional(face_embedding_ref),
            "visual_identity": dict(visual_identity or {}),
        }
        return EventFactory._build_event(
            event_type=TwinEventType.FACE_SIGNAL_DERIVED,
            user_id=user_id,
            session_id=session_id,
            provenance=EventFactory._generic_provenance(
                source_kind=SourceKind.VISION,
                source_refs=source_refs,
                confidence_level=ConfidenceLevel.MEDIUM,
                confidence_score=confidence_score,
                contains_biometrics=True,
            ),
            payload=payload,
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def spelling_pattern_observed(
        *,
        user_id: UUID,
        patterns: dict[str, Any],
        confidence_score: float = 0.7,
        source_kind: SourceKind = SourceKind.CHAT,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        clean_patterns = {
            str(key).strip(): EventFactory._clamp_float(value)
            for key, value in patterns.items()
            if str(key).strip()
        }
        return EventFactory._build_event(
            event_type=TwinEventType.SPELLING_PATTERN_OBSERVED,
            user_id=user_id,
            session_id=session_id,
            provenance=EventFactory._generic_provenance(
                source_kind=source_kind,
                source_refs=source_refs,
                confidence_level=ConfidenceLevel.MEDIUM,
                confidence_score=confidence_score,
            ),
            payload={"patterns": clean_patterns},
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def consent_policy_updated(
        *,
        user_id: UUID,
        operational_memory: bool | None = None,
        behavioral_memory: bool | None = None,
        biometric_memory: bool | None = None,
        training_export: bool | None = None,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        payload: dict[str, Any] = {}
        if operational_memory is not None:
            payload["operational_memory"] = bool(operational_memory)
        if behavioral_memory is not None:
            payload["behavioral_memory"] = bool(behavioral_memory)
        if biometric_memory is not None:
            payload["biometric_memory"] = bool(biometric_memory)
        if training_export is not None:
            payload["training_export"] = bool(training_export)

        return EventFactory._build_event(
            event_type=TwinEventType.CONSENT_POLICY_UPDATED,
            user_id=user_id,
            session_id=session_id,
            provenance=EventFactory._system_provenance(
                source_kind=SourceKind.SYSTEM,
                source_refs=source_refs,
                confidence_level=ConfidenceLevel.EXPLICIT,
                confidence_score=1.0,
                activity_kind="consent_update",
                activity_description="User or operator updated twin consent policy",
            ),
            payload=payload,
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def memory_redacted(
        *,
        user_id: UUID,
        field_key: str,
        reason: str | None = None,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        return EventFactory._lifecycle_event(
            event_type=TwinEventType.MEMORY_REDACTED,
            user_id=user_id,
            field_key=field_key,
            reason=reason,
            source_refs=source_refs,
            metadata=metadata,
            session_id=session_id,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def memory_forgotten(
        *,
        user_id: UUID,
        field_key: str,
        reason: str | None = None,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        return EventFactory._lifecycle_event(
            event_type=TwinEventType.MEMORY_FORGOTTEN,
            user_id=user_id,
            field_key=field_key,
            reason=reason,
            source_refs=source_refs,
            metadata=metadata,
            session_id=session_id,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def memory_retention_expired(
        *,
        user_id: UUID,
        field_key: str,
        reason: str | None = None,
        source_refs: list[TwinReference] | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        return EventFactory._lifecycle_event(
            event_type=TwinEventType.MEMORY_RETENTION_EXPIRED,
            user_id=user_id,
            field_key=field_key,
            reason=reason,
            source_refs=source_refs,
            metadata=metadata,
            session_id=session_id,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def _relationship_event(
        *,
        event_type: TwinEventType,
        user_id: UUID,
        source_entity_id: str,
        target_entity_id: str,
        relation_type: str,
        strength: float,
        confidence_score: float,
        source_kind: SourceKind,
        source_refs: list[TwinReference] | None,
        metadata: dict[str, Any] | None,
        session_id: str | None,
        occurred_at: datetime | None,
        causation_id: UUID | None,
        correlation_id: UUID | None,
        idempotency_key: str | None,
    ) -> EventEnvelope:
        return EventFactory._build_event(
            event_type=event_type,
            user_id=user_id,
            session_id=session_id,
            provenance=EventFactory._generic_provenance(
                source_kind=source_kind,
                source_refs=source_refs,
                confidence_level=ConfidenceLevel.HIGH,
                confidence_score=confidence_score,
            ),
            payload={
                "source_entity_id": EventFactory._required_clean(
                    source_entity_id, "source_entity_id"
                ),
                "target_entity_id": EventFactory._required_clean(
                    target_entity_id, "target_entity_id"
                ),
                "relation_type": EventFactory._required_clean(relation_type, "relation_type"),
                "strength": EventFactory._clamp_float(strength),
            },
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def _ingestion_event(
        *,
        event_type: TwinEventType,
        user_id: UUID,
        object_id: str,
        title: str | None,
        source_kind: SourceKind,
        source_refs: list[TwinReference] | None,
        metadata: dict[str, Any] | None,
        confidence_score: float,
        session_id: str | None,
        occurred_at: datetime | None,
        causation_id: UUID | None,
        correlation_id: UUID | None,
        idempotency_key: str | None,
        object_key: str,
    ) -> EventEnvelope:
        return EventFactory._build_event(
            event_type=event_type,
            user_id=user_id,
            session_id=session_id,
            provenance=EventFactory._generic_provenance(
                source_kind=source_kind,
                source_refs=source_refs,
                confidence_level=ConfidenceLevel.HIGH,
                confidence_score=confidence_score,
            ),
            payload={
                object_key: EventFactory._required_clean(object_id, object_key),
                "title": EventFactory._clean_optional(title),
            },
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def _lifecycle_event(
        *,
        event_type: TwinEventType,
        user_id: UUID,
        field_key: str,
        reason: str | None,
        source_refs: list[TwinReference] | None,
        metadata: dict[str, Any] | None,
        session_id: str | None,
        occurred_at: datetime | None,
        causation_id: UUID | None,
        correlation_id: UUID | None,
        idempotency_key: str | None,
    ) -> EventEnvelope:
        return EventFactory._build_event(
            event_type=event_type,
            user_id=user_id,
            session_id=session_id,
            provenance=EventFactory._system_provenance(
                source_kind=SourceKind.SYSTEM,
                source_refs=source_refs,
                confidence_level=ConfidenceLevel.EXPLICIT,
                confidence_score=1.0,
                activity_kind=event_type.value,
                activity_description=event_type.value,
            ),
            payload={
                "field_key": EventFactory._required_clean(field_key, "field_key"),
                "reason": EventFactory._clean_optional(reason),
            },
            metadata=metadata,
            occurred_at=occurred_at,
            causation_id=causation_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def _build_event(
        *,
        event_type: TwinEventType,
        user_id: UUID,
        provenance: EventProvenance,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        occurred_at: datetime | None = None,
        recorded_at: datetime | None = None,
        causation_id: UUID | None = None,
        correlation_id: UUID | None = None,
        idempotency_key: str | None = None,
        schema_version: str = _DEFAULT_SCHEMA_VERSION,
    ) -> EventEnvelope:
        import structlog.contextvars

        ctx = structlog.contextvars.get_contextvars()

        # Propagate correlation_id from context if missing
        if correlation_id is None:
            trace_id = ctx.get("trace_id")
            if trace_id:
                with contextlib.suppress(ValueError, TypeError):
                    correlation_id = UUID(str(trace_id))

        # If still missing but we have causation, it will be handled by EventEnvelope validator
        # but we can be explicit here too if we want to bind more context.

        merged_metadata = dict(metadata or {})
        if idempotency_key:
            merged_metadata["idempotency_key"] = idempotency_key.strip()
        if session_id:
            merged_metadata.setdefault("session_id", session_id.strip())

        # Enrich metadata with context info
        for key in ["request_id", "span_id", "trace_id"]:
            if val := ctx.get(key):
                merged_metadata.setdefault(f"ctx_{key}", val)

        return EventEnvelope(
            event_type=event_type,
            user_id=user_id,
            session_id=EventFactory._clean_optional(session_id),
            occurred_at=EventFactory._normalize_dt(occurred_at)
            if occurred_at
            else datetime.now(UTC),
            recorded_at=EventFactory._normalize_dt(recorded_at)
            if recorded_at
            else datetime.now(UTC),
            causation_id=causation_id,
            correlation_id=correlation_id,
            provenance=provenance,
            payload=dict(payload or {}),
            schema_version=schema_version,
            metadata=merged_metadata,
        )

    @staticmethod
    def _chat_provenance(
        *,
        source_refs: list[TwinReference] | None,
        explicit: bool,
        confidence_score: float,
    ) -> EventProvenance:
        return EventProvenance(
            source_kind=SourceKind.CHAT,
            source_refs=source_refs or [],
            confidence_level=ConfidenceLevel.EXPLICIT if explicit else ConfidenceLevel.HIGH,
            confidence_score=EventFactory._clamp_float(confidence_score),
        )

    @staticmethod
    def _system_provenance(
        *,
        source_kind: SourceKind,
        source_refs: list[TwinReference] | None,
        confidence_level: ConfidenceLevel,
        confidence_score: float,
        activity_kind: str,
        activity_description: str | None = None,
        contains_biometrics: bool = False,
    ) -> EventProvenance:
        return EventProvenance(
            source_kind=source_kind,
            source_refs=source_refs or [],
            agent=ProvenanceAgent(
                kind="service",
                id="butler-memory",
                display_name="Butler Memory",
            ),
            activity=ProvenanceActivity(
                kind=activity_kind,
                id=activity_kind,
                description=activity_description,
            ),
            confidence_level=confidence_level,
            confidence_score=EventFactory._clamp_float(confidence_score),
            contains_biometrics=contains_biometrics,
        )

    @staticmethod
    def _generic_provenance(
        *,
        source_kind: SourceKind,
        source_refs: list[TwinReference] | None,
        confidence_level: ConfidenceLevel,
        confidence_score: float,
        contains_biometrics: bool = False,
    ) -> EventProvenance:
        return EventProvenance(
            source_kind=source_kind,
            source_refs=source_refs or [],
            confidence_level=confidence_level,
            confidence_score=EventFactory._clamp_float(confidence_score),
            contains_biometrics=contains_biometrics,
        )

    @staticmethod
    def _required_clean(value: str, field_name: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError(f"{field_name} must not be empty")
        return cleaned

    @staticmethod
    def _clean_optional(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _normalize_dt(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _clamp_float(value: Any) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = 0.0
        return max(0.0, min(1.0, numeric))
