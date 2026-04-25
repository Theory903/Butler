"""vLLM Provider Integration (high-throughput self-hosted inference)."""

import logging
from typing import Any

from .base import BaseProvider, ProviderConfig, ProviderType

logger = logging.getLogger(__name__)


class VLLMProvider(BaseProvider):
    """vLLM provider — uses OpenAI-compatible vLLM server."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._chat_client: Any = None

    async def initialize(self) -> None:
        try:
            from langchain_openai import ChatOpenAI

            base_url = self._config.base_url or "http://localhost:8000/v1"

            if self._config.provider_type in [ProviderType.LLM, ProviderType.CHAT]:
                self._chat_client = ChatOpenAI(
                    api_key=self._config.api_key or "EMPTY",
                    base_url=base_url,
                    model=self._config.model or "meta-llama/Meta-Llama-3.1-70B-Instruct",
                    temperature=self._config.temperature,
                    max_tokens=self._config.max_tokens,
                    **self._config.extra_params,
                )
                logger.info(f"vllm_chat_initialized: model={self._config.model}, url={base_url}")

            self._client = self._chat_client
        except ImportError:
            logger.warning("langchain_openai_not_installed: pip install langchain-openai")
        except Exception as e:
            logger.error(f"vllm_initialization_failed: {e}")

    async def call(self, **kwargs: Any) -> Any:
        if not self.is_initialized:
            raise RuntimeError("vLLM provider not initialized")
        if kwargs.pop("test", False):
            return await self._chat_client.ainvoke("Hello")
        return await self._chat_client.ainvoke(kwargs.get("messages", []))

    @property
    def is_initialized(self) -> bool:
        return self._chat_client is not None
