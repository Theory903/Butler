import uuid
from datetime import datetime, UTC
from typing import Optional, List
from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from infrastructure.database import Base

def now_utc():
    return datetime.now(UTC)

class Meeting(Base):
    """A scheduled or real-time meeting session."""
    __tablename__ = "meetings"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    calendar_event_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(512))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    host: Mapped[Optional[str]] = mapped_column(String(255))
    participants: Mapped[list] = mapped_column(JSONB, default=list)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    # Relationships
    transcription: Mapped["Transcription"] = relationship(back_populates="meeting", uselist=False, cascade="all, delete-orphan")
    summary: Mapped["MeetingSummary"] = relationship(back_populates="meeting", uselist=False, cascade="all, delete-orphan")

class Transcription(Base):
    """Full transcript of a meeting session."""
    __tablename__ = "transcriptions"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), unique=True)
    content: Mapped[str] = mapped_column(Text, default="")
    segments: Mapped[list] = mapped_column(JSONB, default=list)  # List of {speaker, text, timestamp}
    
    meeting: Mapped["Meeting"] = relationship(back_populates="transcription")

class MeetingSummary(Base):
    """AI-generated summary and extracted items from a meeting."""
    __tablename__ = "meeting_summaries"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), unique=True)
    summary_text: Mapped[str] = mapped_column(Text)
    action_items: Mapped[list] = mapped_column(JSONB, default=list)
    key_decisions: Mapped[list] = mapped_column(JSONB, default=list)
    
    meeting: Mapped["Meeting"] = relationship(back_populates="summary")
