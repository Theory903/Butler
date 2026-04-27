"""ButlerWebSearchProvider — production sovereign web search layer.

Design goals:
- Butler owns query shaping, result normalization, reranking, and citation packaging
- Provider adapters isolate external API quirks
- Credentials injected via a resolver
- Shared HTTP connection pooling for high-throughput concurrency
- Graceful degradation with explicit failure logging
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx
import structlog

from services.security.safe_request import SafeRequestClient

logger = structlog.get_logger(__name__)

# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------

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
    error: str | None = None


# -----------------------------------------------------------------------------
# Protocols & Configuration
# -----------------------------------------------------------------------------

class SearchBackend(Protocol):
    """Contract for raw provider backends."""
    async def search(self, query: str, max_results: int) -> list[RawSearchResult]:
        """Return raw provider results."""


class CredentialResolver(Protocol):
    """Resolve provider credentials/config for Butler search backends."""
    def get(self, key: str, default: str = "") -> str:
        """Return a credential/config value."""


class EnvCredentialResolver:
    """Transitional environment-based resolver."""
    def get(self, key: str, default: str = "") -> str:
        return os.environ.get(key, default)


class QueryRewritePolicy:
    """Small policy layer for mode-aware query shaping."""

    _MODE_SUFFIXES: dict[str, str] = {
        "news": "site:reuters.com OR site:bbc.com OR site:apnews.com",
        "current_events": "site:reuters.com OR site:bbc.com OR site:apnews.com",
        "academic": "site:arxiv.org OR site:scholar.google.com",
        "technical": "site:docs.python.org OR site:github.com OR site:stackoverflow.com",
    }

    @classmethod
    def rewrite(cls, query: str, mode: str) -> str:
        trimmed = query.strip()
        if not trimmed:
            return trimmed
            
        suffix = cls._MODE_SUFFIXES.get(mode.strip().lower())
        # Avoid appending suffix if user already provided advanced operators
        if suffix and "site:" not in trimmed.lower():
            return f"{trimmed} {suffix}"
        return trimmed


# -----------------------------------------------------------------------------
# HTTP Backend Infrastructure
# -----------------------------------------------------------------------------

class _HTTPBackendBase:
    """Shared HTTP backend utilities featuring persistent connection pooling."""

    # Class-level client for connection pooling across all provider instances
    _shared_client: httpx.AsyncClient | None = None

    def __init__(self, *, timeout_s: float = 10.0, tenant_id: str | None = None) -> None:
        self._timeout_s = timeout_s
        self._tenant_id = tenant_id
        self._safe_client = SafeRequestClient(timeout=httpx.Timeout(timeout_s)) if tenant_id else None

    @classmethod
    def _get_client(cls, timeout_s: float) -> httpx.AsyncClient:
        """Lazy initialization of the shared async client."""
        if cls._shared_client is None or cls._shared_client.is_closed:
            transport = httpx.AsyncHTTPTransport(retries=1, limits=httpx.Limits(max_keepalive_connections=50))
            cls._shared_client = httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_s),
                transport=transport,
                follow_redirects=True
            )
        return cls._shared_client

    async def _execute_request(self, method: str, url: str, **kwargs) -> dict[str, Any]:
        """Centralized request execution with proper error bubbling."""
        try:
            if self._safe_client and self._tenant_id:
                # Assuming SafeRequestClient matches httpx signature closely
                response = await getattr(self._safe_client, method.lower())(url, tenant_id=self._tenant_id, **kwargs)
            else:
                client = self._get_client(self._timeout_s)
                response = await client.request(method, url, **kwargs)

            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Expected JSON object response")
            return data

        except httpx.HTTPStatusError as e:
            logger.error("search_provider_http_error", url=url, status=e.response.status_code, body=e.response.text)
            raise
        except (httpx.RequestError, ValueError) as e:
            logger.error("search_provider_network_error", url=url, error=str(e))
            raise

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
            
        text = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            # Fallback for non-standard ISO formats common in search APIs
            try:
                from dateutil import parser
                return parser.isoparse(text)
            except ImportError:
                return None


# -----------------------------------------------------------------------------
# Provider Implementations
# -----------------------------------------------------------------------------

class _SearXNGProvider(_HTTPBackendBase):
    """SearXNG backend."""

    def __init__(self, base_url: str, tenant_id: str | None = None) -> None:
        super().__init__(tenant_id=tenant_id)
        self._base_url = base_url.rstrip("/")

    async def search(self, query: str, max_results: int = 5) -> list[RawSearchResult]:
        if not self._base_url:
            raise ValueError("SearXNG base URL is missing.")

        data = await self._execute_request("GET", f"{self._base_url}/search", params={"q": query, "format": "json"})
        
        results: list[RawSearchResult] = []
        for item in data.get("results", [])[:max_results]:
            url, title = str(item.get("url", "")).strip(), str(item.get("title", "")).strip()
            if not url or not title:
                continue

            results.append(
                RawSearchResult(
                    url=url,
                    title=title,
                    snippet=(item.get("content") or "")[:2000],
                    published_date=self._parse_datetime(item.get("publishedDate") or item.get("published_date")),
                    score=float(item.get("score", 0.6) or 0.6),
                )
            )
        return results


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
    def from_env(cls, *, credential_resolver: CredentialResolver | None = None) -> ButlerWebSearchProvider:
        resolver = credential_resolver or EnvCredentialResolver()
        provider = resolver.get("BUTLER_SEARCH_PROVIDER", "searxng").strip().lower()

        # Simplified for brevity. You can register Tavily/Firecrawl similarly.
        if provider == "searxng":
            backend = _SearXNGProvider(resolver.get("SEARXNG_URL"))
        else:
            raise NotImplementedError(f"Provider {provider} not fully initialized in registry.")

        logger.info("search_provider_init", provider=provider)

        return cls(
            backend=backend,
            provider_name=provider,
            max_results=int(resolver.get("BUTLER_SEARCH_MAX_RESULTS", cls._DEFAULT_MAX_RESULTS)),
        )

    async def search(self, query: str, mode: str = "general", max_results: int | None = None) -> EvidencePack:
        """Execute provider search and return Butler-owned evidence packaging."""
        started_at = time.monotonic()
        effective_max_results = min(max_results or self._max_results, self._max_results)
        rewritten_query = self._rewrite_policy.rewrite(query, mode)
        
        error_msg = None
        raw_results = []
        
        try:
            raw_results = await self._backend.search(query=rewritten_query, max_results=effective_max_results)
        except Exception as e:
            error_msg = f"Search failed: {type(e).__name__}"
            logger.warning("search_provider_execution_failed", provider=self._provider_name, error=str(e))

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
            has_error=bool(error_msg)
        )

        return EvidencePack(
            query=query,
            mode=mode,
            results=evidence,
            citations=citations,
            provider=self._provider_name,
            latency_ms=latency_ms,
            result_count=len(evidence),
            error=error_msg
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

        return [
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
            for index, item in enumerate(evidence, start=1)
        ]

    @staticmethod
    def _compute_freshness_score(published_date: datetime | None, now: datetime) -> float:
        if published_date is None:
            return 0.5

        dt = published_date.replace(tzinfo=UTC) if published_date.tzinfo is None else published_date
        age_days = max(0, (now - dt).days)
        return max(0.0, 1.0 - (age_days / 90.0))