"""Router factory for embedding providers.

Environment-driven backend selection.
"""

from __future__ import annotations

import os

from butler_core.ml.semantic_router import SemanticEmbeddingRouter
from butler_ml_runtime.providers.disabled import DisabledEmbeddingProvider
from butler_ml_runtime.providers.remote import RemoteEmbeddingProvider
from butler_ml_runtime.providers.sentence_transformers_cpu import (
    SentenceTransformerCpuEmbeddingProvider,
)
from butler_ml_runtime.providers.sentence_transformers_onnx import (
    SentenceTransformerOnnxEmbeddingProvider,
)


def build_embedding_router() -> SemanticEmbeddingRouter:
    """Build embedding router based on environment configuration."""
    backend = os.getenv("BUTLER_EMBEDDING_BACKEND", "disabled").strip().lower()

    if backend == "disabled":
        provider = DisabledEmbeddingProvider()
    elif backend == "sentence-transformers-cpu":
        provider = SentenceTransformerCpuEmbeddingProvider(
            model_name=os.getenv(
                "BUTLER_EMBEDDING_MODEL",
                "intfloat/multilingual-e5-small",
            ),
            model_family=os.getenv("BUTLER_EMBEDDING_MODEL_FAMILY", "e5"),
            max_workers=int(os.getenv("BUTLER_EMBEDDING_WORKERS", "1")),
        )
    elif backend == "sentence-transformers-onnx":
        provider = SentenceTransformerOnnxEmbeddingProvider(
            model_name=os.getenv(
                "BUTLER_EMBEDDING_MODEL",
                "intfloat/multilingual-e5-small",
            ),
            model_family=os.getenv("BUTLER_EMBEDDING_MODEL_FAMILY", "e5"),
            max_workers=int(os.getenv("BUTLER_EMBEDDING_WORKERS", "1")),
        )
    elif backend == "remote":
        provider = RemoteEmbeddingProvider(
            api_url=os.getenv("BUTLER_EMBEDDING_REMOTE_URL", ""),
            api_key=os.getenv("BUTLER_EMBEDDING_REMOTE_API_KEY"),
            model=os.getenv("BUTLER_EMBEDDING_REMOTE_MODEL", "text-embedding-3-small"),
        )
    else:
        raise ValueError(f"Unsupported embedding backend: {backend}")

    return SemanticEmbeddingRouter(embedding_provider=provider)
