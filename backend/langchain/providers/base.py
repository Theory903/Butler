"""Base Provider Framework for LangChain Integrations.

This module provides the LangChain Provider Integration Framework.
Base classes and registry for integrating LangChain providers
with Butler's ML runtime and tool system.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

from abc import ABC, abstractmethod


class ProviderType(Enum):
    """Types of LangChain providers."""

    LLM = "llm"
    CHAT = "chat"
    EMBEDDING = "embedding"
    VECTOR_STORE = "vector_store"
    TOOL = "tool"
    RETRIEVER = "retriever"
    DOCUMENT_LOADER = "document_loader"
    TEXT_SPLITTER = "text_splitter"


@dataclass
class ProviderConfig:
    """Configuration for a LangChain provider."""

    provider_name: str
    provider_type: ProviderType
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = None
    extra_params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "provider_name": self.provider_name,
            "provider_type": self.provider_type.value,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            **self.extra_params,
        }


class BaseProvider(ABC):
    """Base class for LangChain provider integrations."""

    def __init__(self, config: ProviderConfig):
        """Initialize provider with configuration.

        Args:
            config: Provider configuration
        """
        self._config = config
        self._client: Any = None

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the provider client."""

    @abstractmethod
    async def call(self, **kwargs: Any) -> Any:
        """Call the provider with parameters.

        Args:
            **kwargs: Provider-specific parameters

        Returns:
            Provider response
        """

    @property
    def config(self) -> ProviderConfig:
        """Get provider configuration."""
        return self._config

    @property
    def is_initialized(self) -> bool:
        """Check if provider is initialized."""
        return self._client is not None

    async def health_check(self) -> bool:
        """Check if provider is healthy.

        Returns:
            True if healthy, False otherwise
        """
        try:
            # Basic health check - try a simple call
            await self.call(test=True)
            return True
        except Exception:
            return False


class ProviderRegistry:
    """Registry for managing LangChain providers."""

    def __init__(self) -> None:
        """Initialize provider registry."""
        self._providers: dict[str, BaseProvider] = {}
        self._configs: dict[str, ProviderConfig] = {}

    def register(self, provider: BaseProvider) -> None:
        """Register a provider.

        Args:
            provider: Provider instance to register
        """
        provider_id = f"{provider.config.provider_name}_{provider.config.provider_type.value}"
        self._providers[provider_id] = provider
        self._configs[provider_id] = provider.config

    def get(self, provider_name: str, provider_type: ProviderType) -> BaseProvider | None:
        """Get a registered provider.

        Args:
            provider_name: Name of the provider
            provider_type: Type of the provider

        Returns:
            Provider instance or None if not found
        """
        provider_id = f"{provider_name}_{provider_type.value}"
        return self._providers.get(provider_id)

    def list_providers(self) -> list[str]:
        """List all registered provider IDs.

        Returns:
            List of provider IDs
        """
        return list(self._providers.keys())

    def unregister(self, provider_id: str) -> None:
        """Unregister a provider."""
        if provider_id in self._providers:
            del self._providers[provider_id]
            logger.info("provider_unregistered", extra={"provider_id": provider_id})

    async def initialize_all(self) -> None:
        """Initialize all registered providers."""
        for provider in self._providers.values():
            if not provider.is_initialized:
                await provider.initialize()

    async def shutdown_all(self) -> None:
        """Shutdown all registered providers."""
        for provider_id, provider in self._providers.items():
            try:
                if hasattr(provider, "shutdown"):
                    await provider.shutdown()
                logger.info("provider_shutdown_complete", extra={"provider_id": provider_id})
            except Exception as e:
                logger.error(
                    "provider_shutdown_failed", extra={"provider_id": provider_id, "error": str(e)}
                )

    async def health_check_all(self) -> dict[str, bool]:
        """Health check all registered providers.

        Returns:
            Dictionary mapping provider IDs to health status
        """
        results = {}
        for provider_id, provider in self._providers.items():
            results[provider_id] = await provider.health_check()
        return results
