import asyncio
from domain.ml.contracts import EmbeddingContract

class EmbeddingService(EmbeddingContract):
    """Dense text embeddings for Memory retrieval.
    
    Oracle-Grade: Defaults to BAAI/bge-large-en-v1.5 (1024-d).
    Supports truncation and normalization for production-grade retrieval.
    """
    
    def __init__(self, model_name: str = "BAAI/bge-large-en-v1.5"):
        self._model_name = model_name
        self._model = None  # Lazy load
    
    async def embed(self, text: str) -> list[float]:
        """Generate embedding vector for text."""
        if not self._model:
            await self._load_model()
        
        # Run embedding in thread pool (CPU-bound)
        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(
            None, self._model.encode, text
        )
        return embedding.tolist()
    
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch embedding for efficiency."""
        if not self._model:
            await self._load_model()
        
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None, self._model.encode, texts
        )
        return [e.tolist() for e in embeddings]
    
    async def _load_model(self):
        """Lazy load model on first use."""
        from sentence_transformers import SentenceTransformer
        loop = asyncio.get_event_loop()
        self._model = await loop.run_in_executor(
            None, SentenceTransformer, self._model_name
        )
