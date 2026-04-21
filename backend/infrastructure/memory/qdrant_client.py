import logging
from typing import Optional
from qdrant_client import AsyncQdrantClient
from infrastructure.config import settings

logger = logging.getLogger(__name__)

class QdrantClient:
    """Butler's Qdrant Vector Search Client (Oracle-Grade)."""
    
    _instance: Optional["QdrantClient"] = None
    _client: Optional[AsyncQdrantClient] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(QdrantClient, cls).__new__(cls)
        return cls._instance

    async def connect(self):
        """Establish connection to the Qdrant cluster."""
        if self._client is None:
            try:
                self._client = AsyncQdrantClient(
                    host=settings.QDRANT_HOST,
                    port=settings.QDRANT_PORT,
                    api_key=settings.QDRANT_API_KEY
                )
                # Quick health check & Ensure collection exists with correct dimensions
                collections_res = await self._client.get_collections()
                collection_names = [c.name for c in collections_res.collections]
                
                recreate = False
                if "butler_memories" in collection_names:
                    # Check dimensions
                    c_info = await self._client.get_collection("butler_memories")
                    current_dim = c_info.config.params.vectors.size if hasattr(c_info.config.params.vectors, "size") else 0
                    if current_dim != 1536:
                        logger.warning(f"Qdrant collection dimension mismatch: {current_dim} vs 1536. Recreating...")
                        await self._client.delete_collection("butler_memories")
                        recreate = True
                else:
                    recreate = True

                if recreate:
                    from qdrant_client.http.models import Distance, VectorParams
                    await self._client.create_collection(
                        collection_name="butler_memories",
                        vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
                    )
                    logger.info("Initialized Qdrant collection: butler_memories (1536-d)")
                
                logger.info(f"Qdrant connection established at {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")
            except Exception as e:
                logger.error(f"Failed to connect to Qdrant: {e}")
                raise

    async def close(self):
        """Close the Qdrant client connection."""
        if self._client:
            # AsyncQdrantClient uses httpx internally, which handles its own closing usually,
            # but we can set to None to clear the instance.
            self._client = None
            logger.info("Qdrant client instance cleared.")

    @property
    def client(self) -> AsyncQdrantClient:
        if self._client is None:
            raise RuntimeError("QdrantClient is not connected. Call connect() first.")
        return self._client

# Global instance
qdrant_client = QdrantClient()
