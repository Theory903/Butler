"""Database models for tenant provider configuration and custom API keys."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Column, String, DateTime, Boolean, Text, Index
from sqlalchemy.dialects.postgresql import JSON

from infrastructure.database import Base


class TenantProviderPreference(Base):
    """Database model for tenant provider preferences."""
    
    __tablename__ = "tenant_provider_preferences"
    
    tenant_id = Column(String, primary_key=True)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=False)
    use_custom_key = Column(Boolean, default=False, nullable=False)
    custom_key_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    extra_metadata = Column(JSON, default=dict, nullable=False)
    
    __table_args__ = (
        Index("idx_tenant_provider_preferences_tenant", "tenant_id"),
    )


class TenantCustomApiKey(Base):
    """Database model for tenant custom API keys."""
    
    __tablename__ = "tenant_custom_api_keys"
    
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    key_name = Column(String, nullable=False)
    encrypted_key = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    extra_metadata = Column(JSON, default=dict, nullable=False)
    
    __table_args__ = (
        Index("idx_tenant_custom_api_keys_tenant", "tenant_id"),
        Index("idx_tenant_custom_api_keys_provider", "provider"),
        Index("idx_tenant_custom_api_keys_tenant_provider", "tenant_id", "provider"),
    )
