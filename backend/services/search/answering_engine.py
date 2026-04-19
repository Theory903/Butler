"""AnsweringEngine — v3.1 production classifier + answer pipeline.

Classifier uses a pure keyword-heuristic approach (zero LLM deps, sub-ms).

Classification rules:
  - Buckets are NOT mutually exclusive.
  - Widget flags (weather, stock, calculator) are orthogonal to search type.
  - Ambiguous queries that match no bucket fall into ambiguousSearch.
  - Single-word inputs and pure greetings are skipSearch.
  - Standalone follow-up: append last user turn from history if present.

Classification taxonomy:
  skipSearch           — greetings, single-word
  personalSearch       — user's own data ("my", "mine", "I have")
  transactionalSearch  — order, buy, book, schedule, send
  researchSearch       — paper, arxiv, study, doi, research
  discussionSearch     — reddit, forum, opinion, people think
  ambiguousSearch      — non-trivial query, no other bucket fired
  widgetIntent.*       — orthogonal flags: weather, stock, calculate
"""

from __future__ import annotations

import re
import json
import structlog
from typing import Any

from domain.search.contracts import (
    SearchClassification,
    ClassifierResult,
    SearchResult,
    AnsweringEngineResult,
    ISearchService,
    ISearchAdapter,
)

logger = structlog.get_logger(__name__)

# ── Keyword buckets ────────────────────────────────────────────────────────────

_GREETINGS = frozenset({"hi", "hello", "hey", "yo", "sup", "thanks", "ok", "okay", "bye", "good"})

_PERSONAL_PATTERNS = re.compile(
    r"\b(my|mine|i have|i've|my own|for me|show me my|i want my|"
    r"my account|my order|my calendar|my email|my file|my photo|my data)\b",
    re.I,
)
_TRANSACTIONAL_PATTERNS = re.compile(
    r"\b(order|buy|purchase|book|reserve|schedule|send|pay|sign up|subscribe|"
    r"cancel|refund|return|checkout|add to cart)\b",
    re.I,
)
_RESEARCH_PATTERNS = re.compile(
    r"\b(paper|arxiv|doi|pubmed|academic|journal|study|studies|research|"
    r"literature|preprint|citation|peer.?reviewed|systematic review)\b",
    re.I,
)
_DISCUSSION_PATTERNS = re.compile(
    r"\b(reddit|forum|hacker news|hn|discussion|community|what do people|"
    r"opinion|opinions|thoughts on|subreddit|thread|comments about)\b",
    re.I,
)

# Widget: orthogonal flags
_WEATHER_PATTERNS = re.compile(
    r"\b(weather|temperature|forecast|rain|humidity|wind|snow|sunny|cloudy|"
    r"hot|cold today|feels like)\b",
    re.I,
)
_STOCK_PATTERNS = re.compile(
    r"(\$[A-Z]{1,5}|\b(stock|share price|market cap|p/e ratio|ticker|"
    r"nasdaq|nyse|s&p|dow jones|crypto|bitcoin|ethereum|btc|eth)\b)",
    re.I,
)
_CALC_PATTERNS = re.compile(
    r"(\b(calculate|compute|convert|how much is|what is \d|percentage of|"
    r"square root|logarithm|integral|derivative)\b|"
    r"[\d\s]+[\+\-\*/^%][\d\s]+)",
    re.I,
)


# ── Classifier ────────────────────────────────────────────────────────────────

class QueryClassifier:
    """Pure-heuristic, zero-dependency query intent classifier."""

    def classify(self, query: str, chat_history: list[dict[str, str]] | None = None) -> ClassifierResult:
        q = query.strip()
        tokens = q.lower().split()

        # 1. Skip: empty, single-word greeting, trivially short
        is_skip = (
            not q
            or (len(tokens) == 1 and tokens[0] in _GREETINGS)
            or (len(tokens) <= 2 and all(t in _GREETINGS for t in tokens))
        )

        # 2. Orthogonal widget flags
        show_weather = bool(_WEATHER_PATTERNS.search(q))
        show_stock = bool(_STOCK_PATTERNS.search(q))
        show_calc = bool(_CALC_PATTERNS.search(q))

        # 3. Search-type classification
        is_personal = bool(_PERSONAL_PATTERNS.search(q))
        is_transactional = bool(_TRANSACTIONAL_PATTERNS.search(q))
        is_research = bool(_RESEARCH_PATTERNS.search(q))
        is_discussion = bool(_DISCUSSION_PATTERNS.search(q))

        # 4. Ambiguous: non-trivial but nothing fired
        any_search_type = is_personal or is_transactional or is_research or is_discussion
        is_ambiguous = not is_skip and not any_search_type and not show_weather and not show_stock and not show_calc

        # 5. Standalone follow-up: splice in last user message from history if available
        standalone = q
        if chat_history:
            last_user = next(
                (m["content"] for m in reversed(chat_history) if m.get("role") == "user"),
                None,
            )
            if last_user and last_user.strip().lower() != q.lower():
                # Re-contextualise short follow-up queries
                if len(tokens) <= 4:
                    standalone = f"{last_user}. {q}"

        classification = SearchClassification(
            skipSearch=is_skip,
            personalSearch=is_personal,
            transactionalSearch=is_transactional,
            researchSearch=is_research,
            discussionSearch=is_discussion,
            ambiguousSearch=is_ambiguous,
            showWeatherWidget=show_weather,
            showStockWidget=show_stock,
            showCalculationWidget=show_calc,
        )

        logger.debug(
            "query_classified",
            query=q[:80],
            skip=is_skip,
            personal=is_personal,
            transactional=is_transactional,
            research=is_research,
            discussion=is_discussion,
            ambiguous=is_ambiguous,
            weather=show_weather,
            stock=show_stock,
            calc=show_calc,
        )

        return ClassifierResult(classification=classification, standaloneFollowUp=standalone)


# ── AnsweringEngine ───────────────────────────────────────────────────────────

WRITER_PROMPT = """Answer the user query based on the provided search results.
Maintain a helpful, objective tone. Cite sources by index [1], [2], etc.
"""


class AnsweringEngine:
    """Butler's query-classification and web-answering pipeline.

    Depends on ISearchAdapter — any adapter (SearxNG, Brave, mock) can be injected.
    """

    def __init__(self, search_adapter: ISearchAdapter, llm_runtime: Any = None) -> None:
        self._search = search_adapter
        self._llm = llm_runtime
        self._classifier = QueryClassifier()

    async def classify(
        self, query: str, chat_history: list[dict[str, str]] | None = None
    ) -> ClassifierResult:
        """Classify the search intent using the keyword heuristic classifier."""
        return self._classifier.classify(query, chat_history or [])

    async def answer(
        self, query: str, chat_history: list[dict[str, str]] | None = None
    ) -> AnsweringEngineResult:
        """Execute the full answering pipeline: classify → search → generate."""
        history = chat_history or []

        # 1. Classify
        classification_result = await self.classify(query, history)
        standalone_query = classification_result.standaloneFollowUp
        prefs = classification_result.classification

        # 2. Search (if not skipping)
        sources: list[SearchResult] = []
        if not prefs.skipSearch:
            categories: list[str] = ["general"]
            if getattr(prefs, "researchSearch", False):
                categories.append("science")
            if getattr(prefs, "discussionSearch", False):
                categories.append("social media")

            try:
                raw_results = await self._search.search(standalone_query, categories=categories)
                sources = [SearchResult(**r) for r in raw_results[:8]]
            except Exception as exc:
                logger.warning("answering_engine.search_failed", query=standalone_query[:80], error=str(exc))

        # 3. Generate answer
        if sources:
            source_blocks = "\n\n".join(
                f"[{i + 1}] {s.url}\nTitle: {getattr(s, 'title', '')}\n{s.content}"
                for i, s in enumerate(sources[:5])
            )
            answer_text = (
                f"Based on my research about '{standalone_query}':\n\n"
                f"Sources reviewed: {len(sources)}\n\n"
                f"{source_blocks[:2000]}"
            )
        else:
            answer_text = (
                f"I couldn't find specific current information about '{standalone_query}'. "
                "Based on my general knowledge: I can help with this topic if you "
                "provide more context or ask a more specific question."
            )

        # 4. Widget signals
        widgets: list[dict] = []
        if getattr(prefs, "showWeatherWidget", False):
            widgets.append({"type": "weather", "query": standalone_query})
        if getattr(prefs, "showStockWidget", False):
            widgets.append({"type": "stock", "query": standalone_query})
        if getattr(prefs, "showCalculationWidget", False):
            widgets.append({"type": "calculator", "query": standalone_query})

        logger.info(
            "answering_engine.complete",
            query=query[:80],
            source_count=len(sources),
            widgets=len(widgets),
        )

        return AnsweringEngineResult(
            answer=answer_text,
            sources=sources,
            classification=prefs,
            widgets=widgets,
        )
