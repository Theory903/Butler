"""
LangChain Retriever Adapter - Butler search integration preserved.

This adapter exposes Butler's search service as a LangChain BaseRetriever,
supporting evidence retrieval with citations.
"""

from __future__ import annotations

from typing import Any

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from domain.search.contracts import ISearchService


class ButlerSearchRetriever(BaseRetriever):
    """LangChain retriever adapter for Butler's search service.

    This adapter:
    - Wraps Butler's SearchService for evidence retrieval
    - Converts Butler search results to LangChain Document format
    - Supports evidence packs with citations
    - Integrates with Butler's 4-tier memory architecture
    """

    def __init__(
        self,
        search_service: ISearchService | None = None,
        max_results: int = 10,
        include_citations: bool = True,
        **kwargs: Any,
    ):
        """Initialize the Butler search retriever.

        Args:
            search_service: Butler's SearchService instance
            max_results: Maximum number of results to return
            include_citations: Whether to include citation metadata
        """
        super().__init__(**kwargs)
        self.search_service = search_service
        self.max_results = max_results
        self.include_citations = include_citations

    async def _aget_relevant_documents(self, query: str, **kwargs: Any) -> list[Document]:
        """Retrieve relevant documents from Butler's search service.

        Args:
            query: Search query string
            **kwargs: Additional search parameters

        Returns:
            List of LangChain Document objects
        """
        if not self.search_service:
            return []

        try:
            # Execute search through Butler's search service
            search_results = await self.search_service.search(
                query=query,
                max_results=self.max_results,
                **kwargs,
            )

            # Convert Butler results to LangChain Documents
            return self._convert_to_documents(search_results)
        except Exception as e:
            import structlog

            logger = structlog.get_logger(__name__)
            logger.warning(
                "search_retriever_fallback",
                query=query,
                error=str(e),
            )
            return []

    def _convert_to_documents(self, search_results: Any) -> list[Document]:
        """Convert Butler search results to LangChain Document format.

        Args:
            search_results: Butler search results object or list

        Returns:
            List of LangChain Document objects
        """
        documents = []

        # Handle different result formats
        if hasattr(search_results, "results"):
            results = search_results.results
        elif hasattr(search_results, "documents"):
            results = search_results.documents
        elif isinstance(search_results, list):
            results = search_results
        else:
            return []

        for result in results:
            # Extract content
            content = getattr(result, "content", str(result))

            # Build metadata
            metadata = {
                "source": getattr(result, "source", "unknown"),
                "score": getattr(result, "score", 0.0),
                "retrieved_at": getattr(result, "retrieved_at", None),
            }

            # Add citations if available and enabled
            if self.include_citations and hasattr(result, "citations"):
                metadata["citations"] = result.citations

            if self.include_citations and hasattr(result, "url"):
                metadata["url"] = result.url

            # Create LangChain Document
            documents.append(Document(page_content=content, metadata=metadata))

        return documents

    async def aget_evidence_pack(self, query: str, session_id: str | None = None) -> dict[str, Any]:
        """Get an evidence pack with full citation information.

        Args:
            query: Search query string
            session_id: Optional session identifier for context

        Returns:
            Evidence pack dictionary with documents, citations, and metadata
        """
        if not self.search_service:
            return {
                "documents": [],
                "citations": [],
                "metadata": {"error": "search_service_not_available"},
            }

        try:
            # Execute search with evidence pack format
            return await self.search_service.search(
                query=query,
                max_results=self.max_results,
                session_id=session_id,
                format="evidence_pack",
            )

        except Exception as e:
            import structlog

            logger = structlog.get_logger(__name__)
            logger.warning(
                "evidence_pack_failed",
                query=query,
                session_id=session_id,
                error=str(e),
            )
            return {
                "documents": [],
                "citations": [],
                "metadata": {"error": str(e)},
            }
