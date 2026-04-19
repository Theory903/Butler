"""Device domain models — SQLAlchemy ORM.

Implements the persistent operational registry for the Ambient / Environment layer,
tracking hardware identities, protocol semantics, capabilities, and trust states.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database import Base

def _now() -> datetime:
    return datetime.now(timezone.utc)

class DeviceRegistry(Base):
    """The formal hardware/ambient entity bound to a Butler Account."""

    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    
    # Trust & Topology
    trust_state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")  # pending, trusted, compromised, unpaired
    online_state: Mapped[str] = mapped_column(String(32), nullable=False, default="offline") # online, offline, degraded
    
    # Hardware & Network signature
    protocol: Mapped[str] = mapped_column(String(32), nullable=False, default="api")         # matter, zigbee, api, companion
    vendor: Mapped[str] = mapped_column(String(128), nullable=False, default="unknown")
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="unknown")
    
    # Functional semantics mapping out automation abilities
    capabilities: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)          # list of string IDs matching Butler Capability Enums
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    def __repr__(self) -> str:
        return f"<Device {self.vendor} {self.model} (Trust: {self.trust_state})>"
