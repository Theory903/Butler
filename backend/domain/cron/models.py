"""Cron domain models — Phase 8b.

Persistence for Butler cron jobs and execution logs.
Aligns with OpenClaw's durable scheduler pattern.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class CronDeliveryMode(StrEnum):
    WEBHOOK = "webhook"
    ORCHESTRATOR = "orchestrator"


class CronJobStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    EXPIRED = "expired"


class ButlerCronJob(Base):
    """Persistent representation of a Butler cron schedule."""

    __tablename__ = "cron_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Schedule
    expression: Mapped[str] = mapped_column(String(50), nullable=False)  # 5-field crontab
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="UTC")

    # Delivery
    delivery_mode: Mapped[CronDeliveryMode] = mapped_column(
        String(20), nullable=False, default=CronDeliveryMode.ORCHESTRATOR
    )
    delivery_meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # State
    status: Mapped[CronJobStatus] = mapped_column(
        String(20), nullable=False, default=CronJobStatus.ACTIVE
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    # Relationships
    runs: Mapped[list[ButlerCronRun]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ButlerCronJob {self.name} [{self.expression}] status={self.status}>"


class ButlerCronRun(Base):
    """Audit log for a specific cron execution."""

    __tablename__ = "cron_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cron_jobs.id"), nullable=False, index=True
    )

    # Execution details
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success | error
    result_meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    job: Mapped[ButlerCronJob] = relationship(back_populates="runs")

    def __repr__(self) -> str:
        return f"<ButlerCronRun {self.job_id} at {self.triggered_at} status={self.status}>"
