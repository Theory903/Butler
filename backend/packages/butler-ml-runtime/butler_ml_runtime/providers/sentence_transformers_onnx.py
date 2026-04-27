"""ONNX SentenceTransformer embedding provider.

This provider uses ONNX runtime for lightweight inference.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import structlog

logger = structlog.get_logger(__name__)


class SentenceTransformerOnnxEmbeddingProvider:
    """ONNX SentenceTransformer embedding provider.

    This provider uses ONNX runtime for lightweight inference.
    """

    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-small",
        max_workers: int = 1,
        model_family: str = "e5",
        normalize_embeddings: bool = True,
    ) -> None:
        self._model_name = model_name
        self._model_family = model_family
        self._normalize_embeddings = normalize_embeddings
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._model = None
        self._load_lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._load_lock:
            if self._model is not None:
                return

            loop = asyncio.get_running_loop()

            def load_model():
                from sentence_transformers import SentenceTransformer

                return SentenceTransformer(self._model_name)

            logger.info("loading_sentence_transformer_onnx", model=self._model_name)
            self._model = await loop.run_in_executor(self._executor, load_model)
            logger.info("loaded_sentence_transformer_onnx", model=self._model_name)

    async def embed_one(self, text: str) -> list[float]:
        vectors = await self.embed_many([text])
        return vectors[0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        await self.initialize()

        if self._model is None:
            raise RuntimeError("SentenceTransformer model was not initialized.")

        prepared_texts = [self._prepare_query_text(text) for text in texts]
        loop = asyncio.get_running_loop()

        def encode():
            vectors = self._model.encode(
                prepared_texts,
                normalize_embeddings=self._normalize_embeddings,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            return vectors.tolist()

        return await loop.run_in_executor(self._executor, encode)

    def _prepare_query_text(self, text: str) -> str:
        stripped = text.strip()
        if self._model_family == "e5":
            return f"query: {stripped}"
        return stripped

    async def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
