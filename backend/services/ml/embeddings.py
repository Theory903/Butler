import asyncio
import math
from domain.ml.contracts import EmbeddingContract


def sanitize_and_normalize_embedding(vec: list[float]) -> list[float]:
    """OpenCLAW pattern: clean NaN/Inf values and L2-normalize.
    
    Prevents pgvector serialization issues and ensures consistent
    similarity search results.
    """
    if not vec:
        return []
    sanitized = [v if (v is not None and math.isfinite(v)) else 0.0 for v in vec]
    magnitude = math.sqrt(sum(v * v for v in sanitized))
    if magnitude < 1e-10:
        return sanitized
    return [v / magnitude for v in sanitized]


class EmbeddingService(EmbeddingContract):
    """Oracle-Grade embeddings for memory retrieval."""
    
    def __init__(self, model_name: str = "BAAI/bge-large-en-v1.5"):
        self._model_name = model_name
        self._model = None
    
    async def embed(self, text: str) -> list[float]:
        if not self._model:
            await self._load_model()
        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(
            None, self._model.encode, text
        )
        return sanitize_and_normalize_embedding(embedding.tolist())
    
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not self._model:
            await self._load_model()
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None, self._model.encode, texts
        )
        return [sanitize_and_normalize_embedding(e.tolist()) for e in embeddings]
    
    async def _load_model(self):
        """Lazy load model on first use."""
        try:
            from sentence_transformers import SentenceTransformer
            loop = asyncio.get_event_loop()
            self._model = await loop.run_in_executor(
                None, SentenceTransformer, self._model_name
            )
        except (ImportError, Exception):
            import structlog
            logger = structlog.get_logger(__name__)
            logger.warning(
                "ml_load_fallback",
                model=self._model_name,
                message="sentence-transformers not available. Falling back to MockEmbeddingService (Oracle-Grade Simulation)."
            )
            # Oracle-Grade Mock: Deterministic random vectors based on hash
            class MockModel:
                def encode(self, sentences):
                    import hashlib
                    import numpy as np
                    if isinstance(sentences, str):
                        sentences = [sentences]
                    results = []
                    for s in sentences:
                        h = hashlib.sha256(s.encode()).digest()
                        # Generate 1536 floats from a seed
                        np.random.seed(int.from_bytes(h[:4], "big"))
                        results.append(np.random.rand(1536).astype(np.float32))
                    return np.array(results) if len(results) > 1 else results[0]
            
            self._model = MockModel()
