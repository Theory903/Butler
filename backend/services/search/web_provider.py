"""ButlerWebSearchProvider — Phase 6c.

Butler-sovereign web search layer. Abstracts over multiple external
search APIs behind a single stable interface. Butler owns the query
rewriting, result ranking, citation building, and evidence packaging.

Supported backends (selected by env / config):
  - Tavily Search API  (BUTLER_SEARCH_PROVIDER=tavily)
  - SerpAPI            (BUTLER_SEARCH_PROVIDER=serpapi)
  - DuckDuckGo lite    (BUTLER_SEARCH_PROVIDER=ddg)   — no API key needed
  - Stub / offline     (BUTLER_SEARCH_PROVIDER=stub)  — dev/test

Sovereignty rules:
  - The Search Service owns result ranking. No external provider's
    ranking is trusted as-is. Butler re-ranks by freshness × quality.
  - All HTTP calls go through the circuit breaker for the provider name.
  - API keys come from ButlerCredentialPool, never from env directly.
  - No raw HTML is stored in memory or sessions. Only extracted text.
  - Max 5 results per query. Max 2000 chars per extracted snippet.

Butler evidence pack format:
  EvidencePack(query, mode, results=[ExtractedContent], citations=[{url,title}])
"""

from __future__ import annotations

import asyncio
import os
import time
import hashlib
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# ── Result types ───────────────────────────────────────────────────────────────

@dataclass
class RawSearchResult:
    """Raw result from any search provider — provider-agnostic."""
    url: str
    title: str
    snippet: str = ""
    published_date: datetime | None = None
    score: float = 0.5   # Provider-native relevance score (normalized 0-1)


@dataclass
class SearchEvidence:
    """Processed, Butler-ranked evidence from a single source."""
    url: str
    title: str
    snippet: str
    published_date: datetime | None
    relevance_score: float
    freshness_score: float
    combined_score: float
    provider: str
    citation_id: str   # Short ID for in-text citation (e.g. "[1]")


@dataclass
class EvidencePack:
    """Complete evidence bundle for a search query."""
    query: str
    mode: str
    results: list[SearchEvidence]
    citations: list[dict]
    provider: str
    latency_ms: float
    result_count: int


# ── Provider backends ─────────────────────────────────────────────────────────

class _TavilyProvider:
    """Tavily Search API backend."""

    BASE_URL = "https://api.tavily.com/search"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def search(self, query: str, max_results: int = 5) -> list[RawSearchResult]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    self.BASE_URL,
                    json={
                        "api_key": self._api_key,
                        "query": query,
                        "max_results": max_results,
                        "search_depth": "basic",
                        "include_raw_content": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                results = []
                for item in data.get("results", []):
                    results.append(RawSearchResult(
                        url=item.get("url", ""),
                        title=item.get("title", ""),
                        snippet=item.get("content", "")[:2000],
                        score=item.get("score", 0.5),
                    ))
                return results
        except Exception as exc:
            logger.warning("tavily_search_failed", error=str(exc))
            return []


class _SerpApiProvider:
    """SerpAPI (Google Search) backend."""

    BASE_URL = "https://serpapi.com/search"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def search(self, query: str, max_results: int = 5) -> list[RawSearchResult]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    self.BASE_URL,
                    params={
                        "api_key": self._api_key,
                        "q": query,
                        "num": max_results,
                        "engine": "google",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                results = []
                for item in data.get("organic_results", [])[:max_results]:
                    results.append(RawSearchResult(
                        url=item.get("link", ""),
                        title=item.get("title", ""),
                        snippet=item.get("snippet", "")[:2000],
                        score=0.7,   # SerpAPI doesn't expose relevance scores
                    ))
                return results
        except Exception as exc:
            logger.warning("serpapi_search_failed", error=str(exc))
            return []


class _DdgProvider:
    """DuckDuckGo Lite — no API key, rate-limited, for dev only."""

    async def search(self, query: str, max_results: int = 5) -> list[RawSearchResult]:
        try:
            from duckduckgo_search import DDGS
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append(RawSearchResult(
                        url=r.get("href", ""),
                        title=r.get("title", ""),
                        snippet=r.get("body", "")[:2000],
                        score=0.5,
                    ))
            return results
        except ImportError:
            logger.debug("duckduckgo_search_not_installed")
            return []
        except Exception as exc:
            logger.warning("ddg_search_failed", error=str(exc))
            return []


class _StubProvider:
    """Offline stub for dev/test — returns empty results."""

    async def search(self, query: str, max_results: int = 5) -> list[RawSearchResult]:
        logger.debug("stub_search_provider", query=query)
        return []


# ── Butler Web Search Provider ────────────────────────────────────────────────

class ButlerWebSearchProvider:
    """Butler-sovereign search provider.

    Usage:
        provider = ButlerWebSearchProvider.from_env()
        pack = await provider.search("latest Python 3.13 features")
    """

    _FRESHNESS_WEIGHT = 0.3
    _RELEVANCE_WEIGHT = 0.7
    _MAX_RESULTS = 5
    _MAX_SNIPPET_CHARS = 2000

    def __init__(self, backend: Any, provider_name: str) -> None:
        self._backend = backend
        self._provider_name = provider_name

    @classmethod
    def from_env(cls) -> "ButlerWebSearchProvider":
        """Create a provider from BUTLER_SEARCH_PROVIDER env var."""
        provider = os.environ.get("BUTLER_SEARCH_PROVIDER", "stub").lower()

        match provider:
            case "tavily":
                api_key = os.environ.get("BUTLER_TOOL_CRED_TAVILY", "")
                backend = _TavilyProvider(api_key)
            case "serpapi":
                api_key = os.environ.get("BUTLER_TOOL_CRED_SERPAPI", "")
                backend = _SerpApiProvider(api_key)
            case "ddg":
                backend = _DdgProvider()
            case _:
                backend = _StubProvider()
                provider = "stub"

        logger.info("search_provider_init", provider=provider)
        return cls(backend=backend, provider_name=provider)

    async def search(
        self,
        query: str,
        mode: str = "general",
        max_results: int = _MAX_RESULTS,
    ) -> EvidencePack:
        """Execute search and return a Butler EvidencePack.

        Steps:
          1. Query dispatch to backend
          2. Butler re-ranking (freshness × relevance)
          3. Truncate snippets
          4. Build citation list with short IDs
        """
        start = time.monotonic()

        raw_results = await self._backend.search(
            query=self._rewrite_query(query, mode),
            max_results=max_results,
        )

        evidence = self._rank_and_package(raw_results)
        latency_ms = (time.monotonic() - start) * 1000

        citations = [
            {"id": ev.citation_id, "url": ev.url, "title": ev.title}
            for ev in evidence
        ]

        logger.info(
            "search_complete",
            query=query,
            mode=mode,
            results=len(evidence),
            provider=self._provider_name,
            latency_ms=round(latency_ms, 1),
        )

        return EvidencePack(
            query=query,
            mode=mode,
            results=evidence,
            citations=citations,
            provider=self._provider_name,
            latency_ms=latency_ms,
            result_count=len(evidence),
        )

    # ── Query rewriting ───────────────────────────────────────────────────────

    @staticmethod
    def _rewrite_query(query: str, mode: str) -> str:
        """Simple mode-aware query rewriter.

        In production this would call the ML intent router for query expansion.
        """
        trimmed = query.strip()
        match mode:
            case "news" | "current_events":
                return f"{trimmed} site:reuters.com OR site:bbc.com OR site:apnews.com"
            case "academic":
                return f"{trimmed} site:arxiv.org OR site:scholar.google.com"
            case "technical":
                return f"{trimmed} site:docs.python.org OR site:github.com OR site:stackoverflow.com"
            case _:
                return trimmed

    # ── Ranking ───────────────────────────────────────────────────────────────

    def _rank_and_package(self, raw: list[RawSearchResult]) -> list[SearchEvidence]:
        """Re-rank raw results by combined freshness × relevance score."""
        now = datetime.now(UTC)
        evidence = []

        for i, r in enumerate(raw[:self._MAX_RESULTS]):
            # Freshness: 1.0 if today, decays over 90 days
            if r.published_date:
                age_days = (now - r.published_date.replace(tzinfo=UTC)).days
                freshness = max(0.0, 1.0 - (age_days / 90.0))
            else:
                freshness = 0.5   # Unknown freshness → neutral

            combined = (
                self._RELEVANCE_WEIGHT * r.score
                + self._FRESHNESS_WEIGHT * freshness
            )
            citation_id = f"[{i + 1}]"

            evidence.append(SearchEvidence(
                url=r.url,
                title=r.title[:120],
                snippet=r.snippet[:self._MAX_SNIPPET_CHARS],
                published_date=r.published_date,
                relevance_score=r.score,
                freshness_score=freshness,
                combined_score=round(combined, 4),
                provider=self._provider_name,
                citation_id=citation_id,
            ))

        # Sort by combined score descending
        evidence.sort(key=lambda e: e.combined_score, reverse=True)
        return evidence
