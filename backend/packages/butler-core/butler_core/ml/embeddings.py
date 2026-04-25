"""Embedding provider protocol.

Core Butler code must depend only on this protocol.
Implementations may use ONNX, PyTorch, remote APIs, or disabled fallback.
"""

from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    """Provider interface for text embeddings.

    Implementations may use ONNX, PyTorch, remote APIs, or disabled fallback.
    Core Butler code must depend only on this protocol.
    """

    async def embed_one(self, text: str) -> list[float]:
        """Embed one text input."""
        ...

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple text inputs."""
        ...
