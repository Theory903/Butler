"""CrewAI Knowledge integration with Butler's RAG system.

This module provides integration between CrewAI's Knowledge/RAG capabilities
and Butler's retrieval system, enabling multi-source knowledge retrieval
while maintaining Butler's security and governance boundaries.
"""

from __future__ import annotations

import logging
from typing import Any

from .config import CrewAIConfig

logger = logging.getLogger(__name__)


class CrewAIKnowledgeAdapter:
    """Adapter for integrating CrewAI Knowledge with Butler's RAG system.

    This adapter maps CrewAI's multi-source RAG capabilities to Butler's
    retrieval system, enabling:
    - CrewAI's multi-source document ingestion (PDF, CSV, JSON, DOCX, etc.)
    - Butler's vector store integrations (Qdrant, Weaviate, MongoDB, etc.)
    - Butler's security guardrails on knowledge retrieval
    - Butler's governance for knowledge access control

    Integration Principles:
    - Use Butler's vector stores for knowledge storage
    - Use CrewAI's multi-source ingestion for document processing
    - Apply Butler's security guardrails to all knowledge retrieval
    - Maintain Butler's service boundaries and governance
    """

    def __init__(
        self,
        config: CrewAIConfig | None = None,
        content_guard: Any = None,
    ) -> None:
        """Initialize CrewAI Knowledge adapter.

        Args:
            config: CrewAI configuration.
            content_guard: Butler ContentGuard instance for safety checks.
        """
        self._config = config or CrewAIConfig()
        self._content_guard = content_guard
        self._vector_store = None  # Will be initialized with Butler's vector store

    def set_vector_store(self, vector_store: Any) -> None:
        """Set Butler's vector store for knowledge retrieval.

        Args:
            vector_store: Butler's vector store instance.
        """
        self._vector_store = vector_store
        logger.info("Set Butler vector store for CrewAI Knowledge integration")

    async def ingest_document(
        self,
        document_path: str,
        document_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Ingest a document into CrewAI Knowledge with Butler storage.

        Args:
            document_path: Path to the document.
            document_type: Type of document (pdf, csv, json, docx, etc.).
            metadata: Additional metadata for the document.

        Returns:
            Ingestion result with metadata.
        """
        try:
            from crewai import Knowledge

            # Create CrewAI Knowledge instance
            knowledge = Knowledge()

            # Ingest document
            result = knowledge.load(document_path)

            # Store embeddings in Butler's vector store if available
            if self._vector_store and hasattr(result, 'embeddings'):
                await self._store_embeddings_in_butler(
                    embeddings=result.embeddings,
                    metadata=metadata or {},
                )

            logger.info(f"Ingested document: {document_path} (type: {document_type})")

            return {
                "success": True,
                "document_path": document_path,
                "document_type": document_type,
                "chunks": len(result) if hasattr(result, '__len__') else 1,
                "metadata": metadata,
            }

        except ImportError:
            logger.warning("CrewAI not installed - Knowledge integration disabled")
            return {
                "success": False,
                "error": "CrewAI not installed",
            }
        except Exception as e:
            logger.exception(f"Document ingestion failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    async def _store_embeddings_in_butler(
        self,
        embeddings: list[Any],
        metadata: dict[str, Any],
    ) -> None:
        """Store embeddings in Butler's vector store.

        Args:
            embeddings: List of embeddings to store.
            metadata: Metadata for the embeddings.
        """
        if not self._vector_store:
            return

        try:
            # Phase 2: Basic embedding storage
            # Phase 3: Full integration with Butler's vector store and metadata

            for i, embedding in enumerate(embeddings):
                self._vector_store.index(
                    entry_id=f"crewai_knowledge_{metadata.get('document_path', 'unknown')}_{i}",
                    embedding=embedding,
                    payload={
                        **metadata,
                        "chunk_index": i,
                        "source": "crewai_knowledge",
                    },
                )

            logger.info(f"Stored {len(embeddings)} embeddings in Butler vector store")

        except Exception as e:
            logger.warning(f"Failed to store embeddings in Butler: {e}")

    async def retrieve_knowledge(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve relevant knowledge from CrewAI Knowledge with Butler storage.

        Args:
            query: Query string for knowledge retrieval.
            top_k: Number of results to retrieve.
            filters: Optional filters for retrieval.

        Returns:
            List of retrieved knowledge items.
        """
        try:
            from crewai import Knowledge

            # Apply security guardrails to query if enabled
            if self._content_guard:
                safety_check = await self._content_guard.check(query)
                if not safety_check.get("safe", True):
                    logger.warning(
                        f"ContentGuard blocked knowledge query: {safety_check.get('reason')}"
                    )
                    return []

            # Create CrewAI Knowledge instance
            knowledge = Knowledge()

            # Retrieve from CrewAI Knowledge
            crewai_results = knowledge.search(query, top_k=top_k)

            # Retrieve from Butler's vector store if available
            butler_results = []
            if self._vector_store:
                butler_results = await self._retrieve_from_butler_vector_store(
                    query=query,
                    top_k=top_k,
                    filters=filters,
                )

            # Merge and deduplicate results
            merged_results = self._merge_results(crewai_results, butler_results)

            logger.info(f"Retrieved {len(merged_results)} knowledge items for query")

            return merged_results

        except ImportError:
            logger.warning("CrewAI not installed - Knowledge integration disabled")
            return []
        except Exception as e:
            logger.exception(f"Knowledge retrieval failed: {e}")
            return []

    async def _retrieve_from_butler_vector_store(
        self,
        query: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve knowledge from Butler's vector store.

        Args:
            query: Query string.
            top_k: Number of results.
            filters: Optional filters.

        Returns:
            List of retrieved items.
        """
        if not self._vector_store:
            return []

        try:
            # Phase 2: Basic vector store retrieval
            # Phase 3: Full integration with Butler's retrieval fusion engine

            # This is a placeholder for actual vector store retrieval
            # In Phase 3, this will use Butler's RetrievalFusionEngine
            logger.info(f"Retrieving from Butler vector store: query={query}, top_k={top_k}")
            return []

        except Exception as e:
            logger.warning(f"Butler vector store retrieval failed: {e}")
            return []

    def _merge_results(
        self,
        crewai_results: list[Any],
        butler_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge and deduplicate results from CrewAI and Butler.

        Args:
            crewai_results: Results from CrewAI Knowledge.
            butler_results: Results from Butler vector store.

        Returns:
            Merged and deduplicated results.
        """
        # Phase 2: Simple concatenation
        # Phase 3: Advanced merging with scoring and deduplication

        merged = []

        # Add CrewAI results
        for result in crewai_results:
            merged.append({
                "source": "crewai",
                "content": str(result),
                "metadata": {},
            })

        # Add Butler results
        for result in butler_results:
            merged.append({
                "source": "butler",
                "content": result.get("content", ""),
                "metadata": result.get("metadata", {}),
            })

        return merged


class HybridKnowledgeRetriever:
    """Hybrid knowledge retriever combining CrewAI and Butler systems.

    This retriever provides a unified interface for knowledge retrieval
    that combines:
    - CrewAI's multi-source document ingestion
    - Butler's vector store and retrieval fusion
    - Butler's security guardrails
    - Butler's governance and access control
    """

    def __init__(
        self,
        crewai_adapter: CrewAIKnowledgeAdapter,
        butler_vector_store: Any = None,
    ) -> None:
        """Initialize Hybrid Knowledge Retriever.

        Args:
            crewai_adapter: CrewAI Knowledge adapter.
            butler_vector_store: Butler's vector store instance.
        """
        self._crewai_adapter = crewai_adapter
        self._crewai_adapter.set_vector_store(butler_vector_store)

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        sources: list[str] | None = None,
    ) -> dict[str, Any]:
        """Retrieve knowledge from multiple sources.

        Args:
            query: Query string.
            top_k: Number of results per source.
            sources: List of sources to query (crewai, butler, both).

        Returns:
            Retrieval results with metadata.
        """
        sources = sources or ["both"]

        results = {
            "crewai": [],
            "butler": [],
            "merged": [],
        }

        if sources in ["crewai", "both"]:
            results["crewai"] = await self._crewai_adapter.retrieve_knowledge(
                query=query,
                top_k=top_k,
            )

        if sources in ["butler", "both"]:
            results["butler"] = await self._crewai_adapter.retrieve_knowledge(
                query=query,
                top_k=top_k,
            )

        if sources == "both":
            results["merged"] = self._crewai_adapter._merge_results(
                results["crewai"],
                results["butler"],
            )

        return results
