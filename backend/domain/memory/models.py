import enum
import uuid
from datetime import datetime, UTC
from sqlalchemy import String, DateTime, Integer, Float, Boolean, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from infrastructure.database import Base

def now_utc():
    return datetime.now(UTC)

class MemoryStatus(str, enum.Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    CONFLICTED = "conflicted"

class MemoryEntry(Base):
    """Base memory record with temporal metadata."""
    __tablename__ = "memory_entries"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False)  # episodic, entity, preference, fact
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)     # JSONB — the actual memory payload
    from pgvector.sqlalchemy import Vector
    # NOTE: Using actual pgvector type for Phase 11+ integration.
    embedding: Mapped[list] = mapped_column(Vector(1536), nullable=True)    # Vector embedding
    importance: Mapped[float] = mapped_column(Float, default=0.5) # 0.0 - 1.0, decay-eligible
    confidence: Mapped[float] = mapped_column(Float, default=1.0) # 0.0 - 1.0
    source: Mapped[str] = mapped_column(String(32), default="conversation")       # conversation, tool_result, observation
    session_id: Mapped[str] = mapped_column(String(64), nullable=True)
    tags: Mapped[list] = mapped_column(JSONB, default=list)        # JSONB array
    status: Mapped[MemoryStatus] = mapped_column(Enum(MemoryStatus, native_enum=False), default=MemoryStatus.ACTIVE)
    metadata_col: Mapped[dict] = mapped_column("metadata", JSONB, nullable=True)    # JSONB — archival link, context, tool id
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)  # Temporal — when this became true
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True) # Same as valid_to in plan
    superseded_by: Mapped[uuid.UUID] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    access_count: Mapped[int] = mapped_column(Integer, default=0)

class ConversationTurn(Base):
    """Individual conversation turn within a session."""
    __tablename__ = "conversation_turns"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)         # user, assistant, system, tool
    content: Mapped[str] = mapped_column(String, nullable=False)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    intent: Mapped[str] = mapped_column(String(64), nullable=True)
    tool_calls: Mapped[dict] = mapped_column(JSONB, nullable=True)  # JSONB — tools invoked during this turn
    metadata_col: Mapped[dict] = mapped_column("metadata", JSONB, nullable=True)    # JSONB — latency, model, tokens
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

# ── Knowledge Graph Layer ───────────────────────────────────────────────────

class KnowledgeEntity(Base):
    """Canonical entities (People, Organizations, Concepts) extracted from memory."""
    __tablename__ = "knowledge_entities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)  # PERSON, ORG, CONCEPT, EVENT
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(String, nullable=True)
    from pgvector.sqlalchemy import Vector
    name_embedding: Mapped[list] = mapped_column(Vector(1536), nullable=True)
    metadata_col: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    
    status: Mapped[MemoryStatus] = mapped_column(Enum(MemoryStatus, native_enum=False), default=MemoryStatus.ACTIVE)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by: Mapped[uuid.UUID] = mapped_column(nullable=True)

class KnowledgeEdge(Base):
    """Relationships between KnowledgeEntities."""
    __tablename__ = "knowledge_edges"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_entities.id", ondelete="CASCADE"), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_entities.id", ondelete="CASCADE"), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)  # KNOWS, WORKS_AT, etc.
    metadata_col: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class MemoryEntityLink(Base):
    """Link Episodic or Fact memory to KnowledgeEntities."""
    __tablename__ = "memory_entity_links"

    memory_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("memory_entries.id", ondelete="CASCADE"), primary_key=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_entities.id", ondelete="CASCADE"), primary_key=True)

# ── User Understanding & Preference Layer ─────────────────────────────────────

class ExplicitPreference(Base):
    """Explicitly stated or strongly inferred user preferences."""
    __tablename__ = "explicit_preferences"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

class ExplicitDislike(Base):
    """Explicit negative signals (rejections, corrections)."""
    __tablename__ = "explicit_dislikes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[dict] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

class UserConstraint(Base):
    """Rules or constraints defined by the user (e.g., 'Never use emojis')."""
    __tablename__ = "user_constraints"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    constraint_type: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

class Episode(Base):
    """High-level summary of a goal-oriented interaction."""
    __tablename__ = "memory_episodes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=True)
    goal: Mapped[str] = mapped_column(String, nullable=True)
    outcome: Mapped[str] = mapped_column(String(32))  # completed, failed, abandoned
    events: Mapped[list] = mapped_column(JSONB, default=list) # List of major event IDs or descriptions
    lessons: Mapped[list] = mapped_column(JSONB, default=list) # What was learned?
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class Routine(Base):
    """Recurring patterns identified by the memory system."""
    __tablename__ = "memory_routines"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    metadata_col: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

# ── Extraction & Chunking Layer ──────────────────────────────────────────────

class KnowledgeChunk(Base):
    """Bridge between raw text and graph entities (Source Attribution)."""
    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    
    text: Mapped[str] = mapped_column(String, nullable=False)
    index: Mapped[int] = mapped_column(Integer, default=0)
    
    source_type: Mapped[str] = mapped_column(String(32))  # episode, notebook, turn
    source_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    
    from pgvector.sqlalchemy import Vector
    embedding: Mapped[list] = mapped_column(Vector(1536), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class ChunkEntityLink(Base):
    """HAS_ENTITY relationship: links chunks to the entities they mention."""
    __tablename__ = "chunk_entity_links"

    chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="CASCADE"), primary_key=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_entities.id", ondelete="CASCADE"), primary_key=True)
