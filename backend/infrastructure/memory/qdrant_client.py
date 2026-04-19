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
                # Quick health check
                await self._client.get_collections()
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
