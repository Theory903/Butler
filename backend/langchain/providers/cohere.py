"""Cohere Provider Integration."""

import logging
from typing import Any

from .base import BaseProvider, ProviderConfig, ProviderType

logger = logging.getLogger(__name__)


class CohereProvider(BaseProvider):
    """Cohere provider for chat, embeddings, and rerank."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._chat_client: Any = None
        self._embedding_client: Any = None

    async def initialize(self) -> None:
        try:
            from langchain_cohere import ChatCohere, CohereEmbeddings

            if self._config.provider_type in [ProviderType.LLM, ProviderType.CHAT]:
                self._chat_client = ChatCohere(
                    cohere_api_key=self._config.api_key,
                    model=self._config.model or "command-r-plus",
                    temperature=self._config.temperature,
                    **self._config.extra_params,
                )
                logger.info(f"cohere_chat_initialized: model={self._config.model}")

            if self._config.provider_type == ProviderType.EMBEDDING:
                self._embedding_client = CohereEmbeddings(
                    cohere_api_key=self._config.api_key,
                    model=self._config.model or "embed-english-v3.0",
                    **self._config.extra_params,
                )
                logger.info(f"cohere_embedding_initialized: model={self._config.model}")

            self._client = self._chat_client or self._embedding_client
        except ImportError:
            logger.warning("langchain_cohere_not_installed: pip install langchain-cohere")
        except Exception as e:
            logger.error(f"cohere_initialization_failed: {e}")

    async def call(self, **kwargs: Any) -> Any:
        if not self.is_initialized:
            raise RuntimeError("Cohere provider not initialized")
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
