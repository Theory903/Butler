"""LangChain Provider Management API Routes.

Multi-tenant provider registration, configuration, and health checks.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.deps import get_langchain_provider_registry
from langchain.providers import (
    AnthropicProvider,
    CohereProvider,
    GoogleProvider,
    GroqProvider,
    HuggingFaceProvider,
    MistralProvider,
    OllamaProvider,
    OpenAIProvider,
    OpenRouterProvider,
    ProviderConfig,
    ProviderType,
    VLLMProvider,
)

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/integrations/providers", tags=["integrations"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ProviderRegistrationRequest(BaseModel):
    """Request to register a new LangChain provider."""

    provider_id: str = Field(..., description="Unique provider ID")
    provider_name: str = Field(..., description="Provider name (e.g., 'openai', 'anthropic')")
    provider_type: ProviderType = Field(..., description="Type of provider (LLM, CHAT, EMBEDDING)")
    api_key: str | None = Field(None, description="API key (if required)")
    base_url: str | None = Field(None, description="Base URL for self-hosted providers")
    model: str | None = Field(None, description="Model name/ID")
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(None, ge=1)
    extra_params: dict[str, Any] = Field(default_factory=dict)


class ProviderResponse(BaseModel):
    """Provider registration response."""

    provider_id: str
    provider_type: str
    model: str | None
    is_initialized: bool
    is_healthy: bool


class ProviderListResponse(BaseModel):
    """List of registered providers."""

    providers: list[ProviderResponse]


# ---------------------------------------------------------------------------
# Provider class mapping
# ---------------------------------------------------------------------------


_PROVIDER_CLASSES: dict[str, type] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "huggingface": HuggingFaceProvider,
    "google": GoogleProvider,
    "mistral": MistralProvider,
    "groq": GroqProvider,
    "cohere": CohereProvider,
    "ollama": OllamaProvider,
    "openrouter": OpenRouterProvider,
    "vllm": VLLMProvider,
}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_provider(
    request: ProviderRegistrationRequest,
    http_request: Request,
    registry: Any = Depends(get_langchain_provider_registry),
) -> ProviderResponse:
    """Register a new LangChain provider.

    Multi-tenant: provider_id is scoped to tenant_id from auth context.
    """
    tenant_id = getattr(http_request.state, "tenant_id", "default")
    scoped_id = f"{tenant_id}:{request.provider_id}"

    if registry.get(scoped_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Provider {request.provider_id} already registered for tenant {tenant_id}",
        )

    provider_class = _PROVIDER_CLASSES.get(request.provider_name)
    if provider_class is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider type: {request.provider_name}",
        )

    config = ProviderConfig(
        provider_name=request.provider_name,
        provider_type=request.provider_type,
        api_key=request.api_key,
        base_url=request.base_url,
        model=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        extra_params=request.extra_params,
    )

    provider = provider_class(config)
    await provider.initialize()

    registry.register(scoped_id, provider)

    logger.info(
        "provider_registered", extra={"tenant_id": tenant_id, "provider_id": request.provider_id}
    )

    return ProviderResponse(
        provider_id=request.provider_id,
        provider_type=request.provider_type.value,
        model=request.model,
        is_initialized=provider.is_initialized,
        is_healthy=await provider.health_check(),
    )


@router.get("", response_model=ProviderListResponse)
async def list_providers(
    http_request: Request,
    registry: Any = Depends(get_langchain_provider_registry),
) -> ProviderListResponse:
    """List all providers for the current tenant."""
    tenant_id = getattr(http_request.state, "tenant_id", "default")
    prefix = f"{tenant_id}:"

    all_providers = registry.list_providers()
    tenant_providers = [p for p in all_providers if p.startswith(prefix)]

    responses = []
    for scoped_id in tenant_providers:
        provider = registry.get(scoped_id)
        if provider:
            base_id = scoped_id.replace(prefix, "", 1)
            responses.append(
                ProviderResponse(
                    provider_id=base_id,
                    provider_type=provider._config.provider_type.value,
                    model=provider._config.model,
                    is_initialized=provider.is_initialized,
                    is_healthy=await provider.health_check(),
                )
            )

    return ProviderListResponse(providers=responses)


@router.delete("/{provider_id}")
async def delete_provider(
    provider_id: str,
    http_request: Request,
    registry: Any = Depends(get_langchain_provider_registry),
) -> dict[str, str]:
    """Delete a provider for the current tenant."""
    tenant_id = getattr(http_request.state, "tenant_id", "default")
    scoped_id = f"{tenant_id}:{provider_id}"

    provider = registry.get(scoped_id)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider {provider_id} not found for tenant {tenant_id}",
        )

    if hasattr(provider, "shutdown"):
        await provider.shutdown()

    registry.unregister(scoped_id)

    logger.info("provider_deleted", extra={"tenant_id": tenant_id, "provider_id": provider_id})

    return {"message": f"Provider {provider_id} deleted"}


@router.get("/{provider_id}/health")
async def provider_health(
    provider_id: str,
    http_request: Request,
    registry: Any = Depends(get_langchain_provider_registry),
) -> dict[str, bool]:
    """Health check for a specific provider."""
    tenant_id = getattr(http_request.state, "tenant_id", "default")
    scoped_id = f"{tenant_id}:{provider_id}"

    provider = registry.get(scoped_id)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider {provider_id} not found for tenant {tenant_id}",
        )

    return {"healthy": await provider.health_check()}
