"""Marketplace and Plugin Lifecycle Domain Models.

Implements Wave A of Phase 12 Product Ecosystem layer.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, UUID, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database import Base


class PackageState(str, enum.Enum):
    """Lifecycle states for a plugin/skill package."""
    STAGED = "staged"       # Downloaded but not yet promoted
    ACTIVE = "active"       # Currently running version
    PREVIOUS = "previous"   # Rollback target
    FAILED = "failed"       # Installation failure
    RETIRED = "retired"     # Manually disabled or deleted


class RiskTier(int, enum.Enum):
    """Capability-derived risk classification."""
    TIER_0 = 0  # Content-only (Skills/Bundles)
    TIER_1 = 1  # Standard Providers/Helpers
    TIER_2 = 2  # Extended Routes/Native Tools
    TIER_3 = 3  # Host Control/Device Bridge (High Risk)


class PluginPackage(Base):
    """Represents a unique plugin/skill package from ClawHub or local source."""
    __tablename__ = "butler_plugin_packages"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    package_id: Mapped[str] = mapped_column(String(255), unique=True, index=True) # e.g. "clawhub:anthropic-provider"
    name: Mapped[str] = mapped_column(String(255))
    publisher: Mapped[str] = mapped_column(String(255))
    current_version: Mapped[Optional[str]] = mapped_column(String(50))
    state: Mapped[PackageState] = mapped_column(
        Enum(PackageState), default=PackageState.STAGED, index=True
    )
    risk_tier: Mapped[RiskTier] = mapped_column(Enum(RiskTier), default=RiskTier.TIER_0)
    source_url: Mapped[Optional[str]] = mapped_column(String(512))
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    versions: Mapped[List[PluginVersion]] = relationship(
        "PluginVersion", back_populates="package", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[List[SecurityAuditLog]] = relationship(
        "SecurityAuditLog", back_populates="package"
    )


class PluginVersion(Base):
    """Specific version of a plugin package with its manifest and binary metadata."""
    __tablename__ = "butler_plugin_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("butler_plugin_packages.id"), index=True)
    version: Mapped[str] = mapped_column(String(50))
    manifest: Mapped[Dict[str, Any]] = mapped_column(JSON) # Serialized openclaw.plugin.json
    archive_hash: Mapped[str] = mapped_column(String(128)) # SHA256 of the archive
    signature: Mapped[Optional[str]] = mapped_column(Text) # ED25519 signature
    
    # Compatibility checks
    min_gateway_version: Mapped[str] = mapped_column(String(50))
    plugin_api_version: Mapped[str] = mapped_column(String(50))
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    package: Mapped[PluginPackage] = relationship("PluginPackage", back_populates="versions")


class SecurityAuditLog(Base):
    """Immutable audit trail for plugin lifecycle events and security gates."""
    __tablename__ = "butler_security_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    package_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("butler_plugin_packages.id"), index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID, index=True) # Operator/System ID
    action: Mapped[str] = mapped_column(String(100)) # "install", "promote", "rollback", "gate_failure"
    
    # Gate details
    gate_results: Mapped[Dict[str, Any]] = mapped_column(JSON) # Details for Gate A/B/C/D
    status: Mapped[str] = mapped_column(String(50)) # "success", "failed"
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    
    details: Mapped[Dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    package: Mapped[Optional[PluginPackage]] = relationship("PluginPackage", back_populates="audit_logs")
