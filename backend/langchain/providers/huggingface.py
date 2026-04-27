"""HuggingFace Provider Integration.

This module provides integration with HuggingFace's LangChain providers
including HuggingFaceHub, HuggingFaceEmbeddings, and HuggingFace tools.
"""

import logging
from typing import Any

from .base import BaseProvider, ProviderConfig, ProviderType

import structlog

logger = structlog.get_logger(__name__)


class HuggingFaceProvider(BaseProvider):
    """HuggingFace provider for LangChain integration.

    Supports:
    - LLMs via HuggingFaceHub
    - Embeddings via HuggingFaceEmbeddings
    - Local models via HuggingFacePipeline
    """

    def __init__(self, config: ProviderConfig):
        """Initialize HuggingFace provider.

        Args:
            config: Provider configuration
        """
        super().__init__(config)
        self._llm_client: Any = None
        self._embedding_client: Any = None
        self._pipeline_client: Any = None

    async def initialize(self) -> None:
        """Initialize HuggingFace clients."""
        try:
            from langchain_community.llms import HuggingFaceHub
            from langchain_community.llms.huggingface_pipeline import HuggingFacePipeline
            from langchain_huggingface import HuggingFaceEmbeddings

            # Initialize LLM via HuggingFaceHub
            if self._config.provider_type == ProviderType.LLM:
                self._llm_client = HuggingFaceHub(
                    repo_id=self._config.model or "google/flan-t5-large",
                    huggingfacehub_api_token=self._config.api_key,
                    **self._config.extra_params,
                )
                logger.info(f"huggingface_llm_initialized: model={self._config.model}")

            # Initialize embedding client
            if self._config.provider_type == ProviderType.EMBEDDING:
                self._embedding_client = HuggingFaceEmbeddings(
                    model_name=self._config.model or "sentence-transformers/all-MiniLM-L6-v2",
                    **self._config.extra_params,
                )
                logger.info(f"huggingface_embedding_initialized: model={self._config.model}")

            # Initialize local pipeline
            if self._config.provider_type == ProviderType.CHAT and self._config.extra_params.get(
                "local"
            ):
                self._pipeline_client = HuggingFacePipeline.from_model_id(
                    model_id=self._config.model or "gpt2",
                    **self._config.extra_params,
                )
                logger.info(f"huggingface_pipeline_initialized: model={self._config.model}")

            self._client = self._llm_client or self._embedding_client or self._pipeline_client

        except ImportError:
            logger.warning(
                "langchain_huggingface_not_installed: Install with: pip install langchain-huggingface"
            )
        except Exception as e:
            logger.error(f"huggingface_initialization_failed: {e}")

    async def call(self, **kwargs: Any) -> Any:
        """Call HuggingFace provider.

        Args:
            **kwargs: Provider-specific parameters

        Returns:
            Provider response
        """
        if not self.is_initialized:
            raise RuntimeError("HuggingFace provider not initialized")

        test = kwargs.pop("test", False)

        if test:
            # Simple health check
            if self._llm_client:
                return self._llm_client.invoke("test")
            if self._embedding_client:
                return await self._embedding_client.aembed_query("test")
            if self._pipeline_client:
                return self._pipeline_client.invoke("test")

        if self._llm_client:
            prompt = kwargs.get("prompt", "")
            return self._llm_client.invoke(prompt)

        if self._embedding_client:
            text = kwargs.get("text", "")
            return await self._embedding_client.aembed_query(text)

        if self._pipeline_client:
            prompt = kwargs.get("prompt", "")
            return self._pipeline_client.invoke(prompt)

        raise ValueError("No client available for this provider type")

    @property
    def is_initialized(self) -> bool:
        """Check if provider is initialized."""
        return self._client is not None

    async def get_llm(self) -> Any:
        """Get the LLM client.

        Returns:
            HuggingFaceHub instance
        """
        if not self._llm_client:
            await self.initialize()
        return self._llm_client

    async def get_embedding_model(self) -> Any:
        """Get the embedding model client.

        Returns:
            HuggingFaceEmbeddings instance
        """
        if not self._embedding_client:
            await self.initialize()
        return self._embedding_client
