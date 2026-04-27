"""Groq Provider Integration (ultra-fast LPU inference)."""

import logging
from typing import Any

from .base import BaseProvider, ProviderConfig, ProviderType

import structlog

logger = structlog.get_logger(__name__)


class GroqProvider(BaseProvider):
    """Groq provider using ChatGroq for ultra-fast inference."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._chat_client: Any = None

    async def initialize(self) -> None:
        try:
            from langchain_groq import ChatGroq

            if self._config.provider_type in [ProviderType.LLM, ProviderType.CHAT]:
                self._chat_client = ChatGroq(
                    api_key=self._config.api_key,
                    model=self._config.model or "llama-3.1-70b-versatile",
                    temperature=self._config.temperature,
                    max_tokens=self._config.max_tokens,
                    **self._config.extra_params,
                )
                logger.info(f"groq_chat_initialized: model={self._config.model}")

            self._client = self._chat_client
        except ImportError:
            logger.warning("langchain_groq_not_installed: pip install langchain-groq")
        except Exception as e:
            logger.error(f"groq_initialization_failed: {e}")

    async def call(self, **kwargs: Any) -> Any:
        if not self.is_initialized:
            raise RuntimeError("Groq provider not initialized")
        if kwargs.pop("test", False):
            return await self._chat_client.ainvoke("Hello")
        return await self._chat_client.ainvoke(kwargs.get("messages", []))

    @property
    def is_initialized(self) -> bool:
        return self._chat_client is not None
