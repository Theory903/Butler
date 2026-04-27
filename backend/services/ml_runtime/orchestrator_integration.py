"""Integration layer for ProviderOrchestrator into Butler ML runtime service."""

from __future__ import annotations

import os
from typing import Any, AsyncIterator

from .provider_orchestrator import (
    ProviderOrchestrator,
    MLRequest,
    MLResponse,
    create_provider_orchestrator,
    LangChainAdapterConfig,
)
from .openclaw_layer.config import load_config_from_env
from .openclaw_layer.provider_registry import (
    ProviderRegistry,
    create_default_registry,
)
from .openclaw_layer.credential_pool import (
    CredentialPool,
    create_credential,
)


def create_orchestrator_from_env() -> ProviderOrchestrator:
    """Create a ProviderOrchestrator configured from environment variables.
    
    This function reads provider credentials from environment variables and
    configures the orchestrator with the appropriate settings.
    """
    config = load_config_from_env()
    
    # Create provider registry
    registry = create_default_registry()
    
    # Create credential pool and add credentials from environment
    pool = CredentialPool()
    
    # Add OpenAI credentials
    for i in range(1, 10):  # Support up to 9 keys per provider
        key = os.environ.get(f"OPENAI_API_KEY_{i}")
        if key:
            credential = create_credential("openai", key)
            pool.add_credential(credential)
    
    # Add Anthropic credentials
    for i in range(1, 10):
        key = os.environ.get(f"ANTHROPIC_API_KEY_{i}")
        if key:
            credential = create_credential("anthropic", key)
            pool.add_credential(credential)
    
    # Add Groq credentials
    for i in range(1, 10):
        key = os.environ.get(f"GROQ_API_KEY_{i}")
        if key:
            credential = create_credential("groq", key)
            pool.add_credential(credential)
    
    # Add OpenRouter credential (single key)
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    if openrouter_key:
        credential = create_credential("openrouter", openrouter_key)
        pool.add_credential(credential)
    
    # Create LangChain adapter config from environment
    langchain_config = LangChainAdapterConfig(
        temperature=float(os.environ.get("LLM_TEMPERATURE", 0.7)),
        max_tokens=int(os.environ.get("LLM_MAX_TOKENS", 4096)),
        timeout=int(os.environ.get("LLM_TIMEOUT", 120)),
    )
    
    # Create orchestrator
    return create_provider_orchestrator(
        config=config,
        langchain_config=langchain_config,
    )


class OrchestratorBridge:
    """Bridge between Butler's ML runtime interface and ProviderOrchestrator.
    
    This class adapts the new ProviderOrchestrator to work with Butler's existing
    ML runtime contracts and interfaces.
    """
    
    def __init__(
        self,
        orchestrator: ProviderOrchestrator | None = None,
        default_provider: str | None = None,
    ):
        self.orchestrator = orchestrator or create_orchestrator_from_env()
        self.default_provider = default_provider or os.environ.get(
            "DEFAULT_LLM_PROVIDER",
            "openai"
        )
    
    async def generate(
        self,
        prompt: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        system_message: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MLResponse:
        """Generate a response using the ProviderOrchestrator.
        
        Args:
            prompt: The user prompt
            provider: Provider to use (defaults to DEFAULT_LLM_PROVIDER)
            model: Model to use (defaults to provider's default model)
            system_message: Optional system message
            tools: Optional tool definitions
            metadata: Optional metadata dictionary
            
        Returns:
            MLResponse with the generated content and metadata
        """
        request = MLRequest(
            provider=provider or self.default_provider,
            prompt=prompt,
            model=model,
            system_message=system_message,
            tools=tools,
            metadata=metadata or {},
        )
        
        return await self.orchestrator.execute_request(request)
    
    async def generate_stream(
        self,
        prompt: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        system_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response using the ProviderOrchestrator.
        
        Args:
            prompt: The user prompt
            provider: Provider to use (defaults to DEFAULT_LLM_PROVIDER)
            model: Model to use (defaults to provider's default model)
            system_message: Optional system message
            metadata: Optional metadata dictionary
            
        Yields:
            Text chunks as they are generated
        """
        request = MLRequest(
            provider=provider or self.default_provider,
            prompt=prompt,
            model=model,
            system_message=system_message,
            metadata=metadata or {},
        )
        
        async for chunk in self.orchestrator.execute_stream(request):
            yield chunk
    
    def get_provider_health(self, provider: str | None = None) -> dict[str, Any]:
        """Get health status for a provider or all providers."""
        if provider:
            return self.orchestrator.get_provider_health(provider)
        return self.orchestrator.get_all_provider_health()
    
    def get_cost_summary(self, provider: str | None = None) -> dict[str, Any]:
        """Get cost summary for a provider or all providers."""
        return self.orchestrator.get_cost_summary(provider)
    
    def get_metrics(self, provider: str | None = None) -> dict[str, Any]:
        """Get metrics for a provider or all providers."""
        return self.orchestrator.get_metrics(provider)
    
    def add_credential(
        self,
        provider: str,
        key: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a credential to the orchestrator's credential pool."""
        self.orchestrator.add_credential(provider, key, metadata)


def is_orchestration_enabled() -> bool:
    """Check if provider orchestration is enabled via environment variable."""
    return os.environ.get("PROVIDER_ORCHESTRATION_ENABLED", "false").lower() == "true"


def create_orchestrator_bridge_if_enabled(
    default_provider: str | None = None,
) -> OrchestratorBridge | None:
    """Create an OrchestratorBridge if orchestration is enabled.
    
    Args:
        default_provider: Default provider to use (defaults to env var)
        
    Returns:
        OrchestratorBridge instance if enabled, None otherwise
    """
    if is_orchestration_enabled():
        return OrchestratorBridge(default_provider=default_provider)
    return None
