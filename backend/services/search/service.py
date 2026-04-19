from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from services.search.extraction import ContentExtractor
from services.search.web_provider import ButlerWebSearchProvider, EvidencePack as WebEvidencePack
from domain.ml.contracts import IReasoningRuntime
from domain.search.contracts import ISearchService

if TYPE_CHECKING:
    from services.search.deep_research import DeepResearchEngine, DeepResearchResult

logger = logging.getLogger(__name__)


@dataclass
class ExtractedContent:
    url: str
    title: str
    content: str
    extraction_method: str
    freshness: Optional[datetime]
    score: float = 0.0


@dataclass
class EvidencePack:
    query: str
    mode: str
    results: list[ExtractedContent]
    citations: list[dict]
    result_count: int
    latency_ms: float


class SearchService(ISearchService):
    """Butler Evidence Engine — Production implementation (v3.1).

    Coordinates:
      • WebSearchProvider  — discovery (Tavily / SerpAPI / DDG / SearXNG)
      • ContentExtractor   — deep page extraction (Trafilatura / BS4)
      • DeepResearchEngine — multi-hop synthesis (optional, requires ml_runtime)
    """

    def __init__(
        self,
        extractor: ContentExtractor,
        provider: Optional[ButlerWebSearchProvider] = None,
        ml_runtime: Optional[IReasoningRuntime] = None,
    ) -> None:
        self._extractor = extractor
        self._provider = provider or ButlerWebSearchProvider.from_env()
        self._ml = ml_runtime
        # Lazy-init deep engine to avoid circular import at module level
        self._deep_engine: Optional[DeepResearchEngine] = None

    def _ensure_deep_engine(self) -> None:
        """Lazy-initialise DeepResearchEngine on first use."""
        if self._deep_engine is None and self._ml is not None:
            from services.search.deep_research import DeepResearchEngine
            self._deep_engine = DeepResearchEngine(self._ml, self)

    async def search(
        self,
        query: str,
        mode: str = "auto",
        max_results: int = 5,
        **kwargs: Any,
    ) -> EvidencePack:
        """Execute deep search: Discovery → Extraction → Package."""
        start_time = time.perf_counter()

        # 1. Web discovery
        web_pack: WebEvidencePack = await self._provider.search(
            query=query,
            mode=mode if mode != "auto" else "general",
            max_results=max_results,
        )

        # 2. Parallel deep extraction
        extraction_tasks = [self._extractor.extract(r.url) for r in web_pack.results]
        extraction_results = await asyncio.gather(*extraction_tasks, return_exceptions=True)

        # 3. Merge web + extraction results
        final_results: list[ExtractedContent] = []
        for i, web_result in enumerate(web_pack.results):
            ext_res = extraction_results[i]
            if (
                isinstance(ext_res, Exception)
                or not ext_res.text
                or len(ext_res.text) < 200
            ):
                content_text = web_result.snippet
                method = "snippet"
            else:
                content_text = ext_res.text
                method = ext_res.method

            final_results.append(
                ExtractedContent(
                    url=web_result.url,
                    title=web_result.title,
                    content=content_text[:4000],
                    extraction_method=method,
                    freshness=web_result.published_date,
                    score=web_result.combined_score,
                )
            )

        latency_ms = (time.perf_counter() - start_time) * 1000

        return EvidencePack(
            query=query,
            mode=web_pack.mode,
            results=final_results,
            citations=web_pack.citations,
            result_count=len(final_results),
            latency_ms=latency_ms,
        )

    async def deep_research(
        self,
        query: str,
        context: Optional[str] = None,
    ) -> DeepResearchResult:
        """Execute multi-hop deep research when the engine is available."""
        self._ensure_deep_engine()

        if self._deep_engine is None:
            logger.warning("deep_research_engine_not_initialised")
            from services.search.deep_research import DeepResearchResult
            res = await self.search(query)
            snippet = res.results[0].content[:200] if res.results else "No results"
            return DeepResearchResult(
                original_query=query,
                summary=f"Deep engine unavailable. Basic result: {snippet}",
                steps=[],
                all_evidence=res.results,
                completed=True,
            )

        return await self._deep_engine.conduct_research(query, context)

    def _build_citations(self, results: list[ExtractedContent]) -> list[dict]:
        return [
            {"url": r.url, "title": r.title, "freshness": r.freshness}
            for r in results
        ]
