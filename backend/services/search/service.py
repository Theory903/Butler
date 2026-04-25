from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.circuit_breaker import CircuitBreakerRegistry, CircuitOpenError
from domain.ml.contracts import (
    IReasoningRuntime,
    ReasoningRequest,
    ReasoningTier,
    ResponseFormat,
)
from domain.search.contracts import (
    AnsweringEngineResult,
    ISearchService,
    SearchClassification,
    SearchEvidencePack,
    SearchResult,
    SearchWidget,
)
from services.search.extraction import ContentExtractor
from services.search.web_provider import ButlerWebSearchProvider
from services.search.web_provider import EvidencePack as WebEvidencePack

if TYPE_CHECKING:
    from services.search.deep_research import DeepResearchEngine, DeepResearchResult


logger = structlog.get_logger(__name__)


class _SearchAnswerPayload(BaseModel):
    """Strict structured payload for final synthesized answers."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1)


class _SearchClassificationPayload(BaseModel):
    """Strict structured payload for search-intent classification."""

    model_config = ConfigDict(extra="forbid")

    skip_search: bool = False
    personal_search: bool = False
    transactional_search: bool = False
    research_search: bool = False
    discussion_search: bool = False
    ambiguous_search: bool = False
    show_weather_widget: bool = False
    show_stock_widget: bool = False
    show_calculation_widget: bool = False


@dataclass(frozen=True, slots=True)
class _ExtractionOutcome:
    url: str
    title: str
    snippet: str
    published_date: datetime | None
    score: float
    extracted_text: str | None
    extraction_method: str
    provider: str | None = None
    engine: str = "web"


class SearchService(ISearchService):
    """Butler Evidence Engine — production search orchestration with multi-tenant support.

    Coordinates:
      - web discovery provider
      - deep page extraction
      - optional multi-hop research engine
      - optional answer synthesis over normalized evidence
      - optional model-first lightweight classification for widgets/answer posture
    All operations support tenant isolation for production multi-tenant deployment.
    """

    def __init__(
        self,
        extractor: ContentExtractor,
        provider: ButlerWebSearchProvider | None = None,
        ml_runtime: IReasoningRuntime | None = None,
        breakers: CircuitBreakerRegistry | None = None,
        *,
        max_concurrent_extractions: int = 5,
        min_extracted_chars: int = 200,
        max_content_chars: int = 4000,
        max_answer_sources: int = 5,
        answer_generation_tier_with_sources: ReasoningTier = ReasoningTier.T3,
        answer_generation_tier_without_sources: ReasoningTier = ReasoningTier.T2,
        classification_tier: ReasoningTier = ReasoningTier.T2,
    ) -> None:
        if max_concurrent_extractions <= 0:
            raise ValueError("max_concurrent_extractions must be greater than 0")
        if min_extracted_chars < 0:
            raise ValueError("min_extracted_chars must be non-negative")
        if max_content_chars <= 0:
            raise ValueError("max_content_chars must be greater than 0")
        if max_answer_sources <= 0:
            raise ValueError("max_answer_sources must be greater than 0")

        self._extractor = extractor
        self._provider = provider or ButlerWebSearchProvider.from_env()
        self._ml = ml_runtime
        self._breakers = breakers
        self._deep_engine: DeepResearchEngine | None = None

        self._max_concurrent_extractions = max_concurrent_extractions
        self._min_extracted_chars = min_extracted_chars
        self._max_content_chars = max_content_chars
        self._max_answer_sources = max_answer_sources
        self._answer_generation_tier_with_sources = answer_generation_tier_with_sources
        self._answer_generation_tier_without_sources = answer_generation_tier_without_sources
        self._classification_tier = classification_tier
        self._extraction_semaphore = asyncio.Semaphore(max_concurrent_extractions)

    async def close(self) -> None:
        """Close owned resources that expose async shutdown."""
        close_fn = getattr(self._extractor, "close", None)
        if callable(close_fn):
            await close_fn()

    def _ensure_deep_engine(self) -> None:
        """Lazy-initialize the deep research engine."""
        if self._deep_engine is None and self._ml is not None:
            from services.search.deep_research import DeepResearchEngine

            self._deep_engine = DeepResearchEngine(self._ml, self)

    async def search(
        self,
        query: str,
        mode: str = "auto",
        max_results: int = 5,
        tenant_id: str | None = None,
        **kwargs: Any,
    ) -> SearchEvidencePack:
        """Execute discovery -> extraction -> normalization with tenant isolation."""
        del kwargs
        started_at = time.perf_counter()
        normalized_query = query.strip()
        normalized_mode = self._normalize_mode(mode)

        if not normalized_query:
            return self._empty_evidence_pack(
                query="",
                mode=normalized_mode,
                started_at=started_at,
                tenant_id=tenant_id,
            )

        web_pack = await self._discover(
            query=normalized_query,
            mode=normalized_mode,
            max_results=max_results,
        )
        if web_pack is None:
            return self._empty_evidence_pack(
                query=normalized_query,
                mode=normalized_mode,
                started_at=started_at,
                tenant_id=tenant_id,
            )

        extraction_outcomes = await self._extract_all(web_pack)
        final_results = [self._build_search_result(outcome) for outcome in extraction_outcomes]
        citations = self._build_citations(final_results)

        return SearchEvidencePack(
            query=normalized_query,
            mode=web_pack.mode,
            results=final_results,
            citations=citations,
            result_count=len(final_results),
            latency_ms=(time.perf_counter() - started_at) * 1000,
            provider=getattr(web_pack, "provider", None),
            metadata={"tenant_id": tenant_id} if tenant_id else {},
        )

    async def answer(
        self,
        query: str,
        chat_history: list[dict[str, str]] | None = None,
        tenant_id: str | None = None,
    ) -> AnsweringEngineResult:
        """Answer a query using search + optional reasoning synthesis with tenant isolation."""
        normalized_query = query.strip()
        normalized_history = list(chat_history or [])

        if not normalized_query:
            empty_classification = SearchClassification(
                skip_search=True,
                personal_search=False,
                transactional_search=False,
                research_search=False,
                discussion_search=False,
                ambiguous_search=False,
                show_weather_widget=False,
                show_stock_widget=False,
                show_calculation_widget=False,
                academic_search=False,
            )
            return AnsweringEngineResult(
                answer="Please provide a query.",
                sources=[],
                classification=empty_classification,
                widgets=[],
                metadata={
                    "provider": None,
                    "latency_ms": 0.0,
                    "result_count": 0,
                    "mode": "auto",
                    "tenant_id": tenant_id,
                },
            )

        standalone_query = await self._rewrite_followup_query(
            query=normalized_query,
            chat_history=normalized_history,
        )

        classification = await self._classify_query(
            query=standalone_query,
            chat_history=normalized_history,
        )

        evidence = await self.search(
            standalone_query,
            mode="auto",
            max_results=self._max_answer_sources,
            tenant_id=tenant_id,
        )
        sources = list(evidence.results)

        answer_text = await self._generate_answer(
            original_query=normalized_query,
            standalone_query=standalone_query,
            sources=sources,
            classification=classification,
        )

        widgets = self._build_widgets(classification, standalone_query)

        return AnsweringEngineResult(
            answer=answer_text,
            sources=sources,
            classification=classification,
            widgets=widgets,
            metadata={
                "provider": evidence.provider,
                "latency_ms": evidence.latency_ms,
                "result_count": evidence.result_count,
                "mode": evidence.mode,
                "standalone_query": standalone_query,
                "tenant_id": tenant_id,
            },
        )

    async def deep_research(
        self,
        query: str,
        tenant_id: str,  # Required for multi-tenant isolation
        context: str | None = None,
    ) -> DeepResearchResult:
        """Execute multi-hop deep research with tenant isolation when available."""
        self._ensure_deep_engine()

        if self._deep_engine is None:
            logger.warning("deep_research_engine_not_initialised")
            from services.search.deep_research import DeepResearchResult

            basic_results = await self.search(query, tenant_id=tenant_id)
            snippet = (
                basic_results.results[0].content[:200] if basic_results.results else "No results"
            )
            return DeepResearchResult(
                original_query=query,
                summary=f"Deep research engine unavailable. Basic result: {snippet}",
                steps=[],
                all_evidence=basic_results.results,
                completed=True,
            )

        return await self._deep_engine.conduct_research(query, tenant_id, context)

    async def as_retriever(self, max_results: int = 5):
        """Expose search as LangChain Retriever."""
        from backend.langchain.retrievers import ButlerSearchRetriever

        return ButlerSearchRetriever(search_service=self, max_results=max_results)

    async def _discover(
        self,
        *,
        query: str,
        mode: str,
        max_results: int,
    ) -> WebEvidencePack | None:
        """Run discovery through the configured search provider."""
        try:

            async def _do_search() -> WebEvidencePack:
                return await self._provider.search(
                    query=query,
                    mode="general" if mode == "auto" else mode,
                    max_results=max_results,
                )

            if self._breakers is not None:
                breaker = self._breakers.get_breaker("search:web")
                return await breaker.call(_do_search)

            return await _do_search()

        except CircuitOpenError:
            logger.warning("search_provider_circuit_open", query=query, mode=mode)
            return None
        except Exception:
            logger.exception("search_provider_failed", query=query, mode=mode)
            return None

    async def _extract_all(
        self,
        web_pack: WebEvidencePack,
    ) -> list[_ExtractionOutcome]:
        """Extract content from all discovered URLs with bounded concurrency."""

        async def _run_one(result: Any) -> _ExtractionOutcome:
            async with self._extraction_semaphore:
                try:
                    extraction = await self._extractor.extract(result.url)
                except Exception:
                    logger.exception("content_extraction_failed", url=result.url)
                    extraction = None

                extracted_text: str | None = None
                extraction_method = "snippet"

                if (
                    extraction is not None
                    and getattr(extraction, "text", None)
                    and len(extraction.text) >= self._min_extracted_chars
                ):
                    extracted_text = extraction.text
                    extraction_method = getattr(extraction, "method", "extractor")

                return _ExtractionOutcome(
                    url=result.url,
                    title=result.title,
                    snippet=result.snippet,
                    published_date=result.published_date,
                    score=result.combined_score,
                    extracted_text=extracted_text,
                    extraction_method=extraction_method,
                    provider=getattr(web_pack, "provider", None),
                    engine=getattr(result, "provider", "web"),
                )

        tasks = [_run_one(result) for result in web_pack.results]
        return await asyncio.gather(*tasks)

    def _build_search_result(self, outcome: _ExtractionOutcome) -> SearchResult:
        """Build normalized contract search result with safe fallback to snippet."""
        content_text = outcome.extracted_text if outcome.extracted_text else outcome.snippet
        published_date = outcome.published_date.isoformat() if outcome.published_date else None

        return SearchResult(
            url=outcome.url,
            title=outcome.title,
            content=content_text[: self._max_content_chars],
            snippet=outcome.snippet[: self._max_content_chars],
            engine=outcome.engine or "web",
            score=outcome.score,
            published_date=published_date,
            metadata={
                "extraction_method": outcome.extraction_method,
                "provider": outcome.provider,
            },
        )

    def _build_citations(self, results: list[SearchResult]) -> list[dict[str, Any]]:
        """Build citations from final normalized evidence."""
        return [
            {
                "url": result.url,
                "title": result.title,
                "published_date": result.published_date,
                "score": result.score,
                "engine": result.engine,
                "extraction_method": result.metadata.get("extraction_method"),
            }
            for result in results
        ]

    def _empty_evidence_pack(
        self,
        *,
        query: str,
        mode: str,
        started_at: float,
        tenant_id: str | None = None,
    ) -> SearchEvidencePack:
        return SearchEvidencePack(
            query=query,
            mode=mode,
            results=[],
            citations=[],
            result_count=0,
            latency_ms=(time.perf_counter() - started_at) * 1000,
            provider=None,
            metadata={"tenant_id": tenant_id} if tenant_id else {},
        )

    def _normalize_mode(self, mode: str) -> str:
        normalized = (mode or "").strip().lower()
        return normalized or "auto"

    async def _rewrite_followup_query(
        self,
        *,
        query: str,
        chat_history: list[dict[str, str]],
    ) -> str:
        """Rewrite follow-up queries into a standalone query when possible."""
        if self._ml is None or not chat_history:
            return query

        formatted_history = self._format_history(chat_history)
        request = ReasoningRequest(
            prompt=(
                "Rewrite the user's latest query into a standalone search query.\n\n"
                f"Latest query:\n{query}\n\n"
                f"Recent chat history:\n{formatted_history}\n\n"
                "Return JSON only with this schema:\n"
                "{\n"
                '  "standalone_query": "..." \n'
                "}\n"
            ),
            system_prompt=(
                "You are Butler's multilingual follow-up query rewriter.\n"
                "Preserve user language when reasonable.\n"
                "Do not add facts not implied by the conversation.\n"
                "If the query is already standalone, return it unchanged.\n"
                "Return only valid JSON."
            ),
            max_tokens=300,
            temperature=0.0,
            response_format=ResponseFormat.JSON,
            metadata={"task": "search_followup_rewrite"},
        )

        try:
            response = await self._ml.generate(
                request,
                tenant_id="default",  # P0: Search service uses default tenant_id
                preferred_tier=self._classification_tier,
            )
            payload = self._extract_json_object(response.content)
            standalone_query = payload.get("standalone_query")
            if isinstance(standalone_query, str) and standalone_query.strip():
                return standalone_query.strip()
        except Exception:
            logger.exception("search_followup_rewrite_failed")

        return query

    async def _classify_query(
        self,
        *,
        query: str,
        chat_history: list[dict[str, str]],
    ) -> SearchClassification:
        """Classify query intent for widget hints and answer posture."""
        if self._ml is None:
            return self._fallback_classify_from_query(query)

        request = ReasoningRequest(
            prompt=(
                "Classify the search intent of this query.\n\n"
                f"Query:\n{query}\n\n"
                f"Recent chat history:\n{self._format_history(chat_history)}\n\n"
                "Return JSON only with this schema:\n"
                "{\n"
                '  "skip_search": false,\n'
                '  "personal_search": false,\n'
                '  "transactional_search": false,\n'
                '  "research_search": false,\n'
                '  "discussion_search": false,\n'
                '  "ambiguous_search": false,\n'
                '  "show_weather_widget": false,\n'
                '  "show_stock_widget": false,\n'
                '  "show_calculation_widget": false\n'
                "}\n"
            ),
            system_prompt=(
                "You are Butler's multilingual search classifier.\n"
                "Be language-agnostic.\n"
                "Do not assume English.\n"
                "Use widget flags only when strongly indicated.\n"
                "Return only valid JSON."
            ),
            max_tokens=400,
            temperature=0.0,
            response_format=ResponseFormat.JSON,
            metadata={"task": "search_classification"},
        )

        try:
            response = await self._ml.generate(
                request,
                tenant_id="default",  # P0: Search service uses default tenant_id
                preferred_tier=self._classification_tier,
            )
            payload = _SearchClassificationPayload.model_validate(
                self._extract_json_object(response.content)
            )

            return SearchClassification(
                skip_search=payload.skip_search,
                personal_search=payload.personal_search,
                transactional_search=payload.transactional_search,
                research_search=payload.research_search,
                discussion_search=payload.discussion_search,
                ambiguous_search=payload.ambiguous_search,
                show_weather_widget=payload.show_weather_widget,
                show_stock_widget=payload.show_stock_widget,
                show_calculation_widget=payload.show_calculation_widget,
                academic_search=payload.research_search,
            )
        except Exception:
            logger.exception("search_classification_failed")
            return self._fallback_classify_from_query(query)

    def _fallback_classify_from_query(self, query: str) -> SearchClassification:
        """Minimal local fallback classification.

        This stays intentionally small. It is a fallback rail, not the core brain.
        """
        lowered = query.lower()

        weather_terms = ("weather", "forecast", "temperature", "rain", "humidity", "wind")
        stock_terms = (
            "stock",
            "share price",
            "ticker",
            "market cap",
            "crypto",
            "bitcoin",
            "ethereum",
            "btc",
            "eth",
        )
        calc_terms = ("calculate", "compute", "convert", "+", "-", "*", "/", "%")

        return SearchClassification(
            skip_search=False,
            personal_search=False,
            transactional_search=False,
            research_search=False,
            discussion_search=False,
            ambiguous_search=False,
            show_weather_widget=any(term in lowered for term in weather_terms),
            show_stock_widget=any(term in lowered for term in stock_terms),
            show_calculation_widget=any(term in lowered for term in calc_terms),
            academic_search=False,
        )

    async def _generate_answer(
        self,
        *,
        original_query: str,
        standalone_query: str,
        sources: list[SearchResult],
        classification: SearchClassification,
    ) -> str:
        """Generate a grounded answer from normalized sources."""
        if self._ml is None:
            return self._fallback_answer(standalone_query, sources)

        source_block = self._format_sources_for_writer(sources)

        request = ReasoningRequest(
            prompt=(
                f"Original user query:\n{original_query}\n\n"
                f"Standalone query:\n{standalone_query}\n\n"
                f"Classification:\n{classification.model_dump_json()}\n\n"
                f"Sources:\n{source_block}\n\n"
                "Return JSON only with this schema:\n"
                "{\n"
                '  "answer": "grounded answer text"\n'
                "}\n\n"
                "Write a helpful, grounded answer.\n"
                "Use citations like [1], [2], [3] when supported by the sources.\n"
                "If sources are weak or absent, say so clearly.\n"
                "Do not invent facts not grounded in the provided material."
            ),
            system_prompt=(
                "You are Butler's answer synthesis engine.\n"
                "Be concise, grounded, and multilingual-friendly.\n"
                "Answer in the same language as the user query when reasonable.\n"
                "Return only valid JSON."
            ),
            max_tokens=1200,
            temperature=0.2,
            response_format=ResponseFormat.JSON,
            metadata={"task": "search_answer_generation"},
        )

        try:
            response = await self._ml.generate(
                request,
                tenant_id="default",  # P0: Search service uses default tenant_id
                preferred_tier=(
                    self._answer_generation_tier_with_sources
                    if sources
                    else self._answer_generation_tier_without_sources
                ),
            )
            answer = self._extract_answer_from_json(response.content)
            if answer:
                return answer
        except Exception:
            logger.exception("search_service_answer_generation_failed", query=original_query[:80])

        return self._fallback_answer(standalone_query, sources)

    def _extract_answer_from_json(self, raw: str) -> str:
        """Strict answer payload extraction."""
        try:
            payload = _SearchAnswerPayload.model_validate(self._extract_json_object(raw))
        except ValidationError as exc:
            raise ValueError("Invalid answer payload") from exc
        return payload.answer.strip()

    def _extract_json_object(self, raw: str) -> dict[str, Any]:
        """Best-effort JSON object extraction."""
        text = (raw or "").strip()

        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1]).strip()

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]

        try:
            payload = json.loads(text)
        except Exception as exc:
            raise ValueError("Invalid JSON payload") from exc

        if not isinstance(payload, dict):
            raise ValueError("Payload must be a JSON object")

        return payload

    def _fallback_answer(
        self,
        query: str,
        sources: list[SearchResult],
    ) -> str:
        if sources:
            lines = [f"I found {len(sources)} relevant sources for '{query}'."]
            for index, source in enumerate(sources[:3], start=1):
                lines.append(f"[{index}] {source.title} — {source.url}")
            return "\n".join(lines)

        return (
            f"I couldn't find strong current results for '{query}'. "
            "Try a more specific query or provide more context."
        )

    def _format_sources_for_writer(self, sources: list[SearchResult]) -> str:
        if not sources:
            return "(no sources)"

        blocks: list[str] = []
        for index, source in enumerate(sources[: self._max_answer_sources], start=1):
            content = (source.content or source.snippet or "")[: self._max_content_chars]
            blocks.append(
                f"[{index}] {source.url}\n"
                f"Title: {source.title}\n"
                f"Snippet: {source.snippet}\n"
                f"Content: {content}"
            )
        return "\n\n".join(blocks)

    def _build_widgets(
        self,
        prefs: SearchClassification,
        query: str,
    ) -> list[SearchWidget]:
        widgets: list[SearchWidget] = []

        if prefs.show_weather_widget:
            widgets.append(SearchWidget(kind="weather", payload={"query": query}))
        if prefs.show_stock_widget:
            widgets.append(SearchWidget(kind="stock", payload={"query": query}))
        if prefs.show_calculation_widget:
            widgets.append(SearchWidget(kind="calculator", payload={"query": query}))

        return widgets

    def _format_history(self, chat_history: list[dict[str, str]]) -> str:
        if not chat_history:
            return "(none)"

        lines: list[str] = []
        for item in chat_history[-6:]:
            role = str(item.get("role", "user")).strip() or "user"
            content = str(item.get("content", "")).strip()
            if content:
                lines.append(f"{role}: {content}")

        return "\n".join(lines) if lines else "(none)"
