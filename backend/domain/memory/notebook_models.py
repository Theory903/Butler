import uuid
from datetime import datetime, UTC
from typing import List, Optional
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector

from infrastructure.database import Base

def now_utc():
    return datetime.now(UTC)

class Notebook(Base):
    """A research project container for sources and notes."""
    __tablename__ = "notebooks"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_col: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    # Relationships
    sources: Mapped[List["Source"]] = relationship(
        secondary="notebook_sources", back_populates="notebooks"
    )
    notes: Mapped[List["Note"]] = relationship(
        secondary="notebook_notes", back_populates="notebooks"
    )

class Source(Base):
    """A document, video, or web source for research."""
    __tablename__ = "sources"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(512))
    source_type: Mapped[str] = mapped_column(String(32))  # pdf, youtube, web, local
    asset: Mapped[dict] = mapped_column(JSONB, default=dict)  # file_path, url, etc.
    full_text: Mapped[Optional[str]] = mapped_column(Text)
    topics: Mapped[list] = mapped_column(JSONB, default=list)
    metadata_col: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    # Relationships
    notebooks: Mapped[List["Notebook"]] = relationship(
        secondary="notebook_sources", back_populates="sources"
    )
    insights: Mapped[List["SourceInsight"]] = relationship(back_populates="source", cascade="all, delete-orphan")
    embeddings: Mapped[List["SourceEmbedding"]] = relationship(back_populates="source", cascade="all, delete-orphan")

class Note(Base):
    """User-created or AI-generated note related to a notebook."""
    __tablename__ = "notes"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(512))
    content: Mapped[Optional[str]] = mapped_column(Text)
    note_type: Mapped[str] = mapped_column(String(16), default="human")  # human, ai
    metadata_col: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    # Relationships
    notebooks: Mapped[List["Notebook"]] = relationship(
        secondary="notebook_notes", back_populates="notes"
    )

class SourceInsight(Base):
    """Extracted insight from a specific source."""
    __tablename__ = "source_insights"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    insight_type: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    metadata_col: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    source: Mapped["Source"] = relationship(back_populates="insights")

class SourceEmbedding(Base):
    """Vector embedding for a chunk of source text."""
    __tablename__ = "source_embeddings"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Vector] = mapped_column(Vector(1536))  # Default for Ada, adjust as needed

    source: Mapped["Source"] = relationship(back_populates="embeddings")

class NotebookSources(Base):
    """Many-to-many join table for Notebooks and Sources."""
    __tablename__ = "notebook_sources"
    
    notebook_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("notebooks.id", ondelete="CASCADE"), primary_key=True)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True)

class NotebookNotes(Base):
    """Many-to-many join table for Notebooks and Notes."""
    __tablename__ = "notebook_notes"
    
    notebook_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("notebooks.id", ondelete="CASCADE"), primary_key=True)
    note_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True)

class EpisodeProfile(Base):
    """Configuration for podcast episode generation."""
    __tablename__ = "episode_profiles"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    speaker_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("speaker_profiles.id"))
    num_segments: Mapped[int] = mapped_column(Integer, default=5)
    language: Mapped[str] = mapped_column(String(16), default="en-US")
    default_briefing: Mapped[str] = mapped_column(Text)
    metadata_col: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

class SpeakerProfile(Base):
    """Voice and personality configuration for podcast speakers."""
    __tablename__ = "speaker_profiles"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    speakers: Mapped[dict] = mapped_column(JSONB) # List of speaker configs
    metadata_col: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
