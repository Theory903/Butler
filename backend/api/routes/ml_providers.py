"""API routes for provider configuration and management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.ml_providers import (
    ProviderType,
    ProviderListResponse,
    TenantProviderPreference,
    TenantCustomApiKey,
    ProviderConfigRequest,
    CustomApiKeyRequest,
)
from api.routes.gateway import get_current_account
from core.deps import get_db
from services.ml.provider_config_service import ProviderConfigService
from infrastructure.ml.provider_config_repository import ProviderConfigRepository


router = APIRouter(prefix="/api/v1/ml/providers", tags=["ML Providers"])


async def get_provider_config_service(
    db: AsyncSession = Depends(get_db),
) -> ProviderConfigService:
    """Dependency to get provider config service."""
    # Get encryption key from environment
    import os
    encryption_key = os.environ.get("PROVIDER_ENCRYPTION_KEY")
    repository = ProviderConfigRepository(db, encryption_key)
    
    # Get default provider from environment
    default_provider = ProviderType(os.environ.get("DEFAULT_LLM_PROVIDER", "openai"))
    default_model = os.environ.get("DEFAULT_OPENAI_MODEL", "gpt-4o")
    
    return ProviderConfigService(
        repository=repository,
        default_provider=default_provider,
        default_model=default_model,
    )


async def get_current_tenant_id(account: AccountContext = Depends(get_current_account)) -> str:
    """Get current tenant ID from authenticated account context."""
    # Use tid (tenant ID) if available, otherwise fall back to aid (account ID)
    # This handles both multi-tenant and single-tenant deployments
    return getattr(account, "tid", None) or account.aid


@router.get(
    "",
    response_model=ProviderListResponse,
    summary="List available providers and models",
    description="List all available providers, their models, capabilities, and pricing. Includes tenant's current preferences and custom API keys.",
)
async def list_providers(
    tenant_id: str = Depends(get_current_tenant_id),
    service: ProviderConfigService = Depends(get_provider_config_service),
) -> ProviderListResponse:
    """List all available providers and models for the tenant."""
    return await service.list_providers(tenant_id)


@router.post(
    "/preference",
    response_model=TenantProviderPreference,
    status_code=status.HTTP_201_CREATED,
    summary="Set provider preference",
    description="Set the tenant's preferred provider and model. Can optionally use a custom API key.",
)
async def set_provider_preference(
    request: ProviderConfigRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    service: ProviderConfigService = Depends(get_provider_config_service),
) -> TenantProviderPreference:
    """Set tenant's provider preference."""
    try:
        return await service.set_provider_preference(tenant_id, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/preference",
    response_model=TenantProviderPreference | None,
    summary="Get provider preference",
    description="Get the tenant's current provider preference. Returns null if no preference is set.",
)
async def get_provider_preference(
    tenant_id: str = Depends(get_current_tenant_id),
    service: ProviderConfigService = Depends(get_provider_config_service),
) -> TenantProviderPreference | None:
    """Get tenant's provider preference."""
    return await service.get_provider_preference(tenant_id)


@router.delete(
    "/preference",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete provider preference",
    description="Delete the tenant's provider preference. The tenant will revert to using the default provider.",
)
async def delete_provider_preference(
    tenant_id: str = Depends(get_current_tenant_id),
    service: ProviderConfigService = Depends(get_provider_config_service),
) -> None:
    """Delete tenant's provider preference."""
    await service.delete_provider_preference(tenant_id)


@router.post(
    "/custom-keys",
    response_model=TenantCustomApiKey,
    status_code=status.HTTP_201_CREATED,
    summary="Add custom API key",
    description="Add a custom API key for a specific provider. Keys are encrypted at rest.",
)
async def add_custom_key(
    request: CustomApiKeyRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    service: ProviderConfigService = Depends(get_provider_config_service),
) -> TenantCustomApiKey:
    """Add a custom API key for the tenant."""
    return await service.add_custom_key(tenant_id, request)


@router.get(
    "/custom-keys",
    response_model=list[TenantCustomApiKey],
    summary="List custom API keys",
    description="List all custom API keys for the tenant. Optionally filter by provider.",
)
async def list_custom_keys(
    provider: ProviderType | None = None,
    tenant_id: str = Depends(get_current_tenant_id),
    service: ProviderConfigService = Depends(get_provider_config_service),
) -> list[TenantCustomApiKey]:
    """List tenant's custom API keys."""
    return await service.get_custom_keys(tenant_id, provider)


@router.delete(
    "/custom-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete custom API key",
    description="Delete a custom API key by ID.",
)
async def delete_custom_key(
    key_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    service: ProviderConfigService = Depends(get_provider_config_service),
) -> None:
    """Delete a custom API key."""
    success = await service.delete_custom_key(tenant_id, key_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Custom key not found: {key_id}",
        )


@router.get(
    "/active",
    summary="Get active provider configuration",
    description="Get the currently active provider, model, and whether a custom key is being used for the tenant.",
)
async def get_active_provider(
    tenant_id: str = Depends(get_current_tenant_id),
    service: ProviderConfigService = Depends(get_provider_config_service),
) -> dict[str, Any]:
    """Get the active provider configuration for the tenant."""
    provider, model, custom_key_id = await service.get_provider_for_tenant(tenant_id)
    
    preference = await service.get_provider_preference(tenant_id)
    
    return {
        "provider": provider.value,
        "model": model,
        "using_custom_key": preference.use_custom_key if preference else False,
        "custom_key_id": preference.custom_key_id if preference else None,
        "is_custom": bool(preference) if preference else False,
    }
