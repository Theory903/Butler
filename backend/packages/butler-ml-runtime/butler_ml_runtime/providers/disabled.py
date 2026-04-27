"""Disabled embedding provider.

Used when local embeddings are disabled.
"""

from __future__ import annotations


class DisabledEmbeddingProvider:
    """Embedding provider used when local embeddings are disabled."""

    async def embed_one(self, text: str) -> list[float]:
        raise RuntimeError("Local embeddings are disabled.")

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("Local embeddings are disabled.")
