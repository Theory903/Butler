"""ButlerWebSearchProvider — production sovereign web search layer.

Design goals:
- Butler owns query shaping, result normalization, reranking, and citation packaging
- provider adapters isolate external API quirks
- credentials are injected via a resolver, not hardcoded across logic
- no raw HTML persistence
- bounded results and snippet sizes
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx
import structlog

from infrastructure.config import settings
from services.security.safe_request import SafeRequestClient

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RawSearchResult:
    """Provider-agnostic raw search result."""

    url: str
    title: str
    snippet: str = ""
    published_date: datetime | None = None
    score: float = 0.5


@dataclass(frozen=True, slots=True)
class SearchEvidence:
    """Butler-ranked evidence item."""

    url: str
    title: str
    snippet: str
    published_date: datetime | None
    relevance_score: float
    freshness_score: float
    combined_score: float
    provider: str
    citation_id: str


@dataclass(frozen=True, slots=True)
class EvidencePack:
    """Final evidence bundle."""

    query: str
    mode: str
    results: list[SearchEvidence]
    citations: list[dict[str, Any]]
    provider: str
    latency_ms: float
    result_count: int


class SearchBackend(Protocol):
    """Contract for raw provider backends."""

    async def search(self, query: str, max_results: int) -> list[RawSearchResult]:
        """Return raw provider results."""


class CredentialResolver(Protocol):
    """Resolve provider credentials/config for Butler search backends."""

    def get(self, key: str, default: str = "") -> str:
        """Return a credential/config value."""


class EnvCredentialResolver:
    """Transitional environment-based resolver.

    Keep this only as a default adapter. Butler can later swap in a real
    credential pool without changing search-provider logic.
    """

    def get(self, key: str, default: str = "") -> str:
        return os.environ.get(key, default)


class QueryRewritePolicy:
    """Small policy layer for mode-aware query shaping.

    Keep this intentionally small. Rich rewriting should eventually move to
    model-driven query planning, not endless hardcoded branching.
    """

    _MODE_SUFFIXES: dict[str, str] = {
        "news": "site:reuters.com OR site:bbc.com OR site:apnews.com",
        "current_events": "site:reuters.com OR site:bbc.com OR site:apnews.com",
        "academic": "site:arxiv.org OR site:scholar.google.com",
        "technical": "site:docs.python.org OR site:github.com OR site:stackoverflow.com",
    }

    @classmethod
    def rewrite(cls, query: str, mode: str) -> str:
        trimmed = query.strip()
        suffix = cls._MODE_SUFFIXES.get(mode.strip().lower())
        if not suffix or not trimmed:
            return trimmed
        return f"{trimmed} {suffix}"


class _HTTPBackendBase:
    """Shared HTTP backend utilities."""

    def __init__(self, *, timeout_s: float = 10.0, tenant_id: str | None = None) -> None:
        self._timeout = httpx.Timeout(timeout_s)
        self._tenant_id = tenant_id
        self._safe_client = SafeRequestClient(timeout=self._timeout) if tenant_id else None

    async def _get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if self._safe_client and self._tenant_id:
            response = await self._safe_client.get(
                url, tenant_id=self._tenant_id, params=params, headers=headers
            )
        else:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
                response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Expected JSON object response")
        return data

    async def _post_json(
        self,
        url: str,
        *,
        json_body: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if self._safe_client and self._tenant_id:
            response = await self._safe_client.post(
                url, tenant_id=self._tenant_id, json=json_body, headers=headers
            )
        else:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
                response = await client.post(url, json=json_body, headers=headers)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Expected JSON object response")
        return data

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None

        text = value.strip()
        if not text:
            return None

        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None


class _TavilyProvider(_HTTPBackendBase):
    """Tavily backend."""

    BASE_URL = "https://api.tavily.com/search"

    def __init__(self, api_key: str, tenant_id: str | None = None) -> None:
        super().__init__(tenant_id=tenant_id)
        self._api_key = api_key

    async def search(self, query: str, max_results: int = 5) -> list[RawSearchResult]:
        if not self._api_key.strip():
            logger.warning("tavily_search_skipped_missing_api_key")
            return []

        try:
            data = await self._post_json(
                self.BASE_URL,
                json_body={
                    "api_key": self._api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                    "include_raw_content": False,
                    "include_answer": False,
                },
            )
            results: list[RawSearchResult] = []
            for item in data.get("results", []):
                url = str(item.get("url", "")).strip()
                title = str(item.get("title", "")).strip()
                if not url or not title:
                    continue

                results.append(
                    RawSearchResult(
                        url=url,
                        title=title,
                        snippet=(item.get("content") or "")[:2000],
                        published_date=self._parse_datetime(item.get("published_date")),
                        score=float(item.get("score", 0.5) or 0.5),
                    )
                )
            return results
        except Exception as exc:
            logger.warning("tavily_search_failed", error=str(exc))
            return []


class _SerpApiProvider(_HTTPBackendBase):
    """SerpApi backend."""

    BASE_URL = "https://serpapi.com/search"

    def __init__(self, api_key: str, tenant_id: str | None = None) -> None:
        super().__init__(tenant_id=tenant_id)
        self._api_key = api_key

    async def search(self, query: str, max_results: int = 5) -> list[RawSearchResult]:
        if not self._api_key.strip():
            logger.warning("serpapi_search_skipped_missing_api_key")
            return []

        try:
            data = await self._get_json(
                self.BASE_URL,
                params={
                    "api_key": self._api_key,
                    "q": query,
                    "num": max_results,
                    "engine": "google",
                },
            )
            results: list[RawSearchResult] = []
            for item in data.get("organic_results", [])[:max_results]:
                url = str(item.get("link", "")).strip()
                title = str(item.get("title", "")).strip()
                if not url or not title:
                    continue

                results.append(
                    RawSearchResult(
                        url=url,
                        title=title,
                        snippet=(item.get("snippet") or "")[:2000],
                        published_date=self._parse_datetime(
                            item.get("date") or item.get("published_date")
                        ),
                        score=0.7,
                    )
                )
            return results
        except Exception as exc:
            logger.warning("serpapi_search_failed", error=str(exc))
            return []


class _SearXNGProvider(_HTTPBackendBase):
    """SearXNG backend."""

    def __init__(self, base_url: str, tenant_id: str | None = None) -> None:
        super().__init__(tenant_id=tenant_id)
        self._base_url = base_url.rstrip("/")

    async def search(self, query: str, max_results: int = 5) -> list[RawSearchResult]:
        if not self._base_url.strip():
            logger.warning("searxng_search_skipped_missing_base_url")
            return []

        try:
            data = await self._get_json(
                f"{self._base_url}/search",
                params={
                    "q": query,
                    "format": "json",
                },
            )
            results: list[RawSearchResult] = []
            for item in data.get("results", [])[:max_results]:
                url = str(item.get("url", "")).strip()
                title = str(item.get("title", "")).strip()
                if not url or not title:
                    continue

                results.append(
                    RawSearchResult(
                        url=url,
                        title=title,
                        snippet=(item.get("content") or "")[:2000],
                        published_date=self._parse_datetime(
                            item.get("publishedDate") or item.get("published_date")
                        ),
                        score=float(item.get("score", 0.6) or 0.6),
                    )
                )
            return results
        except Exception as exc:
            logger.warning("searxng_search_failed", error=str(exc))
            return []


class _FirecrawlProvider(_HTTPBackendBase):
    """Firecrawl search backend."""

    BASE_URL = "https://api.firecrawl.dev/v2/search"

    def __init__(self, api_key: str, include_markdown: bool = False, tenant_id: str | None = None) -> None:
        super().__init__(tenant_id=tenant_id)
        self._api_key = api_key
        self._include_markdown = include_markdown

    async def search(self, query: str, max_results: int = 5) -> list[RawSearchResult]:
        if not self._api_key.strip():
            logger.warning("firecrawl_search_skipped_missing_api_key")
            return []

        body: dict[str, Any] = {
            "query": query,
            "limit": max_results,
        }
        if self._include_markdown:
            body["scrapeOptions"] = {
                "formats": [{"type": "markdown"}],
            }

        try:
            data = await self._post_json(
                self.BASE_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json_body=body,
            )
            raw_items = data.get("data", []) or data.get("results", [])
            results: list[RawSearchResult] = []
            for item in raw_items[:max_results]:
                url = str(item.get("url", "")).strip()
                title = str(item.get("title", "")).strip()
                if not url or not title:
                    continue

                snippet = (
                    item.get("description") or item.get("markdown") or item.get("summary") or ""
                )

                results.append(
                    RawSearchResult(
                        url=url,
                        title=title,
                        snippet=str(snippet)[:2000],
                        published_date=self._parse_datetime(
                            item.get("publishedDate") or item.get("published_date")
                        ),
                        score=0.65,
                    )
                )
            return results
        except Exception as exc:
            logger.warning("firecrawl_search_failed", error=str(exc))
            return []


class _DDGSProvider:
    """DDGS backend for dev/fallback usage.

    Uses the renamed `ddgs` package first, then falls back to the legacy import
    if present in older environments.
    """

    async def search(self, query: str, max_results: int = 5) -> list[RawSearchResult]:
        def _run() -> list[RawSearchResult]:
            provider_cls = None
            try:
                from ddgs import DDGS  # type: ignore

                provider_cls = DDGS
            except ImportError:
                try:
                    from duckduckgo_search import DDGS  # type: ignore

                    provider_cls = DDGS
                except ImportError:
                    return []

            results: list[RawSearchResult] = []
            with provider_cls() as ddgs:
                for item in ddgs.text(query, max_results=max_results):
                    url = str(item.get("href", "")).strip()
                    title = str(item.get("title", "")).strip()
                    if not url or not title:
                        continue

                    results.append(
                        RawSearchResult(
                            url=url,
                            title=title,
                            snippet=(item.get("body") or "")[:2000],
                            score=0.5,
                        )
                    )
            return results

        try:
            import asyncio

            return await asyncio.to_thread(_run)
        except Exception as exc:
            logger.warning("ddgs_search_failed", error=str(exc))
            return []


class _StubProvider:
    """Offline stub provider."""

    async def search(self, query: str, max_results: int = 5) -> list[RawSearchResult]:
        logger.debug("stub_search_provider", query=query, max_results=max_results)
        return []


class ButlerWebSearchProvider:
    """Butler-sovereign search provider facade."""

    _DEFAULT_MAX_RESULTS = 5
    _DEFAULT_MAX_SNIPPET_CHARS = 2000
    _DEFAULT_FRESHNESS_WEIGHT = 0.3
    _DEFAULT_RELEVANCE_WEIGHT = 0.7

    def __init__(
        self,
        *,
        backend: SearchBackend,
        provider_name: str,
        max_results: int = _DEFAULT_MAX_RESULTS,
        max_snippet_chars: int = _DEFAULT_MAX_SNIPPET_CHARS,
        freshness_weight: float = _DEFAULT_FRESHNESS_WEIGHT,
        relevance_weight: float = _DEFAULT_RELEVANCE_WEIGHT,
        rewrite_policy: type[QueryRewritePolicy] = QueryRewritePolicy,
    ) -> None:
        self._backend = backend
        self._provider_name = provider_name
        self._max_results = max(1, max_results)
        self._max_snippet_chars = max(200, max_snippet_chars)
        self._freshness_weight = max(0.0, freshness_weight)
        self._relevance_weight = max(0.0, relevance_weight)
        self._rewrite_policy = rewrite_policy

    @classmethod
    def from_env(
        cls,
        *,
        credential_resolver: CredentialResolver | None = None,
    ) -> ButlerWebSearchProvider:
        resolver = credential_resolver or EnvCredentialResolver()
        provider = (settings.BUTLER_SEARCH_PROVIDER or resolver.get("BUTLER_SEARCH_PROVIDER", "stub")).strip().lower()

        def _safe_int(key: str, default: int) -> int:
            raw = resolver.get(key, str(default)).strip()
            try:
                return int(raw)
            except ValueError:
                logger.warning("invalid_search_config_int", key=key, value=raw, default=default)
                return default

        def _safe_float(key: str, default: float) -> float:
            raw = resolver.get(key, str(default)).strip()
            try:
                return float(raw)
            except ValueError:
                logger.warning("invalid_search_config_float", key=key, value=raw, default=default)
                return default

        provider_builders: dict[str, tuple[str, Any]] = {
            "tavily": (
                "tavily",
                lambda: _TavilyProvider(settings.TAVILY_API_KEY or resolver.get("BUTLER_TOOL_CRED_TAVILY")),
            ),
            "serpapi": (
                "serpapi",
                lambda: _SerpApiProvider(resolver.get("BUTLER_TOOL_CRED_SERPAPI")),
            ),
            "searxng": (
                "searxng",
                lambda: _SearXNGProvider(settings.SEARXNG_URL or resolver.get("SEARXNG_URL")),
            ),
            "firecrawl": (
                "firecrawl",
                lambda: _FirecrawlProvider(
                    settings.FIRECRAWL_API_KEY or resolver.get("FIRECRAWL_API_KEY"),
                    include_markdown=resolver.get("FIRECRAWL_INCLUDE_MARKDOWN", "false")
                    .strip()
                    .lower()
                    in {"1", "true", "yes"},
                ),
            ),
            "ddg": ("ddg", lambda: _DDGSProvider()),
            "stub": ("stub", lambda: _StubProvider()),
        }

        selected_name, builder = provider_builders.get(provider, provider_builders["stub"])
        backend = builder()

        logger.info("search_provider_init", provider=selected_name)

        return cls(
            backend=backend,
            provider_name=selected_name,
            max_results=_safe_int("BUTLER_SEARCH_MAX_RESULTS", cls._DEFAULT_MAX_RESULTS),
            max_snippet_chars=_safe_int(
                "BUTLER_SEARCH_MAX_SNIPPET_CHARS",
                cls._DEFAULT_MAX_SNIPPET_CHARS,
            ),
            freshness_weight=_safe_float(
                "BUTLER_SEARCH_FRESHNESS_WEIGHT",
                cls._DEFAULT_FRESHNESS_WEIGHT,
            ),
            relevance_weight=_safe_float(
                "BUTLER_SEARCH_RELEVANCE_WEIGHT",
                cls._DEFAULT_RELEVANCE_WEIGHT,
            ),
        )

    async def search(
        self,
        query: str,
        mode: str = "general",
        max_results: int | None = None,
    ) -> EvidencePack:
        """Execute provider search and return Butler-owned evidence packaging."""
        started_at = time.monotonic()
        effective_max_results = min(max_results or self._max_results, self._max_results)
        rewritten_query = self._rewrite_policy.rewrite(query, mode)

        raw_results = await self._backend.search(
            query=rewritten_query,
            max_results=effective_max_results,
        )

        evidence = self._rank_and_package(raw_results)
        latency_ms = (time.monotonic() - started_at) * 1000

        citations = [
            {
                "id": item.citation_id,
                "url": item.url,
                "title": item.title,
                "freshness": item.published_date.isoformat() if item.published_date else None,
            }
            for item in evidence
        ]

        logger.info(
            "search_complete",
            query=query,
            mode=mode,
            provider=self._provider_name,
            results=len(evidence),
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

    def _rank_and_package(self, raw_results: list[RawSearchResult]) -> list[SearchEvidence]:
        """Butler-owned reranking and evidence packaging."""
        now = datetime.now(UTC)
        evidence: list[SearchEvidence] = []

        for index, item in enumerate(raw_results[: self._max_results]):
            if not item.url.strip() or not item.title.strip():
                continue

            freshness = self._compute_freshness_score(item.published_date, now)
            combined = (self._relevance_weight * item.score) + (self._freshness_weight * freshness)

            evidence.append(
                SearchEvidence(
                    url=item.url.strip(),
                    title=item.title.strip()[:120],
                    snippet=item.snippet[: self._max_snippet_chars],
                    published_date=item.published_date,
                    relevance_score=item.score,
                    freshness_score=freshness,
                    combined_score=round(combined, 4),
                    provider=self._provider_name,
                    citation_id=f"[{index + 1}]",
                )
            )

        evidence.sort(key=lambda result: result.combined_score, reverse=True)

        reranked: list[SearchEvidence] = []
        for index, item in enumerate(evidence, start=1):
            reranked.append(
                SearchEvidence(
                    url=item.url,
                    title=item.title,
                    snippet=item.snippet,
                    published_date=item.published_date,
                    relevance_score=item.relevance_score,
                    freshness_score=item.freshness_score,
                    combined_score=item.combined_score,
                    provider=item.provider,
                    citation_id=f"[{index}]",
                )
            )
        return reranked

    @staticmethod
    def _compute_freshness_score(
        published_date: datetime | None,
        now: datetime,
    ) -> float:
        if published_date is None:
            return 0.5

        dt = published_date
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        age_days = max(0, (now - dt).days)
        return max(0.0, 1.0 - (age_days / 90.0))
