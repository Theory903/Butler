"""Anthropic Provider Integration.

This module provides integration with Anthropic's LangChain providers
including ChatAnthropic and Anthropic embeddings.
"""

import logging
from typing import Any

from .base import BaseProvider, ProviderConfig, ProviderType

import structlog

logger = structlog.get_logger(__name__)


class AnthropicProvider(BaseProvider):
    """Anthropic provider for LangChain integration.

    Supports:
    - Chat models (claude-3-opus, claude-3-sonnet, claude-3-haiku)
    - Embeddings (via Anthropic API)
    """

    def __init__(self, config: ProviderConfig):
        """Initialize Anthropic provider.

        Args:
            config: Provider configuration
        """
        super().__init__(config)
        self._chat_client: Any = None
        self._embedding_client: Any = None

    async def initialize(self) -> None:
        """Initialize Anthropic clients."""
        try:
            from langchain_anthropic import ChatAnthropic

            # Initialize chat client
            if self._config.provider_type in [ProviderType.LLM, ProviderType.CHAT]:
                self._chat_client = ChatAnthropic(
                    api_key=self._config.api_key,
                    base_url=self._config.base_url,
                    model=self._config.model or "claude-3-sonnet-20240229",
                    temperature=self._config.temperature,
                    max_tokens=self._config.max_tokens,
                    **self._config.extra_params,
                )
                logger.info(f"anthropic_chat_initialized: model={self._config.model}")

            self._client = self._chat_client

        except ImportError:
            logger.warning(
                "langchain_anthropic_not_installed: Install with: pip install langchain-anthropic"
            )
        except Exception as e:
            logger.error(f"anthropic_initialization_failed: {e}")

    async def call(self, **kwargs: Any) -> Any:
        """Call Anthropic provider.

        Args:
            **kwargs: Provider-specific parameters

        Returns:
            Provider response
        """
        if not self.is_initialized:
            raise RuntimeError("Anthropic provider not initialized")

        test = kwargs.pop("test", False)

        if test:
            # Simple health check
            return await self._chat_client.ainvoke("Hello")

        messages = kwargs.get("messages", [])
        return await self._chat_client.ainvoke(messages)

    @property
    def is_initialized(self) -> bool:
        """Check if provider is initialized."""
        return self._chat_client is not None

    async def get_chat_model(self) -> Any:
        """Get the chat model client.

        Returns:
            ChatAnthropic instance
        """
        if not self._chat_client:
            await self.initialize()
        return self._chat_client
