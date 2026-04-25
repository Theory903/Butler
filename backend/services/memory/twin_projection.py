from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from services.memory.twin_events import EventEnvelope
from services.memory.twin_types import ConfidenceLevel, TwinEventType


class ProjectionStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    FORGOTTEN = "forgotten"


class IdentityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    preferred_name: str | None = None
    pronouns: str | None = None
    location: str | None = None
    timezone: str | None = None
    bio: str | None = None


class CommunicationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_length: str | None = None
    preferred_structure: str | None = None
    preferred_tone: str | None = None
    prose_vs_bullets: float | None = None
    bluntness_tolerance: float | None = None
    typo_tolerance: float | None = None
    correction_sensitivity: float | None = None
    formality_range: tuple[float, float] | None = None
    emoji_usage: str | None = None
    greeting_style: str | None = None
    farewell_style: str | None = None
    prefers_bullets: bool | None = None
    prefers_prose: bool | None = None


class LanguageProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_languages: list[str] = Field(default_factory=list)
    primary_language: str | None = None
    transliteration_usage: str | None = None
    code_switching: bool = False
    multilingual_patterns: dict[str, Any] = Field(default_factory=dict)


class PreferenceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explicit: dict[str, Any] = Field(default_factory=dict)
    inferred: dict[str, Any] = Field(default_factory=dict)

    def get_value(self, key: str) -> tuple[Any, ConfidenceLevel] | None:
        if key in self.explicit and isinstance(self.explicit[key], dict):
            return self.explicit[key].get("value"), ConfidenceLevel.EXPLICIT
        if key in self.inferred and isinstance(self.inferred[key], dict):
            return self.inferred[key].get("value"), ConfidenceLevel.MEDIUM
        return None

    def set_value(
        self,
        key: str,
        value: Any,
        confidence: ConfidenceLevel,
        source: str = "explicit",
        domain: str | None = None,
    ) -> None:
        target = self.explicit if confidence == ConfidenceLevel.EXPLICIT else self.inferred
        existing = target.get(key, {})
        target[key] = {
            "value": value,
            "confidence": confidence.value,
            "source": source,
            "domain": domain or existing.get("domain", "general"),
            "created_at": existing.get("created_at", datetime.now(UTC).isoformat()),
            "updated_at": datetime.now(UTC).isoformat(),
        }


class DislikeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explicit: dict[str, Any] = Field(default_factory=dict)
    inferred: dict[str, Any] = Field(default_factory=dict)


class ConstraintProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hard: dict[str, Any] = Field(default_factory=dict)
    soft: dict[str, Any] = Field(default_factory=dict)


class GoalState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    status: str = "active"
    priority: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    superseded_by: str | None = None


class ProjectState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    status: str = "active"
    importance: float = 0.5
    recency: float = 0.5
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_active_at: datetime | None = None


class RelationshipState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    label: str
    strength: float = 0.5
    last_interaction: datetime | None = None
    interaction_count: int = 0
    sentiment: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EntityState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    kind: str
    properties: dict[str, Any] = Field(default_factory=dict)
    first_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TopicAffinity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    strength: float = 0.0
    recency: datetime | None = None
    signals: list[str] = Field(default_factory=list)


class BehavioralSignals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acceptance_rate: float | None = None
    correction_sensitivity: float | None = None
    verbosity_preference: float | None = None
    interaction_depth: float | None = None
    revisit_patterns: list[dict[str, Any]] = Field(default_factory=list)
    response_stability: float | None = None


class MultimodalProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_reference: str | None = None
    face_reference: str | None = None
    consented: bool = False
    last_consent_at: datetime | None = None


class ConsentState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operational_memory: bool = True
    behavioral_memory: bool = True
    biometric_memory: bool = False
    training_export: bool = False
    multimodal_consent_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProvenanceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events_processed: int = 0
    last_event_at: datetime | None = None
    first_event_at: datetime | None = None
    provenance_breakdown: dict[str, int] = Field(default_factory=dict)


class DigitalTwinProjection(BaseModel):
    """Canonical digital twin projection.

    This is the materialized read model for operational reads.
    It is rebuilt from events but stored as a snapshot for fast access.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    version: int = Field(default=0, ge=0)
    status: ProjectionStatus = ProjectionStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    identity_profile: IdentityProfile = Field(default_factory=IdentityProfile)
    communication_profile: CommunicationProfile = Field(default_factory=CommunicationProfile)
    language_profile: LanguageProfile = Field(default_factory=LanguageProfile)
    preference_profile: PreferenceProfile = Field(default_factory=PreferenceProfile)
    dislike_profile: DislikeProfile = Field(default_factory=DislikeProfile)
    constraint_profile: ConstraintProfile = Field(default_factory=ConstraintProfile)

    active_goals: list[GoalState] = Field(default_factory=list)
    active_projects: list[ProjectState] = Field(default_factory=list)
    active_topics: list[TopicAffinity] = Field(default_factory=list)
    active_relationships: list[RelationshipState] = Field(default_factory=list)

    entities: list[EntityState] = Field(default_factory=list)

    behavioral_signals: BehavioralSignals = Field(default_factory=BehavioralSignals)
    multimodal_profile: MultimodalProfile = Field(default_factory=MultimodalProfile)
    consent_state: ConsentState = Field(default_factory=ConsentState)
    provenance_summary: ProvenanceSummary = Field(default_factory=ProvenanceSummary)

    metadata: dict[str, Any] = Field(default_factory=dict)


def new_projection(user_id: UUID) -> DigitalTwinProjection:
    return DigitalTwinProjection(user_id=user_id)


def apply_event_to_projection(
    projection: DigitalTwinProjection,
    event: EventEnvelope,
) -> DigitalTwinProjection:
    """Apply a single event to the projection, returning a new version."""
    updated = projection.model_copy(deep=True)
    updated.version += 1
    updated.updated_at = event.recorded_at if event.recorded_at else datetime.now(UTC)

    match event.event_type:
        case TwinEventType.PREFERENCE_UPDATED:
            _apply_preference_updated(updated, event)
        case TwinEventType.DISLIKE_UPDATED:
            _apply_dislike_updated(updated, event)
        case TwinEventType.CONSTRAINT_UPDATED:
            _apply_constraint_updated(updated, event)
        case TwinEventType.SEMANTIC_FACT_CREATED:
            _apply_semantic_fact_created(updated, event)
        case TwinEventType.SEMANTIC_FACT_REINFORCED:
            _apply_semantic_fact_reinforced(updated, event)
        case TwinEventType.SEMANTIC_FACT_SUPERSEDED:
            _apply_semantic_fact_superseded(updated, event)
        case TwinEventType.SEMANTIC_FACT_CONTRADICTED:
            _apply_semantic_fact_contradicted(updated, event)
        case TwinEventType.ENTITY_RESOLVED:
            _apply_entity_resolved(updated, event)
        case TwinEventType.RELATIONSHIP_CREATED:
            _apply_relationship_created(updated, event)
        case TwinEventType.RELATIONSHIP_UPDATED:
            _apply_relationship_updated(updated, event)
        case TwinEventType.TOPIC_SIGNAL_OBSERVED:
            _apply_topic_signal(updated, event)
        case TwinEventType.LANGUAGE_SIGNAL_OBSERVED:
            _apply_language_signal(updated, event)
        case TwinEventType.COMMUNICATION_STYLE_OBSERVED:
            _apply_communication_style(updated, event)
        case TwinEventType.SESSION_SUMMARY_UPDATED:
            _apply_session_summary(updated, event)
        case TwinEventType.CONSENT_POLICY_UPDATED:
            _apply_consent_updated(updated, event)
        case TwinEventType.MEMORY_REDACTED:
            _apply_redaction(updated, event)
        case TwinEventType.MEMORY_FORGOTTEN:
            _apply_forgetting(updated, event)
        case TwinEventType.MEMORY_RETENTION_EXPIRED:
            _apply_retention_expired(updated, event)
        case TwinEventType.EPISODE_CAPTURED:
            _apply_episode_captured(updated, event)
        case TwinEventType.CONVERSATION_TURN_RECORDED:
            _apply_conversation_turn_recorded(updated, event)
        case TwinEventType.VOICE_SIGNAL_DERIVED:
            _apply_voice_signal(updated, event)
        case TwinEventType.FACE_SIGNAL_DERIVED:
            _apply_face_signal(updated, event)
        case TwinEventType.SPELLING_PATTERN_OBSERVED:
            _apply_spelling_pattern(updated, event)
        case _:
            pass

    updated.provenance_summary.events_processed += 1
    if (
        updated.provenance_summary.last_event_at is None
        or event.occurred_at > updated.provenance_summary.last_event_at
    ):
        updated.provenance_summary.last_event_at = event.occurred_at
    if updated.provenance_summary.first_event_at is None:
        updated.provenance_summary.first_event_at = event.occurred_at

    source_type = event.provenance.source_kind.value if event.provenance else "unknown"
    updated.provenance_summary.provenance_breakdown[source_type] = (
        updated.provenance_summary.provenance_breakdown.get(source_type, 0) + 1
    )

    return updated


def _apply_preference_updated(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    payload = event.payload
    key = _clean_str(payload.get("key"))
    value = payload.get("value")
    if not key or value is None:
        return

    confidence = event.provenance.confidence_level if event.provenance else ConfidenceLevel.MEDIUM
    source = "explicit" if payload.get("explicit", False) else "inferred"
    domain = _clean_str(payload.get("domain")) or "general"
    proj.preference_profile.set_value(key, value, confidence, source, domain)


def _apply_dislike_updated(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    payload = event.payload
    key = _clean_str(payload.get("key"))
    value = payload.get("value")
    if not key or value is None:
        return

    target = (
        proj.dislike_profile.explicit
        if payload.get("explicit", False)
        else proj.dislike_profile.inferred
    )
    confidence = (
        event.provenance.confidence_level.value
        if event.provenance
        else ConfidenceLevel.MEDIUM.value
    )
    existing = target.get(key, {})
    target[key] = {
        "value": value,
        "confidence": confidence,
        "source": payload.get(
            "source", "explicit" if payload.get("explicit", False) else "inferred"
        ),
        "reason": payload.get("reason"),
        "created_at": existing.get("created_at", datetime.now(UTC).isoformat()),
        "updated_at": datetime.now(UTC).isoformat(),
    }


def _apply_constraint_updated(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    payload = event.payload
    key = _clean_str(payload.get("key"))
    value = payload.get("value")
    if not key or value is None:
        return

    constraint_type = str(payload.get("type", "soft")).strip().lower()
    target = (
        proj.constraint_profile.hard if constraint_type == "hard" else proj.constraint_profile.soft
    )
    existing = target.get(key, {})
    target[key] = {
        "value": value,
        "reason": payload.get("reason"),
        "source": payload.get("source", "event"),
        "created_at": existing.get("created_at", datetime.now(UTC).isoformat()),
        "updated_at": datetime.now(UTC).isoformat(),
    }


def _apply_semantic_fact_created(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    payload = event.payload
    fact_key = _clean_str(payload.get("fact_key") or payload.get("key"))
    value = payload.get("value")
    if not fact_key or value is None:
        return

    _set_identity_field(proj, fact_key, value, event, state="active")


def _apply_semantic_fact_reinforced(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    payload = event.payload
    fact_key = _clean_str(payload.get("fact_key") or payload.get("key"))
    if not fact_key:
        return

    existing = proj.metadata.setdefault("identity_facts", {}).get(fact_key)
    if not isinstance(existing, dict):
        value = payload.get("value")
        if value is None:
            return
        _set_identity_field(proj, fact_key, value, event, state="active")
        return

    existing["last_confirmed_at"] = event.occurred_at.isoformat()
    existing["confidence"] = min(
        1.0,
        max(float(existing.get("confidence", 0.5)), _event_confidence_score(event)) + 0.02,
    )
    existing["status"] = "active"
    existing["reinforced_count"] = int(existing.get("reinforced_count", 0)) + 1
    existing["updated_at"] = datetime.now(UTC).isoformat()


def _apply_semantic_fact_superseded(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    payload = event.payload
    fact_key = _clean_str(payload.get("fact_key") or payload.get("key"))
    if not fact_key:
        return

    identity_facts = proj.metadata.setdefault("identity_facts", {})
    existing = identity_facts.get(fact_key)
    if isinstance(existing, dict):
        existing["status"] = "superseded"
        existing["superseded_by"] = str(event.event_id)
        existing["valid_until"] = event.occurred_at.isoformat()
        existing["updated_at"] = datetime.now(UTC).isoformat()

    new_value = payload.get("new_value", payload.get("value"))
    if new_value is not None:
        _set_identity_field(
            proj,
            fact_key,
            new_value,
            event,
            state="active",
            supersedes=str(event.event_id),
        )


def _apply_semantic_fact_contradicted(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    payload = event.payload
    fact_key = _clean_str(payload.get("fact_key") or payload.get("key"))
    if not fact_key:
        return

    existing = proj.metadata.setdefault("identity_facts", {}).get(fact_key)
    if not isinstance(existing, dict):
        return

    existing["status"] = "contradicted"
    existing["contradiction_reason"] = payload.get("reason")
    existing["contradicted_at"] = event.occurred_at.isoformat()
    existing["updated_at"] = datetime.now(UTC).isoformat()


def _apply_entity_resolved(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    payload = event.payload
    entity_id = _clean_str(payload.get("entity_id"))
    name = _clean_str(payload.get("name") or payload.get("canonical_name"))
    kind = _clean_str(payload.get("kind") or payload.get("entity_type")) or "unknown"
    if not entity_id or not name:
        return

    aliases = payload.get("aliases", [])
    if not isinstance(aliases, list):
        aliases = []

    alias_single = _clean_str(payload.get("alias"))
    if alias_single:
        aliases.append(alias_single)

    for ent in proj.entities:
        if ent.id == entity_id:
            ent.name = name or ent.name
            ent.kind = kind or ent.kind
            ent.last_updated = datetime.now(UTC)
            if isinstance(payload.get("properties"), dict):
                ent.properties.update(payload["properties"])
            summary = _clean_str(payload.get("summary"))
            if summary:
                ent.properties["summary"] = summary
            for alias in aliases:
                alias_clean = _clean_str(alias)
                if alias_clean and alias_clean not in ent.aliases:
                    ent.aliases.append(alias_clean)
            ent.aliases = sorted(set(ent.aliases))
            return

    properties = payload.get("properties", {})
    if not isinstance(properties, dict):
        properties = {}
    summary = _clean_str(payload.get("summary"))
    if summary:
        properties["summary"] = summary

    proj.entities.append(
        EntityState(
            id=entity_id,
            name=name,
            aliases=sorted({_clean_str(a) for a in aliases if _clean_str(a)}),
            kind=kind,
            properties=properties,
        )
    )


def _apply_relationship_created(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    payload = event.payload

    entity_id = _clean_str(
        payload.get("entity_id")
        or payload.get("target_entity_id")
        or payload.get("source_entity_id")
    )
    label = _clean_str(payload.get("label") or payload.get("relation_type"))
    if not entity_id or not label:
        return

    strength = _clamp_float(payload.get("strength", 0.5), default=0.5)
    sentiment = payload.get("sentiment")
    sentiment_value = None if sentiment is None else _clamp_float(sentiment)
    meta = payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}

    for rel in proj.active_relationships:
        if rel.entity_id == entity_id and rel.label == label:
            rel.strength = strength
            rel.sentiment = sentiment_value
            rel.last_interaction = event.occurred_at
            rel.interaction_count += 1
            rel.metadata.update(meta)
            return

    proj.active_relationships.append(
        RelationshipState(
            entity_id=entity_id,
            label=label,
            strength=strength,
            last_interaction=event.occurred_at,
            interaction_count=1,
            sentiment=sentiment_value,
            metadata=meta,
        )
    )


def _apply_relationship_updated(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    payload = event.payload
    entity_id = _clean_str(
        payload.get("entity_id")
        or payload.get("target_entity_id")
        or payload.get("source_entity_id")
    )
    label = _clean_str(payload.get("label") or payload.get("relation_type"))
    if not entity_id:
        return

    for rel in proj.active_relationships:
        if rel.entity_id == entity_id and (label is None or rel.label == label):
            if label:
                rel.label = label
            if "strength" in payload:
                rel.strength = _clamp_float(payload["strength"], default=rel.strength)
            if "sentiment" in payload and payload["sentiment"] is not None:
                rel.sentiment = _clamp_float(payload["sentiment"])
            if "metadata" in payload and isinstance(payload["metadata"], dict):
                rel.metadata.update(payload["metadata"])
            rel.interaction_count += 1
            rel.last_interaction = event.occurred_at
            return


def _apply_topic_signal(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    payload = event.payload
    topic = _clean_str(payload.get("topic"))
    signal = _clean_str(payload.get("signal"))
    if not topic:
        return

    observed_strength = _clamp_float(payload.get("strength", 0.1), default=0.1)
    for ta in proj.active_topics:
        if ta.name == topic:
            ta.strength = min(1.0, ta.strength + max(0.05, observed_strength))
            ta.recency = event.occurred_at
            if signal and signal not in ta.signals:
                ta.signals.append(signal)
            ta.signals = sorted(set(ta.signals))
            return

    proj.active_topics.append(
        TopicAffinity(
            name=topic,
            strength=max(0.05, observed_strength),
            recency=event.occurred_at,
            signals=[signal] if signal else [],
        )
    )
    proj.active_topics.sort(key=lambda item: (-item.strength, item.name))


def _apply_language_signal(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    payload = event.payload
    language = _clean_str(payload.get("language"))
    if language:
        if language not in proj.language_profile.preferred_languages:
            proj.language_profile.preferred_languages.append(language)
            proj.language_profile.preferred_languages.sort()
        if not proj.language_profile.primary_language:
            proj.language_profile.primary_language = language

    if "transliteration_usage" in payload:
        translit = payload.get("transliteration_usage")
        if isinstance(translit, bool):
            proj.language_profile.transliteration_usage = "enabled" if translit else "disabled"
        else:
            proj.language_profile.transliteration_usage = (
                None if translit is None else str(translit).strip() or None
            )

    if "code_switching" in payload:
        proj.language_profile.code_switching = bool(payload.get("code_switching"))

    if "multilingual_patterns" in payload and isinstance(payload["multilingual_patterns"], dict):
        proj.language_profile.multilingual_patterns.update(payload["multilingual_patterns"])


def _apply_communication_style(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    payload = event.payload

    for field_name in (
        "preferred_length",
        "preferred_structure",
        "preferred_tone",
        "prose_vs_bullets",
        "bluntness_tolerance",
        "typo_tolerance",
        "correction_sensitivity",
        "formality_range",
        "emoji_usage",
        "greeting_style",
        "farewell_style",
        "prefers_bullets",
        "prefers_prose",
    ):
        if field_name in payload and hasattr(proj.communication_profile, field_name):
            setattr(proj.communication_profile, field_name, payload[field_name])

    if "correction_sensitivity" in payload and payload["correction_sensitivity"] is not None:
        proj.behavioral_signals.correction_sensitivity = _clamp_float(
            payload["correction_sensitivity"]
        )


def _apply_session_summary(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    payload = event.payload
    summary = payload.get("summary")
    if isinstance(summary, str) and summary.strip():
        proj.metadata["latest_session_summary"] = summary.strip()
        proj.metadata["latest_session_summary_updated_at"] = event.occurred_at.isoformat()

    active_goal = _clean_str(payload.get("active_goal"))
    if active_goal:
        _upsert_goal(
            proj,
            goal_id=_slugify(active_goal),
            title=active_goal,
            priority=int(payload.get("priority", 0)),
            event_time=event.occurred_at,
        )

    active_project = _clean_str(payload.get("active_project"))
    if active_project:
        _upsert_project(
            proj,
            project_id=_slugify(active_project),
            name=active_project,
            importance=_clamp_float(payload.get("importance", 0.5), default=0.5),
            event_time=event.occurred_at,
        )


def _apply_consent_updated(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    payload = event.payload
    if "operational_memory" in payload:
        proj.consent_state.operational_memory = bool(payload["operational_memory"])
    if "behavioral_memory" in payload:
        proj.consent_state.behavioral_memory = bool(payload["behavioral_memory"])
    if "biometric_memory" in payload:
        proj.consent_state.biometric_memory = bool(payload["biometric_memory"])
    if "training_export" in payload:
        proj.consent_state.training_export = bool(payload["training_export"])

    if "multimodal_consent_at" in payload:
        proj.consent_state.multimodal_consent_at = _parse_datetime(payload["multimodal_consent_at"])

    proj.consent_state.updated_at = datetime.now(UTC)

    biometric_allowed = proj.consent_state.biometric_memory
    proj.multimodal_profile.consented = biometric_allowed
    if biometric_allowed:
        proj.multimodal_profile.last_consent_at = (
            proj.consent_state.multimodal_consent_at or event.occurred_at
        )
    else:
        proj.multimodal_profile.voice_reference = None
        proj.multimodal_profile.face_reference = None


def _apply_redaction(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    payload = event.payload
    field = _clean_str(payload.get("field") or payload.get("field_key"))
    if not field:
        return

    for bucket in (
        proj.preference_profile.explicit,
        proj.preference_profile.inferred,
        proj.dislike_profile.explicit,
        proj.dislike_profile.inferred,
        proj.constraint_profile.hard,
        proj.constraint_profile.soft,
    ):
        if field in bucket:
            bucket[field] = {
                "value": "<REDACTED>",
                "redacted": True,
                "updated_at": datetime.now(UTC).isoformat(),
            }

    identity_facts = proj.metadata.get("identity_facts")
    if (
        isinstance(identity_facts, dict)
        and field in identity_facts
        and isinstance(identity_facts[field], dict)
    ):
        identity_facts[field]["value"] = "<REDACTED>"
        identity_facts[field]["status"] = "redacted"
        identity_facts[field]["updated_at"] = datetime.now(UTC).isoformat()


def _apply_forgetting(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    payload = event.payload
    field = _clean_str(payload.get("field") or payload.get("field_key"))

    if field:
        for bucket in (
            proj.preference_profile.explicit,
            proj.preference_profile.inferred,
            proj.dislike_profile.explicit,
            proj.dislike_profile.inferred,
            proj.constraint_profile.hard,
            proj.constraint_profile.soft,
        ):
            bucket.pop(field, None)

        identity_facts = proj.metadata.get("identity_facts")
        if isinstance(identity_facts, dict):
            identity_facts.pop(field, None)
        return

    proj.status = ProjectionStatus.FORGOTTEN
    proj.preference_profile = PreferenceProfile()
    proj.dislike_profile = DislikeProfile()
    proj.constraint_profile = ConstraintProfile()
    proj.active_goals.clear()
    proj.active_projects.clear()
    proj.active_topics.clear()
    proj.active_relationships.clear()
    proj.entities.clear()
    proj.metadata.clear()


def _apply_retention_expired(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    payload = event.payload
    field = _clean_str(payload.get("field") or payload.get("field_key"))
    category = _clean_str(payload.get("category"))

    if category == "topic":
        proj.active_topics = [item for item in proj.active_topics if item.name != field]
        return
    if category == "relationship":
        proj.active_relationships = [
            item for item in proj.active_relationships if item.entity_id != field
        ]
        return
    if category == "project":
        proj.active_projects = [item for item in proj.active_projects if item.id != field]
        return
    if category == "goal":
        proj.active_goals = [item for item in proj.active_goals if item.id != field]
        return

    if field:
        for bucket in (
            proj.preference_profile.inferred,
            proj.dislike_profile.inferred,
            proj.constraint_profile.soft,
        ):
            bucket.pop(field, None)

        identity_facts = proj.metadata.get("identity_facts")
        if isinstance(identity_facts, dict) and field in identity_facts:
            identity_facts[field]["status"] = "expired"
            identity_facts[field]["updated_at"] = datetime.now(UTC).isoformat()


def _apply_episode_captured(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    payload = event.payload

    goal = _clean_str(payload.get("goal"))
    if goal:
        _upsert_goal(
            proj,
            goal_id=_slugify(goal),
            title=goal,
            priority=int(payload.get("priority", 0)),
            event_time=event.occurred_at,
        )

    project = _clean_str(payload.get("project"))
    if project:
        _upsert_project(
            proj,
            project_id=_slugify(project),
            name=project,
            importance=_clamp_float(payload.get("importance", 0.5), default=0.5),
            event_time=event.occurred_at,
        )


def _apply_conversation_turn_recorded(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    payload = event.payload
    role = _clean_str(payload.get("role"))
    if role != "user":
        return

    depth_hint = payload.get("interaction_depth")
    if depth_hint is not None:
        proj.behavioral_signals.interaction_depth = _clamp_float(depth_hint)

    revisit = payload.get("revisit_pattern")
    if isinstance(revisit, dict):
        proj.behavioral_signals.revisit_patterns.append(revisit)


def _apply_voice_signal(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    if not proj.consent_state.biometric_memory:
        return

    voice_reference = _clean_str(
        event.payload.get("voice_reference") or event.payload.get("voice_embedding_ref")
    )
    if voice_reference:
        proj.multimodal_profile.voice_reference = voice_reference
        proj.multimodal_profile.consented = True
        proj.multimodal_profile.last_consent_at = (
            proj.consent_state.multimodal_consent_at or event.occurred_at
        )


def _apply_face_signal(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    if not proj.consent_state.biometric_memory:
        return

    face_reference = _clean_str(
        event.payload.get("face_reference") or event.payload.get("face_embedding_ref")
    )
    if face_reference:
        proj.multimodal_profile.face_reference = face_reference
        proj.multimodal_profile.consented = True
        proj.multimodal_profile.last_consent_at = (
            proj.consent_state.multimodal_consent_at or event.occurred_at
        )


def _apply_spelling_pattern(proj: DigitalTwinProjection, event: EventEnvelope) -> None:
    payload = event.payload
    patterns = payload.get("patterns")
    if isinstance(patterns, dict):
        if "typo_tolerance" in patterns:
            proj.communication_profile.typo_tolerance = _clamp_float(patterns["typo_tolerance"])
        if "correction_sensitivity" in patterns:
            value = _clamp_float(patterns["correction_sensitivity"])
            proj.communication_profile.correction_sensitivity = value
            proj.behavioral_signals.correction_sensitivity = value
        if "response_stability" in patterns:
            proj.behavioral_signals.response_stability = _clamp_float(
                patterns["response_stability"]
            )
        if "verbosity_preference" in patterns:
            proj.behavioral_signals.verbosity_preference = _clamp_float(
                patterns["verbosity_preference"]
            )


def _set_identity_field(
    proj: DigitalTwinProjection,
    fact_key: str,
    value: Any,
    event: EventEnvelope,
    *,
    state: str,
    supersedes: str | None = None,
) -> None:
    identity_facts = proj.metadata.setdefault("identity_facts", {})
    existing = identity_facts.get(fact_key, {})
    identity_facts[fact_key] = {
        "value": value,
        "confidence": _event_confidence_score(event),
        "confidence_level": event.provenance.confidence_level.value
        if event.provenance
        else ConfidenceLevel.MEDIUM.value,
        "source_kind": event.provenance.source_kind.value if event.provenance else "unknown",
        "first_observed_at": existing.get("first_observed_at", event.occurred_at.isoformat()),
        "last_confirmed_at": event.occurred_at.isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
        "status": state,
        "supersedes": supersedes,
    }

    field_map = {
        "display_name": "display_name",
        "preferred_name": "preferred_name",
        "pronouns": "pronouns",
        "location": "location",
        "timezone": "timezone",
        "bio": "bio",
    }
    target_attr = field_map.get(fact_key)
    if target_attr and hasattr(proj.identity_profile, target_attr):
        setattr(proj.identity_profile, target_attr, value)


def _upsert_goal(
    proj: DigitalTwinProjection,
    *,
    goal_id: str,
    title: str,
    priority: int,
    event_time: datetime,
) -> None:
    for goal in proj.active_goals:
        if goal.id == goal_id:
            goal.title = title
            goal.priority = priority
            goal.status = "active"
            goal.updated_at = event_time
            return

    proj.active_goals.append(
        GoalState(
            id=goal_id,
            title=title,
            priority=priority,
            created_at=event_time,
            updated_at=event_time,
        )
    )


def _upsert_project(
    proj: DigitalTwinProjection,
    *,
    project_id: str,
    name: str,
    importance: float,
    event_time: datetime,
) -> None:
    for project in proj.active_projects:
        if project.id == project_id:
            project.name = name
            project.importance = importance
            project.recency = 1.0
            project.last_active_at = event_time
            project.updated_at = event_time
            return

    proj.active_projects.append(
        ProjectState(
            id=project_id,
            name=name,
            importance=importance,
            recency=1.0,
            created_at=event_time,
            updated_at=event_time,
            last_active_at=event_time,
        )
    )


def _event_confidence_score(event: EventEnvelope) -> float:
    if event.provenance:
        return max(0.0, min(1.0, float(event.provenance.confidence_score)))
    return 0.5


def _clean_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _clamp_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = default
    return max(0.0, min(1.0, numeric))


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def _slugify(value: str) -> str:
    return value.strip().lower().replace("/", "-").replace("_", "-").replace(" ", "-")
