"""Embedding Providers — Voyage, Cohere, HuggingFace."""

from __future__ import annotations

import os
from typing import List, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=5.0)


class EmbeddingResult:
    """Result of text embedding."""
    
    def __init__(self, embedding: List[float], model: str):
        self.embedding = embedding
        self.model = model


# ── Voyage AI Embedding Provider ───────────────────────────────────────────

class VoyageEmbeddingProvider:
    """Voyage AI Embedding Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.voyageai.com/v1",
        model: str = "voyage-3",
    ) -> None:
        self._api_key = api_key or os.environ.get("VOYAGE_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def embed(self, text: str) -> EmbeddingResult:
        """Generate embedding for a single text."""
        url = f"{self._base_url}/embeddings"
        
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self._model,
            "input": text,
        }
        
        response = await self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        embedding = data["data"][0]["embedding"]
        
        return EmbeddingResult(embedding=embedding, model=self._model)

    async def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        """Generate embeddings for multiple texts."""
        url = f"{self._base_url}/embeddings"
        
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self._model,
            "input": texts,
        }
        
        response = await self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data["data"]:
            results.append(EmbeddingResult(
                embedding=item["embedding"],
                model=self._model
            ))
        
        return results


# ── Cohere Embedding Provider ─────────────────────────────────────────────

class CohereEmbeddingProvider:
    """Cohere Embedding Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.cohere.ai/v2",
        model: str = "embed-english-v3.0",
    ) -> None:
        self._api_key = api_key or os.environ.get("COHERE_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def embed(self, text: str) -> EmbeddingResult:
        """Generate embedding for a single text."""
        url = f"{self._base_url}/embed"
        
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Cohere-Version": "2024-09-04",
        }
        
        payload = {
            "model": self._model,
            "input_type": "search_document",
            "texts": [text],
        }
        
        response = await self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        embedding = data["embeddings"][0]
        
        return EmbeddingResult(embedding=embedding, model=self._model)

    async def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        """Generate embeddings for multiple texts."""
        url = f"{self._base_url}/embed"
        
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Cohere-Version": "2024-09-04",
        }
        
        payload = {
            "model": self._model,
            "input_type": "search_document",
            "texts": texts,
        }
        
        response = await self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for embedding in data["embeddings"]:
            results.append(EmbeddingResult(
                embedding=embedding,
                model=self._model
            ))
        
        return results


# ── HuggingFace Embedding Provider ─────────────────────────────────────────

class HuggingFaceEmbeddingProvider:
    """HuggingFace Inference API Embedding Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "sentence-transformers/all-MiniLM-L6-v2",
    ) -> None:
        self._api_key = api_key or os.environ.get("HF_API_KEY")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def embed(self, text: str) -> EmbeddingResult:
        """Generate embedding for a single text."""
        url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{self._model}"
        
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "inputs": text,
            "options": {"wait_for_model": True},
        }
        
        response = await self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        return EmbeddingResult(embedding=data, model=self._model)

    async def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        """Generate embeddings for multiple texts."""
        url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{self._model}"
        
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        
        results = []
        
        for text in texts:
            payload = {
                "inputs": text,
                "options": {"wait_for_model": True},
            }
            
            response = await self._client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            results.append(EmbeddingResult(embedding=data, model=self._model))
        
        return results


# ── Embedding Provider Factory ───────────────────────────────────────────────

class EmbeddingProviderFactory:
    """Factory for embedding providers."""
    
    _instances = {}
    
    @classmethod
    def get_provider(cls, provider_type: str):
        """Return a singleton instance of the requested embedding provider."""
        if provider_type in cls._instances:
            return cls._instances[provider_type]
        
        provider = None
        if provider_type == "voyage":
            from services.ml.providers.embeddings import VoyageEmbeddingProvider
            provider = VoyageEmbeddingProvider()
        elif provider_type == "cohere":
            from services.ml.providers.embeddings import CohereEmbeddingProvider
            provider = CohereEmbeddingProvider()
        elif provider_type == "huggingface":
            from services.ml.providers.embeddings import HuggingFaceEmbeddingProvider
            provider = HuggingFaceEmbeddingProvider()
        else:
            raise ValueError(f"Unsupported embedding provider: {provider_type}")
        
        cls._instances[provider_type] = provider
        return provider