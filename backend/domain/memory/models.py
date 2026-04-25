from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database import Base

EMBEDDING_DIMENSION = 1536


def now_utc() -> datetime:
    return datetime.now(UTC)


class MemoryStatus(enum.StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    CONFLICTED = "conflicted"


memory_status_enum = Enum(
    MemoryStatus,
    name="memory_status_enum",
    native_enum=False,
    validate_strings=True,
)


class MemoryEntry(Base):
    """Canonical memory record with temporal and retrieval metadata."""

    __tablename__ = "memory_entries"
    __table_args__ = (
        Index(
            "ix_memory_entries_tenant_account_type_status",
            "tenant_id",
            "account_id",
            "memory_type",
            "status",
        ),
        Index(
            "ix_memory_entries_tenant_account_session_created",
            "tenant_id",
            "account_id",
            "session_id",
            "created_at",
        ),
        Index("ix_memory_entries_tenant_account_created", "tenant_id", "account_id", "created_at"),
        Index(
            "ix_memory_entries_tenant_account_valid_from", "tenant_id", "account_id", "valid_from"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    memory_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    content: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSION),
        nullable=True,
    )
    importance: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.5,
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
    )
    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="conversation",
    )
    session_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    tags: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    status: Mapped[MemoryStatus] = mapped_column(
        memory_status_enum,
        nullable=False,
        default=MemoryStatus.ACTIVE,
        index=True,
    )
    metadata_col: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_utc,
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("memory_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_utc,
        index=True,
    )
    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_utc,
    )
    access_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )


class ConversationTurn(Base):
    """Individual conversation turn within a session."""

    __tablename__ = "conversation_turns"
    __table_args__ = (
        Index(
            "ix_conversation_turns_tenant_account_session_turn",
            "tenant_id",
            "account_id",
            "session_id",
            "turn_index",
        ),
        UniqueConstraint(
            "tenant_id", "account_id", "session_id", "turn_index", name="uq_conversation_turn_order"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    session_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    turn_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    intent: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    tool_calls: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    metadata_col: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_utc,
        index=True,
    )


class KnowledgeEntity(Base):
    """Canonical entities extracted from memory and grounded content."""

    __tablename__ = "knowledge_entities"
    __table_args__ = (
        Index(
            "ix_knowledge_entities_tenant_account_type_name",
            "tenant_id",
            "account_id",
            "entity_type",
            "name",
        ),
        Index("ix_knowledge_entities_tenant_account_status", "tenant_id", "account_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    name_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSION),
        nullable=True,
    )
    metadata_col: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_utc,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_utc,
        onupdate=now_utc,
    )
    status: Mapped[MemoryStatus] = mapped_column(
        memory_status_enum,
        nullable=False,
        default=MemoryStatus.ACTIVE,
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_entities.id", ondelete="SET NULL"),
        nullable=True,
    )


class KnowledgeEdge(Base):
    """Relationship edge between two knowledge entities."""

    __tablename__ = "knowledge_edges"
    __table_args__ = (
        Index(
            "ix_knowledge_edges_tenant_account_relation", "tenant_id", "account_id", "relation_type"
        ),
        Index("ix_knowledge_edges_source_target", "source_id", "target_id"),
        UniqueConstraint(
            "tenant_id",
            "account_id",
            "source_id",
            "target_id",
            "relation_type",
            name="uq_knowledge_edge",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    metadata_col: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_utc,
    )


class MemoryEntityLink(Base):
    """Link memory entries to extracted knowledge entities."""

    __tablename__ = "memory_entity_links"
    __table_args__ = (Index("ix_memory_entity_links_entity_id", "entity_id"),)

    memory_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("memory_entries.id", ondelete="CASCADE"),
        primary_key=True,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_entities.id", ondelete="CASCADE"),
        primary_key=True,
    )


class ExplicitPreference(Base):
    """Explicitly stated or strongly inferred user preferences."""

    __tablename__ = "explicit_preferences"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "account_id", "category", "key", name="uq_explicit_preference"
        ),
        Index(
            "ix_explicit_preferences_tenant_account_category", "tenant_id", "account_id", "category"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    value: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_utc,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_utc,
        onupdate=now_utc,
    )


class ExplicitDislike(Base):
    """Explicit negative user signals."""

    __tablename__ = "explicit_dislikes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "account_id", "key", name="uq_explicit_dislike"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    reason: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_utc,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_utc,
        onupdate=now_utc,
    )


class UserConstraint(Base):
    """User-defined operational or stylistic constraints."""

    __tablename__ = "user_constraints"
    __table_args__ = (
        Index(
            "ix_user_constraints_tenant_account_type_active",
            "tenant_id",
            "account_id",
            "constraint_type",
            "active",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    constraint_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    value: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_utc,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_utc,
        onupdate=now_utc,
    )


class Episode(Base):
    """High-level summary of a goal-oriented interaction episode."""

    __tablename__ = "memory_episodes"
    __table_args__ = (
        Index("ix_memory_episodes_tenant_account_session", "tenant_id", "account_id", "session_id"),
        Index("ix_memory_episodes_tenant_account_created", "tenant_id", "account_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    session_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    goal: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    outcome: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    events: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    lessons: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_utc,
    )


class Routine(Base):
    """Recurring behavior pattern identified from user activity."""

    __tablename__ = "memory_routines"
    __table_args__ = (
        Index("ix_memory_routines_tenant_account_name", "tenant_id", "account_id", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    occurrences: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    metadata_col: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_utc,
    )
    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_utc,
    )


class KnowledgeChunk(Base):
    """Chunked text unit used for retrieval and source attribution."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        Index(
            "ix_knowledge_chunks_tenant_account_source",
            "tenant_id",
            "account_id",
            "source_type",
            "source_id",
        ),
        Index(
            "ix_knowledge_chunks_tenant_account_created", "tenant_id", "account_id", "created_at"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSION),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_utc,
    )


class ChunkEntityLink(Base):
    """Link chunks to entities they mention."""

    __tablename__ = "chunk_entity_links"
    __table_args__ = (Index("ix_chunk_entity_links_entity_id", "entity_id"),)

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_chunks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_entities.id", ondelete="CASCADE"),
        primary_key=True,
    )
