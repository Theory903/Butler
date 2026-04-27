"""Ollama Provider Integration (local models)."""

import logging
from typing import Any

from .base import BaseProvider, ProviderConfig, ProviderType

import structlog

logger = structlog.get_logger(__name__)


class OllamaProvider(BaseProvider):
    """Ollama provider for local LLM inference."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._chat_client: Any = None
        self._embedding_client: Any = None

    async def initialize(self) -> None:
        try:
            from langchain_ollama import ChatOllama, OllamaEmbeddings

            base_url = self._config.base_url or "http://localhost:11434"

            if self._config.provider_type in [ProviderType.LLM, ProviderType.CHAT]:
                self._chat_client = ChatOllama(
                    base_url=base_url,
                    model=self._config.model or "llama3.1",
                    temperature=self._config.temperature,
                    **self._config.extra_params,
                )
                logger.info(f"ollama_chat_initialized: model={self._config.model}, url={base_url}")

            if self._config.provider_type == ProviderType.EMBEDDING:
                self._embedding_client = OllamaEmbeddings(
                    base_url=base_url,
                    model=self._config.model or "nomic-embed-text",
                    **self._config.extra_params,
                )
                logger.info(f"ollama_embedding_initialized: model={self._config.model}")

            self._client = self._chat_client or self._embedding_client
        except ImportError:
            logger.warning("langchain_ollama_not_installed: pip install langchain-ollama")
        except Exception as e:
            logger.error(f"ollama_initialization_failed: {e}")

    async def call(self, **kwargs: Any) -> Any:
        if not self.is_initialized:
            raise RuntimeError("Ollama provider not initialized")
        if kwargs.pop("test", False):
            return await (self._chat_client or self._embedding_client).ainvoke("Hello")
        if self._chat_client:
            return await self._chat_client.ainvoke(kwargs.get("messages", []))
        if self._embedding_client:
            return await self._embedding_client.aembed_query(kwargs.get("text", ""))
        raise ValueError("No client available")

    @property
    def is_initialized(self) -> bool:
        return self._client is not None
