import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database import Base


class DeliveryRecord(Base):
    """Tracking the entire delivery lifecycle of a message."""

    __tablename__ = "comm_delivery_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)

    recipient: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sender_profile_id: Mapped[str] = mapped_column(String(255), nullable=True)

    # Normalized State
    phase: Mapped[str] = mapped_column(String(50), nullable=False, default="accepted")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued")
    terminal: Mapped[bool] = mapped_column(Boolean, default=False)
    retryable: Mapped[bool] = mapped_column(Boolean, default=True)

    # Raw Provider Data
    provider_message_id: Mapped[str] = mapped_column(String(255), nullable=True, index=True)
    provider_status_raw: Mapped[str] = mapped_column(String(255), nullable=True)
    provider_event_type: Mapped[str] = mapped_column(String(100), nullable=True)

    # Timing
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    first_provider_acceptance: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    final_delivery: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ConsentState(Base):
    """Global suppressions, bounces, and complaints."""

    __tablename__ = "comm_consent_states"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(50), nullable=False)  # active, suppressed, pending
    reason: Mapped[str] = mapped_column(
        String(255), nullable=True
    )  # user_opt_out, hard_bounce, complaint

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class SenderProfile(Base):
    """Internal profiles used to route messages to specific providers safely."""

    __tablename__ = "comm_sender_profiles"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # e.g., whatsapp_business, personal_email
    verified: Mapped[bool] = mapped_column(Boolean, default=False)

    capabilities: Mapped[list[str]] = mapped_column(
        JSON, default=list
    )  # e.g., ["transactional", "marketing"]

    domain: Mapped[str] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[str] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
