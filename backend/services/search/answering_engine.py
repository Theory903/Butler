"""AnsweringEngine — AI-first multilingual search-answer pipeline.

Design goals:
- model-first classification and follow-up rewriting
- schema-validated structured outputs
- multilingual / code-mixed query support
- minimal deterministic fallback rails
- grounded answer synthesis over normalized search results
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from domain.ml.contracts import (
    IReasoningRuntime,
    ReasoningRequest,
    ReasoningTier,
    ResponseFormat,
)
from domain.search.contracts import (
    AnsweringEngineResult,
    ClassifierResult,
    ISearchAdapter,
    SearchClassification,
    SearchResult,
    SearchWidget,
)

logger = structlog.get_logger(__name__)


class _ClassificationPayload(BaseModel):
    """Structured model output for search classification."""

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

    standalone_follow_up: str = Field(default="")
    rationale: str = Field(default="")


class _AnswerPayload(BaseModel):
    """Structured answer-generation payload."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1)


class _JsonModelParser:
    """Robust JSON-to-model parser for LLM outputs."""

    @staticmethod
    def parse(raw: str, model_type: type[BaseModel]) -> BaseModel:
        candidates = _JsonModelParser._candidate_json_strings(raw)
        last_error: Exception | None = None

        for candidate in candidates:
            try:
                return model_type.model_validate_json(candidate)
            except (ValidationError, ValueError) as exc:
                last_error = exc
                continue

        raise ValueError(f"Could not parse structured model output: {last_error}") from last_error

    @staticmethod
    def _candidate_json_strings(raw: str) -> list[str]:
        content = (raw or "").strip()
        candidates: list[str] = []

        if content:
            candidates.append(content)

        if content.startswith("```"):
            lines = content.splitlines()
            if len(lines) >= 3:
                unfenced = "\n".join(lines[1:-1]).strip()
                if unfenced:
                    candidates.append(unfenced)

        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            extracted = content[start : end + 1].strip()
            if extracted:
                candidates.append(extracted)

        unique: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                unique.append(candidate)

        return unique


class QueryClassifier:
    """AI-first multilingual query classifier.

    Falls back to a tiny deterministic rail only when no runtime is available
    or structured output parsing fails.
    """

    def __init__(self, llm: IReasoningRuntime | None = None) -> None:
        self._llm = llm

    async def classify(
        self,
        query: str,
        chat_history: Sequence[dict[str, str]] | None = None,
    ) -> ClassifierResult:
        normalized_query = query.strip()
        history = list(chat_history or [])

        if not normalized_query:
            return ClassifierResult(
                classification=SearchClassification(
                    skip_search=True,
                    ambiguous_search=False,
                ),
                standalone_follow_up="",
            )

        if self._llm is not None:
            try:
                return await self._llm_classify(normalized_query, history)
            except Exception:
                logger.exception("query_classifier_llm_failed")

        return self._fallback_classify(normalized_query, history)

    async def _llm_classify(
        self,
        query: str,
        chat_history: Sequence[dict[str, str]],
    ) -> ClassifierResult:
        history_block = self._format_history(chat_history)

        request = ReasoningRequest(
            prompt=(
                "Classify the user query for Butler's search-answer pipeline.\n\n"
                f"Query:\n{query}\n\n"
                f"Recent chat history:\n{history_block}\n\n"
                "Return JSON only with fields:\n"
                "{\n"
                '  "skip_search": false,\n'
                '  "personal_search": false,\n'
                '  "transactional_search": false,\n'
                '  "research_search": false,\n'
                '  "discussion_search": false,\n'
                '  "ambiguous_search": false,\n'
                '  "show_weather_widget": false,\n'
                '  "show_stock_widget": false,\n'
                '  "show_calculation_widget": false,\n'
                '  "standalone_follow_up": "rewritten standalone query",\n'
                '  "rationale": "brief explanation"\n'
                "}\n"
            ),
            system_prompt=(
                "You are Butler's multilingual search-intent classifier.\n"
                "Handle any language, mixed language, transliteration, or code-mixed input.\n"
                "Do not assume English.\n"
                "Set skip_search=true only for trivial conversational turns or requests that clearly do not need web search.\n"
                "Set personal_search=true when the request is primarily about the user's own private data/history.\n"
                "Set transactional_search=true when the user is trying to perform an action.\n"
                "Set research_search=true for academic, technical, literature, or deep factual research.\n"
                "Set discussion_search=true for opinion/community/forum style requests.\n"
                "Set ambiguous_search=true only when intent remains unclear after reading the query and history.\n"
                "Set widget flags only when strongly indicated.\n"
                "Produce a standalone_follow_up that can be searched directly."
            ),
            max_tokens=600,
            temperature=0.1,
            response_format=ResponseFormat.JSON,
            metadata={"task": "search_query_classification"},
        )

        response = await self._llm.generate(
            request,
            tenant_id="default",  # P0: Search answering uses default tenant_id
            preferred_tier=ReasoningTier.T2,
        )
        payload = _JsonModelParser.parse(response.content, _ClassificationPayload)

        classification = SearchClassification(
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

        standalone = payload.standalone_follow_up.strip() or query

        logger.debug(
            "query_classified",
            query=query[:80],
            skip_search=classification.skip_search,
            personal_search=classification.personal_search,
            transactional_search=classification.transactional_search,
            research_search=classification.research_search,
            discussion_search=classification.discussion_search,
            ambiguous_search=classification.ambiguous_search,
            show_weather_widget=classification.show_weather_widget,
            show_stock_widget=classification.show_stock_widget,
            show_calculation_widget=classification.show_calculation_widget,
        )

        return ClassifierResult(
            classification=classification,
            standalone_follow_up=standalone,
        )

    def _fallback_classify(
        self,
        query: str,
        chat_history: Sequence[dict[str, str]],
    ) -> ClassifierResult:
        """Minimal deterministic fallback rail.

        Keep this intentionally small and language-light.
        """
        tokens = query.split()
        standalone = query

        if chat_history and len(tokens) <= 4:
            last_user = next(
                (
                    item.get("content", "")
                    for item in reversed(chat_history)
                    if item.get("role") == "user" and item.get("content", "").strip()
                ),
                "",
            )
            if last_user and last_user.strip().lower() != query.lower():
                standalone = f"{last_user}. {query}"

        classification = SearchClassification(
            skip_search=len(tokens) <= 1,
            ambiguous_search=len(tokens) > 1,
        )

        return ClassifierResult(
            classification=classification,
            standalone_follow_up=standalone,
        )

    def _format_history(self, chat_history: Sequence[dict[str, str]]) -> str:
        if not chat_history:
            return "(none)"

        lines: list[str] = []
        for item in chat_history[-6:]:
            role = item.get("role", "user")
            content = item.get("content", "").strip()
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines) if lines else "(none)"


class AnsweringEngine:
    """Butler's AI-first query classification and answer synthesis pipeline."""

    def __init__(
        self,
        search_adapter: ISearchAdapter,
        llm: IReasoningRuntime | None = None,
        breakers: Any | None = None,
        max_sources: int = 8,
        max_writer_sources: int = 5,
        max_source_chars: int = 1200,
    ) -> None:
        if max_sources <= 0:
            raise ValueError("max_sources must be greater than 0")
        if max_writer_sources <= 0:
            raise ValueError("max_writer_sources must be greater than 0")
        if max_source_chars <= 0:
            raise ValueError("max_source_chars must be greater than 0")

        self._search = search_adapter
        self._llm = llm
        self._breakers = breakers
        self._classifier = QueryClassifier(llm=llm)
        self._max_sources = max_sources
        self._max_writer_sources = max_writer_sources
        self._max_source_chars = max_source_chars

    async def classify(
        self,
        query: str,
        chat_history: Sequence[dict[str, str]] | None = None,
    ) -> ClassifierResult:
        return await self._classifier.classify(query, chat_history or [])

    async def answer(
        self,
        query: str,
        chat_history: Sequence[dict[str, str]] | None = None,
    ) -> AnsweringEngineResult:
        history = list(chat_history or [])

        classification_result = await self.classify(query, history)
        standalone_query = classification_result.standalone_follow_up
        prefs = classification_result.classification

        sources: list[SearchResult] = []
        if not prefs.skip_search:
            categories = self._build_categories(prefs)
            try:
                raw_results = await self._search.search(
                    standalone_query,
                    categories=categories,
                    num_results=self._max_sources,
                )
                sources = self._normalize_sources(raw_results[: self._max_sources])
            except Exception:
                logger.exception(
                    "answering_engine_search_failed",
                    query=standalone_query[:80],
                )

        answer_text = await self._generate_answer(
            original_query=query,
            standalone_query=standalone_query,
            sources=sources,
            classification=prefs,
        )
        widgets = self._build_widgets(prefs, standalone_query)

        logger.info(
            "answering_engine_complete",
            query=query[:80],
            source_count=len(sources),
            widget_count=len(widgets),
        )

        return AnsweringEngineResult(
            answer=answer_text,
            sources=sources,
            classification=prefs,
            widgets=widgets,
            metadata={
                "standalone_query": standalone_query,
            },
        )

    def _build_categories(self, prefs: SearchClassification) -> list[str]:
        categories = ["general"]
        if prefs.research_search:
            categories.append("science")
        if prefs.discussion_search:
            categories.append("social media")
        return categories

    def _normalize_sources(self, raw_results: Sequence[dict[str, Any]]) -> list[SearchResult]:
        sources: list[SearchResult] = []
        for item in raw_results:
            try:
                sources.append(SearchResult.model_validate(item))
            except Exception:
                logger.debug("answering_engine_invalid_source_ignored")
        return sources

    async def _generate_answer(
        self,
        *,
        original_query: str,
        standalone_query: str,
        sources: Sequence[SearchResult],
        classification: SearchClassification,
    ) -> str:
        if self._llm is None:
            return self._fallback_answer(standalone_query, sources)

        source_block = self._format_sources_for_writer(sources)
        request = ReasoningRequest(
            prompt=(
                f"User query:\n{original_query}\n\n"
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
                "You are Butler's answering engine.\n"
                "Be concise, grounded, and multilingual-friendly.\n"
                "Answer in the same language as the user query when reasonable.\n"
                "Prefer directness over fluff.\n"
                "Return only valid JSON."
            ),
            max_tokens=1200,
            temperature=0.2,
            response_format=ResponseFormat.JSON,
            metadata={"task": "answer_generation"},
        )

        try:
            response = await self._llm.generate(
                request,
                tenant_id="default",  # P0: Search answering uses default tenant_id
                preferred_tier=ReasoningTier.T3 if sources else ReasoningTier.T2,
            )
            payload = _JsonModelParser.parse(response.content, _AnswerPayload)
            answer = payload.answer.strip()
            if answer:
                return answer
        except Exception:
            logger.exception("answer_generation_failed", query=standalone_query[:80])

        return self._fallback_answer(standalone_query, sources)

    def _fallback_answer(
        self,
        standalone_query: str,
        sources: Sequence[SearchResult],
    ) -> str:
        if sources:
            lines = [f"I found {len(sources)} relevant sources for '{standalone_query}'."]
            for index, source in enumerate(sources[:3], start=1):
                lines.append(f"[{index}] {source.title} — {source.url}")
            return "\n".join(lines)

        return (
            f"I couldn't find strong current results for '{standalone_query}'. "
            "Try a more specific query or provide more context."
        )

    def _format_sources_for_writer(self, sources: Sequence[SearchResult]) -> str:
        if not sources:
            return "(no sources)"

        blocks: list[str] = []
        for index, source in enumerate(sources[: self._max_writer_sources], start=1):
            content = (source.content or source.snippet or "")[: self._max_source_chars]
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
        standalone_query: str,
    ) -> list[SearchWidget]:
        widgets: list[SearchWidget] = []

        if prefs.show_weather_widget:
            widgets.append(SearchWidget(kind="weather", payload={"query": standalone_query}))
        if prefs.show_stock_widget:
            widgets.append(SearchWidget(kind="stock", payload={"query": standalone_query}))
        if prefs.show_calculation_widget:
            widgets.append(SearchWidget(kind="calculator", payload={"query": standalone_query}))

        return widgets
