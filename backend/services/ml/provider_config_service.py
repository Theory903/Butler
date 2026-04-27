"""Service for managing tenant provider configuration and custom API keys."""

from __future__ import annotations

from typing import Any

from api.schemas.ml_providers import (
    ProviderType,
    ProviderModel,
    ProviderCapability,
    ProviderListResponse,
    TenantProviderPreference,
    TenantCustomApiKey,
    ProviderConfigRequest,
    CustomApiKeyRequest,
)
from infrastructure.ml.provider_config_repository import ProviderConfigRepository
from services.ml_runtime.openclaw_layer.provider_registry import (
    ProviderSpec,
    create_default_registry,
)


class ProviderConfigService:
    """Service for managing provider configuration."""
    
    def __init__(
        self,
        repository: ProviderConfigRepository,
        default_provider: ProviderType = ProviderType.OPENAI,
        default_model: str = "gpt-4o",
    ):
        self.repository = repository
        self.default_provider = default_provider
        self.default_model = default_model
        self._registry = create_default_registry()
    
    async def list_providers(
        self,
        tenant_id: str,
    ) -> ProviderListResponse:
        """List all available providers and models."""
        # Get tenant preferences and custom keys
        preference = await self.repository.get_tenant_preference(tenant_id)
        custom_keys = await self.repository.get_custom_keys(tenant_id)
        
        # Build provider list from registry
        providers: dict[ProviderType, list[ProviderModel]] = {}
        
        for spec in self._registry.list_providers():
            provider_type = self._map_provider_type(spec.name)
            if provider_type not in providers:
                providers[provider_type] = []
            
            # Get available models for this provider
            models = self._get_models_for_provider(spec)
            providers[provider_type].extend(models)
        
        return ProviderListResponse(
            default_provider=self.default_provider,
            default_model=self.default_model,
            providers=providers,
            tenant_preferences=preference,
            custom_keys=custom_keys,
        )
    
    async def set_provider_preference(
        self,
        tenant_id: str,
        request: ProviderConfigRequest,
    ) -> TenantProviderPreference:
        """Set tenant's preferred provider and model."""
        # Validate that the provider and model are available
        provider_spec = self._registry.get_provider(request.provider.value)
        if not provider_spec:
            raise ValueError(f"Provider not found: {request.provider}")
        
        # Validate model
        models = self._get_models_for_provider(provider_spec)
        model_names = [m.name for m in models]
        if request.model not in model_names:
            raise ValueError(
                f"Model {request.model} not available for provider {request.provider}. "
                f"Available models: {', '.join(model_names)}"
            )
        
        # If using custom key, validate it exists
        if request.use_custom_key and request.custom_key_id:
            custom_key = await self.repository.get_custom_key(tenant_id, request.custom_key_id)
            if not custom_key or custom_key.provider != request.provider:
                raise ValueError(f"Custom key not found or provider mismatch")
        
        return await self.repository.set_tenant_preference(tenant_id, request)
    
    async def get_provider_preference(
        self,
        tenant_id: str,
    ) -> TenantProviderPreference | None:
        """Get tenant's provider preference."""
        return await self.repository.get_tenant_preference(tenant_id)
    
    async def delete_provider_preference(
        self,
        tenant_id: str,
    ) -> bool:
        """Delete tenant's provider preference (revert to default)."""
        return await self.repository.delete_tenant_preference(tenant_id)
    
    async def add_custom_key(
        self,
        tenant_id: str,
        request: CustomApiKeyRequest,
    ) -> TenantCustomApiKey:
        """Add a custom API key for a tenant."""
        return await self.repository.add_custom_key(tenant_id, request)
    
    async def get_custom_keys(
        self,
        tenant_id: str,
        provider: ProviderType | None = None,
    ) -> list[TenantCustomApiKey]:
        """Get custom API keys for a tenant."""
        return await self.repository.get_custom_keys(tenant_id, provider)
    
    async def delete_custom_key(
        self,
        tenant_id: str,
        key_id: str,
    ) -> bool:
        """Delete a custom API key."""
        return await self.repository.delete_custom_key(tenant_id, key_id)
    
    async def get_provider_for_tenant(
        self,
        tenant_id: str,
    ) -> tuple[ProviderType, str, str | None]:
        """Get the provider, model, and custom key for a tenant.
        
        Returns:
            (provider, model, custom_api_key) - custom_api_key is None if not using custom key
        """
        preference = await self.repository.get_tenant_preference(tenant_id)
        
        if preference:
            provider = preference.provider
            model = preference.model
            
            if preference.use_custom_key and preference.custom_key_id:
                custom_key = await self.repository.get_custom_key(tenant_id, preference.custom_key_id)
                if custom_key:
                    # Update last used
                    await self.repository.update_last_used(tenant_id, preference.custom_key_id)
                    decrypted_key = self.repository._decrypt_key(custom_key.encrypted_key)
                    return provider, model, decrypted_key
            
            return provider, model, None
        
        # Return default
        return self.default_provider, self.default_model, None
    
    def _map_provider_type(self, provider_name: str) -> ProviderType:
        """Map provider name to ProviderType enum."""
        provider_lower = provider_name.lower()
        
        if "openai" in provider_lower or "gpt" in provider_lower:
            return ProviderType.OPENAI
        elif "anthropic" in provider_lower or "claude" in provider_lower:
            return ProviderType.ANTHROPIC
        elif "groq" in provider_lower:
            return ProviderType.GROQ
        elif "vertex" in provider_lower or "gemini" in provider_lower:
            return ProviderType.VERTEX_AI
        elif "openrouter" in provider_lower:
            return ProviderType.OPENROUTER
        elif "ollama" in provider_lower:
            return ProviderType.OLLAMA
        elif "vllm" in provider_lower:
            return ProviderType.VLLM
        
        return ProviderType.OPENAI  # Default
    
    def _get_models_for_provider(self, spec: ProviderSpec) -> list[ProviderModel]:
        """Get available models for a provider spec."""
        # This would typically come from provider API or configuration
        # For now, return a default model based on the provider
        provider_type = self._map_provider_type(spec.name)
        
        models = []
        
        if provider_type == ProviderType.OPENAI:
            models.extend([
                ProviderModel(
                    name="gpt-4o",
                    display_name="GPT-4o",
                    provider=ProviderType.OPENAI,
                    context_window=128000,
                    max_output_tokens=4096,
                    capabilities=[
                        ProviderCapability.CHAT,
                        ProviderCapability.STREAMING,
                        ProviderCapability.TOOLS,
                        ProviderCapability.FUNCTION_CALLING,
                        ProviderCapability.JSON_MODE,
                        ProviderCapability.VISION,
                    ],
                    pricing_per_1k_input=0.005,
                    pricing_per_1k_output=0.015,
                    tier="T2",
                ),
                ProviderModel(
                    name="gpt-4o-mini",
                    display_name="GPT-4o Mini",
                    provider=ProviderType.OPENAI,
                    context_window=128000,
                    max_output_tokens=16384,
                    capabilities=[
                        ProviderCapability.CHAT,
                        ProviderCapability.STREAMING,
                        ProviderCapability.TOOLS,
                        ProviderCapability.FUNCTION_CALLING,
                        ProviderCapability.JSON_MODE,
                        ProviderCapability.VISION,
                    ],
                    pricing_per_1k_input=0.00015,
                    pricing_per_1k_output=0.0006,
                    tier="T1",
                ),
            ])
        elif provider_type == ProviderType.ANTHROPIC:
            models.extend([
                ProviderModel(
                    name="claude-sonnet-4-6-20250529",
                    display_name="Claude Sonnet 4.6",
                    provider=ProviderType.ANTHROPIC,
                    context_window=200000,
                    max_output_tokens=8192,
                    capabilities=[
                        ProviderCapability.CHAT,
                        ProviderCapability.STREAMING,
                        ProviderCapability.TOOLS,
                        ProviderCapability.FUNCTION_CALLING,
                        ProviderCapability.VISION,
                    ],
                    pricing_per_1k_input=0.003,
                    pricing_per_1k_output=0.015,
                    tier="T2",
                ),
                ProviderModel(
                    name="claude-haiku-4-20250529",
                    display_name="Claude Haiku 4",
                    provider=ProviderType.ANTHROPIC,
                    context_window=200000,
                    max_output_tokens=4096,
                    capabilities=[
                        ProviderCapability.CHAT,
                        ProviderCapability.STREAMING,
                        ProviderCapability.VISION,
                    ],
                    pricing_per_1k_input=0.00025,
                    pricing_per_1k_output=0.00125,
                    tier="T1",
                ),
            ])
        elif provider_type == ProviderType.GROQ:
            models.extend([
                ProviderModel(
                    name="llama-3.3-70b-versatile",
                    display_name="Llama 3.3 70B",
                    provider=ProviderType.GROQ,
                    context_window=128000,
                    max_output_tokens=4096,
                    capabilities=[
                        ProviderCapability.CHAT,
                        ProviderCapability.STREAMING,
                        ProviderCapability.TOOLS,
                        ProviderCapability.FUNCTION_CALLING,
                    ],
                    pricing_per_1k_input=0.00059,
                    pricing_per_1k_output=0.00079,
                    tier="T1",
                ),
            ])
        
        return models
