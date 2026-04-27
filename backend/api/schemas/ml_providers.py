"""API schemas for provider configuration and management."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, SecretStr


class ProviderType(str, Enum):
    """Supported provider types."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GROQ = "groq"
    VERTEX_AI = "vertex_ai"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
    VLLM = "vllm"


class ProviderCapability(str, Enum):
    """Provider capabilities."""
    CHAT = "chat"
    STREAMING = "streaming"
    TOOLS = "tools"
    VISION = "vision"
    FUNCTION_CALLING = "function_calling"
    JSON_MODE = "json_mode"
    EMBEDDINGS = "embeddings"


class ProviderModel(BaseModel):
    """Model information for a provider."""
    
    name: str
    display_name: str
    provider: ProviderType
    context_window: int
    max_output_tokens: int
    capabilities: list[ProviderCapability]
    pricing_per_1k_input: float
    pricing_per_1k_output: float
    tier: str = Field(default="T2", description="Reasoning tier: T0, T1, T2, T3")
    is_available: bool = True


class TenantProviderPreference(BaseModel):
    """Tenant's preferred provider and model configuration."""
    
    tenant_id: str
    provider: ProviderType
    model: str
    use_custom_key: bool = False
    custom_key_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TenantCustomApiKey(BaseModel):
    """Custom API key stored for a tenant."""
    
    id: str
    tenant_id: str
    provider: ProviderType
    key_name: str
    encrypted_key: str  # Encrypted at rest
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: datetime | None = None
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderConfigRequest(BaseModel):
    """Request to set tenant provider configuration."""
    
    provider: ProviderType
    model: str
    use_custom_key: bool = False
    custom_key_id: str | None = None


class CustomApiKeyRequest(BaseModel):
    """Request to add a custom API key."""
    
    provider: ProviderType
    key_name: str
    api_key: SecretStr
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderListResponse(BaseModel):
    """Response listing available providers and models."""
    
    default_provider: ProviderType
    default_model: str
    providers: dict[ProviderType, list[ProviderModel]]
    tenant_preferences: TenantProviderPreference | None = None
    custom_keys: list[TenantCustomApiKey] = Field(default_factory=list)
