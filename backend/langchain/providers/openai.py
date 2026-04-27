"""OpenAI Provider Integration.

This module provides integration with OpenAI's LangChain providers
including ChatOpenAI, OpenAIEmbeddings, and OpenAI tools.
"""

import logging
from typing import Any

from .base import BaseProvider, ProviderConfig, ProviderType

import structlog

logger = structlog.get_logger(__name__)


class OpenAIProvider(BaseProvider):
    """OpenAI provider for LangChain integration.

    Supports:
    - Chat models (gpt-4, gpt-3.5-turbo, etc.)
    - Embeddings (text-embedding-3-small/large)
    - Tools (function calling, DALL-E, etc.)
    """

    def __init__(self, config: ProviderConfig):
        """Initialize OpenAI provider.

        Args:
            config: Provider configuration
        """
        super().__init__(config)
        self._chat_client: Any = None
        self._embedding_client: Any = None

    async def initialize(self) -> None:
        """Initialize OpenAI clients."""
        try:
            from langchain_community.tools.openai_dalle_image_generation import (
                OpenAIDALLEImageGenerationTool,
            )
            from langchain_community.utilities.dalle_image_generator import DallEAPIWrapper
            from langchain_openai import ChatOpenAI, OpenAIEmbeddings

            # Initialize chat client
            if self._config.provider_type in [ProviderType.LLM, ProviderType.CHAT]:
                self._chat_client = ChatOpenAI(
                    api_key=self._config.api_key,
                    base_url=self._config.base_url,
                    model=self._config.model or "gpt-4",
                    temperature=self._config.temperature,
                    max_tokens=self._config.max_tokens,
                    **self._config.extra_params,
                )
                logger.info(f"openai_chat_initialized: model={self._config.model}")

            # Initialize embedding client
            if self._config.provider_type == ProviderType.EMBEDDING:
                self._embedding_client = OpenAIEmbeddings(
                    api_key=self._config.api_key,
                    base_url=self._config.base_url,
                    model=self._config.model or "text-embedding-3-small",
                    **self._config.extra_params,
                )
                logger.info(f"openai_embedding_initialized: model={self._config.model}")

            # Initialize DALL-E tool
            if self._config.provider_type == ProviderType.TOOL:
                api_wrapper = DallEAPIWrapper(api_key=self._config.api_key)
                self._client = OpenAIDALLEImageGenerationTool(api_wrapper=api_wrapper)
                logger.info("openai_dalle_tool_initialized")

            self._client = self._chat_client or self._embedding_client or self._client

        except ImportError:
            logger.warning(
                "langchain_openai_not_installed: Install with: pip install langchain-openai"
            )
        except Exception as e:
            logger.error(f"openai_initialization_failed: {e}")

    async def call(self, **kwargs: Any) -> Any:
        """Call OpenAI provider.

        Args:
            **kwargs: Provider-specific parameters

        Returns:
            Provider response
        """
        if not self.is_initialized:
            raise RuntimeError("OpenAI provider not initialized")

        test = kwargs.pop("test", False)

        if test:
            # Simple health check
            if self._chat_client:
                return await self._chat_client.ainvoke("Hello")
            if self._embedding_client:
                return await self._embedding_client.aembed_query("test")
            if self._client:
                return "OK"

        if self._chat_client:
            messages = kwargs.get("messages", [])
            return await self._chat_client.ainvoke(messages)

        if self._embedding_client:
            text = kwargs.get("text", "")
            return await self._embedding_client.aembed_query(text)

        if self._client:
            # Tool call
            return await self._client.arun(kwargs.get("prompt", ""))

        raise ValueError("No client available for this provider type")

    @property
    def is_initialized(self) -> bool:
        """Check if provider is initialized."""
        return self._client is not None

    async def get_chat_model(self) -> Any:
        """Get the chat model client.

        Returns:
            ChatOpenAI instance
        """
        if not self._chat_client:
            await self.initialize()
        return self._chat_client

    async def get_embedding_model(self) -> Any:
        """Get the embedding model client.

        Returns:
            OpenAIEmbeddings instance
        """
        if not self._embedding_client:
            await self.initialize()
        return self._embedding_client
