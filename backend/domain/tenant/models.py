"""Tenant domain models — SQLAlchemy ORM.

Implements tenant-specific tables for multi-tenant SaaS security:
  - tenant_credentials (encrypted provider credentials)
  - usage_events (append-only usage tracking for billing)
  - audit_events (security event logging)
  - approval_requests (approval workflow for sensitive operations)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class TenantCredential(Base):
    """Encrypted provider credentials for a tenant.

    Credentials are encrypted at rest and have short TTLs.
    Rotation is handled automatically based on expiry.
    """

    __tablename__ = "tenant_credentials"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_tenant_credentials_tenant_provider"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    tenant_slug: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        unique=True,  # display only
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    credential_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    credential_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<TenantCredential id={self.id} tenant_id={self.tenant_id} provider={self.provider!r}>"
        )


class UsageEvent(Base):
    """Append-only usage event for billing and analytics.

    Events are never mutated after creation.
    Used for metering, quota enforcement, and billing.
    """

    __tablename__ = "usage_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, index=True
    )

    def __repr__(self) -> str:
        return f"<UsageEvent id={self.id} tenant_id={self.tenant_id} resource_type={self.resource_type!r}>"


class AuditEvent(Base):
    """Security audit event for compliance and forensics.

    Events are immutable - never modified after creation.
    Captures security-relevant events for all tenant actions.
    """

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    resource: Mapped[str | None] = mapped_column(String(256), nullable=True)
    action: Mapped[str] = mapped_column(String(256), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, index=True
    )

    def __repr__(self) -> str:
        return (
            f"<AuditEvent id={self.id} tenant_id={self.tenant_id} event_type={self.event_type!r}>"
        )


class ApprovalRequest(Base):
    """Approval request for sensitive operations.

    Tracks approval workflow state for operations requiring human approval.
    """

    __tablename__ = "approval_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_id: Mapped[str] = mapped_column(String(256), nullable=False)
    action: Mapped[str] = mapped_column(String(256), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    denied_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    denied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    denial_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, index=True
    )
    metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    @property
    def is_expired(self) -> bool:
        return datetime.now(UTC) > self.expires_at

    @property
    def is_pending(self) -> bool:
        return self.status == "pending" and not self.is_expired

    @property
    def is_approved(self) -> bool:
        return self.status == "approved"

    @property
    def is_denied(self) -> bool:
        return self.status == "denied"

    def __repr__(self) -> str:
        return f"<ApprovalRequest id={self.id} tenant_id={self.tenant_id} status={self.status!r}>"
