"""Google (Gemini / Vertex AI) Provider Integration."""

import logging
from typing import Any

from .base import BaseProvider, ProviderConfig, ProviderType

import structlog

logger = structlog.get_logger(__name__)


class GoogleProvider(BaseProvider):
    """Google provider for Gemini chat models and embeddings."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._chat_client: Any = None
        self._embedding_client: Any = None

    async def initialize(self) -> None:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

            if self._config.provider_type in [ProviderType.LLM, ProviderType.CHAT]:
                self._chat_client = ChatGoogleGenerativeAI(
                    google_api_key=self._config.api_key,
                    model=self._config.model or "gemini-1.5-pro",
                    temperature=self._config.temperature,
                    max_output_tokens=self._config.max_tokens,
                    **self._config.extra_params,
                )
                logger.info(f"google_chat_initialized: model={self._config.model}")

            if self._config.provider_type == ProviderType.EMBEDDING:
                self._embedding_client = GoogleGenerativeAIEmbeddings(
                    google_api_key=self._config.api_key,
                    model=self._config.model or "models/embedding-001",
                    **self._config.extra_params,
                )
                logger.info(f"google_embedding_initialized: model={self._config.model}")

            self._client = self._chat_client or self._embedding_client
        except ImportError:
            logger.warning(
                "langchain_google_genai_not_installed: pip install langchain-google-genai"
            )
        except Exception as e:
            logger.error(f"google_initialization_failed: {e}")

    async def call(self, **kwargs: Any) -> Any:
        if not self.is_initialized:
            raise RuntimeError("Google provider not initialized")
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
