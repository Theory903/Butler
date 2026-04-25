"""
Qdrant Vector Store - Production Vector Search

Implements high-performance vector search using Qdrant.
Supports tenant-scoped collections, hybrid search, and real-time updates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    HnswConfigDiff,
    MatchValue,
    PointIdsList,
    PointStruct,
    SearchParams,
    VectorParams,
)

from domain.ml.contracts import EmbeddingContract

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class VectorSearchResult:
    """Vector search result."""

    id: str
    score: float
    payload: dict[str, Any]
    memory_type: str
    created_at: datetime


class QdrantVectorStore:
    """
    Qdrant-based vector store for production memory search.

    Features:
    - Tenant-scoped collections for isolation
    - Hybrid search (vector + filter)
    - Real-time updates
    - HNSW indexing for fast search
    """

    def __init__(
        self,
        url: str = "http://localhost:6333",
        api_key: str | None = None,
        embedder: EmbeddingContract | None = None,
    ) -> None:
        """Initialize Qdrant vector store."""
        self._url = url
        self._api_key = api_key
        self._embedder = embedder
        self._client: AsyncQdrantClient | None = None

    async def _get_client(self) -> AsyncQdrantClient:
        """Get or create Qdrant client."""
        if self._client is None:
            self._client = AsyncQdrantClient(
                url=self._url,
                api_key=self._api_key,
            )
        return self._client

    def _collection_name(self, tenant_id: str) -> str:
        """Generate tenant-scoped collection name."""
        return f"tenant_{tenant_id.replace('-', '_')}"

    async def ensure_collection(
        self,
        tenant_id: str,
        vector_size: int = 1536,
    ) -> None:
        """
        Ensure collection exists for tenant.

        Args:
            tenant_id: Tenant UUID
            vector_size: Embedding dimension
        """
        client = await self._get_client()
        collection_name = self._collection_name(tenant_id)

        try:
            await client.get_collection(collection_name)
            logger.debug(
                "qdrant_collection_exists",
                collection=collection_name,
            )
        except Exception:
            # Collection doesn't exist, create it
            await client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE,
                    hnsw_config=HnswConfigDiff(
                        m=16,
                        ef_construct=64,
                    ),
                ),
            )
            logger.info(
                "qdrant_collection_created",
                collection=collection_name,
                vector_size=vector_size,
            )

    async def upsert(
        self,
        tenant_id: str,
        points: list[dict[str, Any]],
    ) -> None:
        """
        Upsert vectors to tenant collection.

        Args:
            tenant_id: Tenant UUID
            points: List of points with id, vector, and payload
        """
        client = await self._get_client()
        collection_name = self._collection_name(tenant_id)

        qdrant_points = [
            PointStruct(
                id=point["id"],
                vector=point["vector"],
                payload={
                    "memory_type": point.get("memory_type", "general"),
                    "content": point.get("content", ""),
                    "created_at": point.get("created_at", datetime.now(UTC).isoformat()),
                    "importance": point.get("importance", 0.5),
                    "metadata": point.get("metadata", {}),
                },
            )
            for point in points
        ]

        await client.upsert(
            collection_name=collection_name,
            points=qdrant_points,
        )

        logger.debug(
            "qdrant_upsert_completed",
            collection=collection_name,
            points_count=len(points),
        )

    async def search(
        self,
        tenant_id: str,
        query_vector: list[float],
        limit: int = 10,
        memory_type: str | None = None,
        min_score: float = 0.0,
        search_params: SearchParams | None = None,
    ) -> list[VectorSearchResult]:
        """
        Search vectors in tenant collection.

        Args:
            tenant_id: Tenant UUID
            query_vector: Query embedding
            limit: Number of results to return
            memory_type: Filter by memory type
            min_score: Minimum score threshold
            search_params: Search parameters (hnsw_ef, etc.)

        Returns:
            List of search results
        """
        client = await self._get_client()
        collection_name = self._collection_name(tenant_id)

        # Build filter - always include tenant_id for defense-in-depth
        filter_conditions = [
            FieldCondition(
                key="tenant_id",
                match=MatchValue(value=tenant_id),
            )
        ]
        if memory_type:
            filter_conditions.append(
                FieldCondition(
                    key="memory_type",
                    match=MatchValue(value=memory_type),
                )
            )

        query_filter = Filter(must=filter_conditions)

        if search_params is None:
            search_params = SearchParams(
                hnsw_ef=128,
                exact=False,
            )

        results = await client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=limit,
            query_filter=query_filter,
            score_threshold=min_score,
            with_payload=True,
            params=search_params,
        )

        return [
            VectorSearchResult(
                id=str(result.id),
                score=result.score,
                payload=result.payload or {},
                memory_type=result.payload.get("memory_type", "general")
                if result.payload
                else "general",
                created_at=datetime.fromisoformat(
                    result.payload.get("created_at", datetime.now(UTC).isoformat())
                )
                if result.payload
                else datetime.now(UTC),
            )
            for result in results.points
        ]

    async def delete(
        self,
        tenant_id: str,
        point_ids: list[str],
    ) -> None:
        """
        Delete points from tenant collection.

        Args:
            tenant_id: Tenant UUID
            point_ids: List of point IDs to delete
        """
        client = await self._get_client()
        collection_name = self._collection_name(tenant_id)

        await client.delete(
            collection_name=collection_name,
            points_selector=PointIdsList(points=point_ids),
        )

        logger.debug(
            "qdrant_delete_completed",
            collection=collection_name,
            points_count=len(point_ids),
        )

    async def delete_collection(self, tenant_id: str) -> None:
        """
        Delete entire tenant collection.

        Args:
            tenant_id: Tenant UUID
        """
        client = await self._get_client()
        collection_name = self._collection_name(tenant_id)

        try:
            await client.delete_collection(collection_name)
            logger.info(
                "qdrant_collection_deleted",
                collection=collection_name,
            )
        except Exception:
            logger.warning(
                "qdrant_collection_delete_failed",
                collection=collection_name,
            )

    async def get_collection_info(self, tenant_id: str) -> dict[str, Any]:
        """
        Get collection information.

        Args:
            tenant_id: Tenant UUID

        Returns:
            Collection info
        """
        client = await self._get_client()
        collection_name = self._collection_name(tenant_id)

        try:
            info = await client.get_collection(collection_name)
            vectors_config = info.config.params.vectors
            return {
                "name": collection_name,
                "vector_count": info.points_count,
                "vector_size": vectors_config.size if hasattr(vectors_config, "size") else 0,
                "distance": vectors_config.distance.value
                if hasattr(vectors_config, "distance")
                else "unknown",
            }
        except Exception:
            return {
                "name": collection_name,
                "vector_count": 0,
                "vector_size": 0,
                "distance": "unknown",
            }

    async def hybrid_search(
        self,
        tenant_id: str,
        query: str,
        query_vector: list[float] | None = None,
        limit: int = 10,
        memory_type: str | None = None,
        keyword_filter: str | None = None,
    ) -> list[VectorSearchResult]:
        """
        Hybrid search combining vector and keyword search.

        Args:
            tenant_id: Tenant UUID
            query: Query text
            query_vector: Query embedding (optional, will generate if not provided)
            limit: Number of results to return
            memory_type: Filter by memory type
            keyword_filter: Keyword to filter results

        Returns:
            List of search results
        """
        # Generate embedding if not provided
        if query_vector is None and self._embedder:
            query_vector = await self._embedder.embed(query)

        if not query_vector:
            return []

        client = await self._get_client()
        collection_name = self._collection_name(tenant_id)

        # Build filter
        filter_conditions = []
        if memory_type:
            filter_conditions.append(
                FieldCondition(
                    key="memory_type",
                    match=MatchValue(value=memory_type),
                )
            )

        if keyword_filter:
            filter_conditions.append(
                FieldCondition(
                    key="content",
                    match=MatchValue(value=keyword_filter),
                )
            )

        query_filter = Filter(must=filter_conditions) if filter_conditions else None

        results = await client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=limit,
            query_filter=query_filter,
            with_payload=True,
        )

        return [
            VectorSearchResult(
                id=str(result.id),
                score=result.score,
                payload=result.payload or {},
                memory_type=result.payload.get("memory_type", "general")
                if result.payload
                else "general",
                created_at=datetime.fromisoformat(
                    result.payload.get("created_at", datetime.now(UTC).isoformat())
                )
                if result.payload
                else datetime.now(UTC),
            )
            for result in results.points
        ]

    async def close(self) -> None:
        """Close Qdrant client."""
        if self._client:
            await self._client.close()
            self._client = None
