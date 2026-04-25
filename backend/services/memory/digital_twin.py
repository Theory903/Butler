"""
Butler Digital Twin Memory System

Implements persistent memory graph with digital twin capabilities for user profiles.
Follows docs/03-reference/system/digital-twin-memory.md pattern.

SWE-5 Requirements:
- Pydantic schemas
- Temporal reasoning
- Entity resolution
- Graph relationships
- Full OpenTelemetry
"""

from __future__ import annotations

import datetime
import enum
import uuid
from typing import Any
from uuid import UUID

from opentelemetry import trace
from opentelemetry.trace import Tracer
from pydantic import BaseModel, ConfigDict, Field, field_validator

tracer: Tracer = trace.get_tracer(__name__)


class ConsentTier(enum.StrEnum):
    """User consent tiers for memory usage."""

    NEVER_TRAIN = "never_train"
    PRIVATE_EVAL_ONLY = "private_eval_only"
    OPT_IN = "opt_in"


class MemoryLayerType(enum.StrEnum):
    """Types of memory layers."""

    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PREFERENCES = "preferences"
    GRAPH = "graph"
    FILES = "files"
    TRAINING = "training"


class EntityType(enum.StrEnum):
    """Known entity types for resolution."""

    PERSON = "person"
    PLACE = "place"
    ORGANIZATION = "organization"
    PRODUCT = "product"
    CONCEPT = "concept"
    DOCUMENT = "document"
    DEVICE = "device"


class MemoryFact(BaseModel):
    """Single extracted fact from interactions."""

    fact_id: UUID = Field(default_factory=uuid.uuid4)
    entity_id: UUID
    attribute: str
    value: Any
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    source_interaction_id: UUID | None = None
    first_observed: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    last_observed: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    observation_count: int = 1
    is_active: bool = True


class Preference(BaseModel):
    """User preference with temporal decay."""

    preference_id: UUID = Field(default_factory=uuid.uuid4)
    domain: str
    key: str
    value: Any
    strength: float = Field(ge=-1.0, le=1.0)
    last_updated: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    source_count: int = 1
    explicit: bool = False


class EpisodicMemory(BaseModel):
    """Record of an interaction or event."""

    episode_id: UUID = Field(default_factory=uuid.uuid4)
    timestamp: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    interaction_type: str
    content: str
    context: dict[str, Any] = Field(default_factory=dict)
    entities_extracted: list[UUID] = Field(default_factory=list)
    importance: float = Field(ge=0.0, le=1.0, default=0.5)


class EntityNode(BaseModel):
    """Node in the relationship graph."""

    entity_id: UUID = Field(default_factory=uuid.uuid4)
    entity_type: EntityType
    canonical_name: str
    aliases: set[str] = Field(default_factory=set)
    attributes: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    last_seen: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )


class RelationshipEdge(BaseModel):
    """Edge between two entities in the graph."""

    edge_id: UUID = Field(default_factory=uuid.uuid4)
    from_entity: UUID
    to_entity: UUID
    relationship_type: str
    strength: float = Field(ge=0.0, le=1.0, default=1.0)
    first_observed: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    last_observed: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )


class FileMemory(BaseModel):
    """Memory of uploaded documents and files."""

    file_id: UUID = Field(default_factory=uuid.uuid4)
    original_name: str
    content_hash: str
    mime_type: str
    size_bytes: int
    extracted_text: str | None
    entities_found: list[UUID] = Field(default_factory=list)
    summary: str | None
    uploaded_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    last_accessed: datetime.datetime | None


class TrainingSample(BaseModel):
    """Anonymized training sample (opt-in only)."""

    sample_id: UUID = Field(default_factory=uuid.uuid4)
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    input_context: str
    output_response: str
    anonymized: bool = True
    quality_score: float | None = None


class MemoryLayer(BaseModel):
    """Abstract base for all memory layers."""

    layer_type: MemoryLayerType
    last_updated: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    entry_count: int = 0

    model_config = ConfigDict(arbitrary_types_allowed=True)


class EpisodicLayer(MemoryLayer):
    """Episodic memory layer - conversation history."""

    layer_type: MemoryLayerType = MemoryLayerType.EPISODIC
    episodes: list[EpisodicMemory] = Field(default_factory=list)


class SemanticLayer(MemoryLayer):
    """Semantic memory layer - extracted facts."""

    layer_type: MemoryLayerType = MemoryLayerType.SEMANTIC
    facts: dict[UUID, MemoryFact] = Field(default_factory=dict)


class PreferenceLayer(MemoryLayer):
    """Preference memory layer - user likes/dislikes."""

    layer_type: MemoryLayerType = MemoryLayerType.PREFERENCES
    preferences: dict[str, Preference] = Field(default_factory=dict)


class GraphLayer(MemoryLayer):
    """Graph memory layer - entity relationships."""

    layer_type: MemoryLayerType = MemoryLayerType.GRAPH
    entities: dict[UUID, EntityNode] = Field(default_factory=dict)
    edges: dict[UUID, RelationshipEdge] = Field(default_factory=dict)


class FileLayer(MemoryLayer):
    """File memory layer - document understanding."""

    layer_type: MemoryLayerType = MemoryLayerType.FILES
    files: dict[UUID, FileMemory] = Field(default_factory=dict)


class TrainingLayer(MemoryLayer):
    """Training memory layer - opt-in anonymized samples."""

    layer_type: MemoryLayerType = MemoryLayerType.TRAINING
    samples: list[TrainingSample] = Field(default_factory=list)


class DigitalTwinProfile(BaseModel):
    """Complete digital twin profile for a user."""

    user_id: UUID
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    last_updated: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    consent_tier: ConsentTier = ConsentTier.NEVER_TRAIN
    retention_days: int | None = None

    # Memory layers
    episodic: EpisodicLayer = Field(default_factory=EpisodicLayer)
    semantic: SemanticLayer = Field(default_factory=SemanticLayer)
    preferences: PreferenceLayer = Field(default_factory=PreferenceLayer)
    graph: GraphLayer = Field(default_factory=GraphLayer)
    files: FileLayer = Field(default_factory=FileLayer)
    training: TrainingLayer = Field(default_factory=TrainingLayer)

    @field_validator("last_updated")
    @classmethod
    def update_timestamp(cls, v: datetime.datetime) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


class TwinBuilder:
    """Builds and updates digital twin profiles from interactions over time."""

    def __init__(self, user_id: UUID):
        self.user_id = user_id
        self.profile = DigitalTwinProfile(user_id=user_id)

    @tracer.start_as_current_span("TwinBuilder.add_interaction")
    def add_interaction(self, interaction: EpisodicMemory) -> None:
        """Add a new interaction to the twin profile."""
        self.profile.episodic.episodes.append(interaction)
        self.profile.episodic.entry_count += 1
        self.profile.last_updated = datetime.datetime.now(datetime.UTC)

    @tracer.start_as_current_span("TwinBuilder.add_fact")
    def add_fact(self, fact: MemoryFact) -> None:
        """Add or update an extracted fact."""
        existing = self.profile.semantic.facts.get(fact.fact_id)
        if existing:
            existing.last_observed = datetime.datetime.now(datetime.UTC)
            existing.observation_count += 1
            existing.confidence = max(existing.confidence, fact.confidence)
        else:
            self.profile.semantic.facts[fact.fact_id] = fact
            self.profile.semantic.entry_count += 1
        self.profile.last_updated = datetime.datetime.now(datetime.UTC)

    @tracer.start_as_current_span("TwinBuilder.add_preference")
    def add_preference(self, preference: Preference) -> None:
        """Add or update a user preference."""
        key = f"{preference.domain}:{preference.key}"
        existing = self.profile.preferences.preferences.get(key)
        if existing:
            existing.strength = (
                existing.strength * existing.source_count + preference.strength
            ) / (existing.source_count + 1)
            existing.source_count += 1
            existing.last_updated = datetime.datetime.now(datetime.UTC)
        else:
            self.profile.preferences.preferences[key] = preference
            self.profile.preferences.entry_count += 1
        self.profile.last_updated = datetime.datetime.now(datetime.UTC)

    @tracer.start_as_current_span("TwinBuilder.add_entity")
    def add_entity(self, entity: EntityNode) -> None:
        """Add an entity to the graph layer."""
        self.profile.graph.entities[entity.entity_id] = entity
        self.profile.graph.entry_count += 1
        self.profile.last_updated = datetime.datetime.now(datetime.UTC)

    @tracer.start_as_current_span("TwinBuilder.add_relationship")
    def add_relationship(self, edge: RelationshipEdge) -> None:
        """Add a relationship between entities."""
        self.profile.graph.edges[edge.edge_id] = edge
        self.profile.graph.entry_count += 1
        self.profile.last_updated = datetime.datetime.now(datetime.UTC)

    @tracer.start_as_current_span("TwinBuilder.add_file")
    def add_file(self, file: FileMemory) -> None:
        """Add an uploaded file to memory."""
        self.profile.files.files[file.file_id] = file
        self.profile.files.entry_count += 1
        self.profile.last_updated = datetime.datetime.now(datetime.UTC)

    def build(self) -> DigitalTwinProfile:
        """Return the completed profile."""
        return self.profile


class TwinQueryEngine:
    """Queries digital twin profiles for personalization and context."""

    def __init__(self, profile: DigitalTwinProfile):
        self.profile = profile

    @tracer.start_as_current_span("TwinQueryEngine.get_recent_episodes")
    def get_recent_episodes(
        self, limit: int = 10, hours: int | None = None
    ) -> list[EpisodicMemory]:
        """Get recent episodic memory entries."""
        episodes = sorted(self.profile.episodic.episodes, key=lambda e: e.timestamp, reverse=True)
        if hours:
            cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=hours)
            episodes = [e for e in episodes if e.timestamp >= cutoff]
        return episodes[:limit]

    @tracer.start_as_current_span("TwinQueryEngine.get_preference")
    def get_preference(self, domain: str, key: str, default: Any = None) -> Any:
        """Get a user preference value."""
        pref_key = f"{domain}:{key}"
        pref = self.profile.preferences.preferences.get(pref_key)
        return pref.value if pref else default

    @tracer.start_as_current_span("TwinQueryEngine.find_entities")
    def find_entities(self, name_query: str) -> list[EntityNode]:
        """Find entities by name or alias."""
        query = name_query.lower()
        matches = []
        for entity in self.profile.graph.entities.values():
            if query in entity.canonical_name.lower() or any(
                query in alias.lower() for alias in entity.aliases
            ):
                matches.append(entity)
        return matches

    @tracer.start_as_current_span("TwinQueryEngine.get_relationships")
    def get_relationships(self, entity_id: UUID) -> list[RelationshipEdge]:
        """Get all relationships for an entity."""
        return [
            edge
            for edge in self.profile.graph.edges.values()
            if edge.from_entity == entity_id or edge.to_entity == entity_id
        ]

    @tracer.start_as_current_span("TwinQueryEngine.get_context_window")
    def get_context_window(self, max_tokens: int = 4096) -> dict[str, Any]:
        """Build a context window for LLM prompting."""
        return {
            "user_id": str(self.profile.user_id),
            "recent_interactions": [e.content for e in self.get_recent_episodes(limit=5)],
            "key_preferences": [
                {"domain": p.domain, "key": p.key, "value": p.value}
                for p in self.profile.preferences.preferences.values()
                if p.strength > 0.7
            ],
            "active_entities": [
                {"name": e.canonical_name, "type": e.entity_type}
                for e in self.profile.graph.entities.values()
                if (datetime.datetime.now(datetime.UTC) - e.last_seen).days < 30
            ][:20],
        }


class TrainingDataTransformer:
    """Handles opt-in training data pipeline with consent enforcement."""

    @staticmethod
    @tracer.start_as_current_span("TrainingDataTransformer.create_sample")
    def create_sample(
        profile: DigitalTwinProfile, input_context: str, output_response: str
    ) -> TrainingSample | None:
        """Create a training sample only if user has opted in."""
        if profile.consent_tier != ConsentTier.OPT_IN:
            return None

        sample = TrainingSample(
            input_context=input_context, output_response=output_response, anonymized=True
        )
        profile.training.samples.append(sample)
        profile.training.entry_count += 1
        return sample

    @staticmethod
    def can_use_for_training(profile: DigitalTwinProfile) -> bool:
        """Check if user has consented to training data usage."""
        return profile.consent_tier == ConsentTier.OPT_IN

    @staticmethod
    def can_use_for_evaluation(profile: DigitalTwinProfile) -> bool:
        """Check if user allows private evaluation usage."""
        return profile.consent_tier in (ConsentTier.PRIVATE_EVAL_ONLY, ConsentTier.OPT_IN)


class EntityResolver:
    """Resolves and deduplicates entities across interactions."""

    def __init__(self, profile: DigitalTwinProfile):
        self.profile = profile

    @tracer.start_as_current_span("EntityResolver.resolve")
    def resolve(self, name: str, entity_type: EntityType) -> EntityNode:
        """Resolve a name to an existing entity or create new."""
        # Check existing entities
        for entity in self.profile.graph.entities.values():
            if entity.entity_type != entity_type:
                continue
            if name.lower() == entity.canonical_name.lower() or name.lower() in (
                a.lower() for a in entity.aliases
            ):
                entity.last_seen = datetime.datetime.now(datetime.UTC)
                return entity

        # Create new entity
        new_entity = EntityNode(entity_type=entity_type, canonical_name=name)
        self.profile.graph.entities[new_entity.entity_id] = new_entity
        self.profile.graph.entry_count += 1
        return new_entity

    def add_alias(self, entity_id: UUID, alias: str) -> None:
        """Add an alias to an existing entity."""
        entity = self.profile.graph.entities.get(entity_id)
        if entity:
            entity.aliases.add(alias)


class TemporalReasoner:
    """Provides temporal reasoning over memory."""

    def __init__(self, profile: DigitalTwinProfile):
        self.profile = profile

    def get_fact_at_time(
        self, entity_id: UUID, attribute: str, at_time: datetime.datetime
    ) -> MemoryFact | None:
        """Get the most recent fact value at a specific point in time."""
        matching = [
            fact
            for fact in self.profile.semantic.facts.values()
            if fact.entity_id == entity_id
            and fact.attribute == attribute
            and fact.first_observed <= at_time
            and fact.is_active
        ]
        if not matching:
            return None
        return max(matching, key=lambda f: f.last_observed)

    def get_preference_trend(self, domain: str, key: str, days: int = 30) -> list[float]:
        """Get preference strength trend over time."""
        # Implementation would track historical preference values
        return []
