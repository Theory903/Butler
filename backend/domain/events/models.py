"""Events domain models — SQLAlchemy ORM for Operational Data.

Implements the infrastructure backbone schema from docs/02-services/data.md.
These models own the persistence for:
  - outbox_events (Transactional Outbox Pattern)
  - audit_events (Canonical Operational Truth Ledger)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)

def _outbox_expiry() -> datetime:
    return _now() + timedelta(days=7)


class OutboxEvent(Base):
    """Transactional Outbox component for exact-once event publishing."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        {"postgresql_partition_by": "RANGE (created_at)"}
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # Event identity
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Payload
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    
    # Routing
    target_topic: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # State
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Timing
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, primary_key=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_outbox_expiry
    )

    def __repr__(self) -> str:
        return f"<OutboxEvent {self.aggregate_type}:{self.event_type} status={self.status}>"


class AuditEvent(Base):
    """Canonical operational ledger capturing all structural domain changes."""

    __tablename__ = "audit_events"
    __table_args__ = (
        {"postgresql_partition_by": "RANGE (observed_at)"}
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # Canonical envelope
    event_version: Mapped[str] = mapped_column(String(10), nullable=False, default="v1")
    event_family: Mapped[str] = mapped_column(String(30), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Actor context
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    
    # Session context
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    
    # Resource context
    resource_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    
    # Correlation
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    trace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    
    # Event data
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sensitivity_class: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    
    # Payload
    event_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    
    # Timing
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    def __repr__(self) -> str:
        return f"<AuditEvent {self.actor_id} -> {self.action} ({self.outcome})>"
