from __future__ import annotations

import asyncio
import hashlib
import math
from collections.abc import Sequence
from typing import Any

import structlog

from domain.ml.contracts import EmbeddingContract

logger = structlog.get_logger(__name__)


def sanitize_and_normalize_embedding(vec: Sequence[float]) -> list[float]:
    """Clean NaN/Inf values and L2-normalize a vector.

    This keeps downstream vector-store serialization stable and ensures
    cosine-similarity-style retrieval behaves consistently even if an
    upstream backend returns pathological values.
    """
    if not vec:
        return []

    sanitized = [
        float(value) if (value is not None and math.isfinite(float(value))) else 0.0
        for value in vec
    ]
    magnitude = math.sqrt(sum(value * value for value in sanitized))
    if magnitude < 1e-10:
        return sanitized
    return [value / magnitude for value in sanitized]


class EmbeddingService(EmbeddingContract):
    """Production embedding service for Butler retrieval.

    Design goals:
    - lazy-load once, safely, under concurrency
    - avoid event-loop anti-patterns in Python 3.13+
    - support multilingual defaults
    - support retrieval prompt configuration for model families that need it
    - provide deterministic fallback vectors only as a last-resort rail
    """

    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-large",
        *,
        default_prompt_name: str | None = "retrieval",
        prompts: dict[str, str] | None = None,
        batch_size: int = 32,
        normalize_embeddings: bool = True,
        backend: str = "torch",
        device: str | None = None,
        trust_remote_code: bool = False,
        max_concurrent_encodes: int = 8,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than 0")
        if max_concurrent_encodes <= 0:
            raise ValueError("max_concurrent_encodes must be greater than 0")

        self._model_name = model_name
        self._default_prompt_name = default_prompt_name
        self._prompts = prompts or self._default_prompts_for_model(model_name)
        self._batch_size = batch_size
        self._normalize_embeddings = normalize_embeddings
        self._backend = backend
        self._device = device
        self._trust_remote_code = trust_remote_code

        self._model: Any | None = None
        self._load_lock = asyncio.Lock()
        self._encode_semaphore = asyncio.Semaphore(max_concurrent_encodes)

    async def embed(self, text: str) -> list[float]:
        """Embed a single text input."""
        normalized_text = (text or "").strip()
        if not normalized_text:
            return []

        await self._ensure_model()

        async with self._encode_semaphore:
            embedding = await asyncio.to_thread(
                self._encode_single,
                normalized_text,
            )

        return sanitize_and_normalize_embedding(embedding)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple text inputs."""
        cleaned_texts = [(text or "").strip() for text in texts]
        if not cleaned_texts:
            return []

        await self._ensure_model()

        async with self._encode_semaphore:
            embeddings = await asyncio.to_thread(
                self._encode_batch,
                cleaned_texts,
            )

        return [sanitize_and_normalize_embedding(item) for item in embeddings]

    async def _ensure_model(self) -> None:
        """Lazy-load the model once, safely, under concurrent access."""
        if self._model is not None:
            return

        async with self._load_lock:
            if self._model is not None:
                return
            self._model = await self._load_model()

    async def _load_model(self) -> Any:
        """Load the configured embedding model or fallback rail."""
        try:
            from sentence_transformers import SentenceTransformer

            model = await asyncio.to_thread(
                SentenceTransformer,
                self._model_name,
                device=self._device,
                backend=self._backend,
                prompts=self._prompts or None,
                default_prompt_name=self._default_prompt_name,
                trust_remote_code=self._trust_remote_code,
            )
            logger.info(
                "embedding_model_loaded",
                model=self._model_name,
                backend=self._backend,
                device=self._device,
                prompt_names=sorted((self._prompts or {}).keys()),
            )
            return model
        except Exception as exc:
            logger.warning(
                "embedding_model_load_fallback",
                model=self._model_name,
                error=str(exc),
                message=(
                    "sentence-transformers model unavailable. Falling back to "
                    "deterministic mock embeddings."
                ),
            )
            return _MockEmbeddingModel()

    def _encode_single(self, text: str) -> list[float]:
        """Synchronous single-item encode path executed in a worker thread."""
        if self._model is None:
            raise RuntimeError("Embedding model is not loaded")

        encoded = self._model.encode(
            text,
            batch_size=1,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=self._normalize_embeddings,
        )
        return self._to_python_vector(encoded)

    def _encode_batch(self, texts: list[str]) -> list[list[float]]:
        """Synchronous batch encode path executed in a worker thread."""
        if self._model is None:
            raise RuntimeError("Embedding model is not loaded")

        encoded = self._model.encode(
            texts,
            batch_size=self._batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=self._normalize_embeddings,
        )

        # sentence-transformers returns a 2D numpy array for batches
        return [self._to_python_vector(item) for item in encoded]

    def _to_python_vector(self, value: Any) -> list[float]:
        """Convert model output into a plain Python float vector."""
        result = value.tolist() if hasattr(value, "tolist") else list(value)

        return [float(item) for item in result]

    def _default_prompts_for_model(self, model_name: str) -> dict[str, str]:
        """Return sensible retrieval prompts for models that expect them.

        Keep this small and model-family-oriented, not a giant hardcoded zoo.
        """
        lowered = model_name.lower()

        # Sentence Transformers docs note e5 retrieval prefixes such as
        # `query: ` and `passage: ` for multilingual-e5-large.
        if "e5" in lowered:
            return {
                "retrieval": "query: ",
                "document": "passage: ",
            }

        # Sentence Transformers docs note bge retrieval prompting for
        # bge-large-en-v1.5. We keep a generic BGE retrieval prompt rail.
        if "bge" in lowered:
            return {
                "retrieval": "Represent this sentence for searching relevant passages: ",
                "document": "",
            }

        return {}


class _MockEmbeddingModel:
    """Deterministic fallback embedding model.

    This is a last-resort resilience rail, not a substitute for real embeddings.
    """

    def __init__(self, dimensions: int = 1536) -> None:
        self._dimensions = dimensions

    def encode(
        self,
        sentences: str | list[str],
        *,
        batch_size: int = 32,
        show_progress_bar: bool = False,
        convert_to_numpy: bool = True,
        normalize_embeddings: bool = True,
    ):
        del batch_size, show_progress_bar, convert_to_numpy, normalize_embeddings

        import numpy as np

        if isinstance(sentences, str):
            return np.array(self._vector_for_text(sentences), dtype=np.float32)

        return np.array(
            [self._vector_for_text(sentence) for sentence in sentences],
            dtype=np.float32,
        )

    def _vector_for_text(self, text: str) -> list[float]:
        import random

        digest = hashlib.sha256(text.encode("utf-8")).digest()
        seed = int.from_bytes(digest[:8], "big", signed=False)
        rng = random.Random(seed)
        return [rng.random() for _ in range(self._dimensions)]
