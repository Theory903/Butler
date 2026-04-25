"""Search Providers — Butler production search adapter layer.

Providers covered:
- SearXNG
- Serper
- Firecrawl Search
- Google Custom Search JSON API (legacy/optional)

Design goals:
- typed, normalized search results
- provider-specific quirks isolated in adapters
- configurable provider selection
- no route/business logic leakage into adapters
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field

from services.security.safe_request import SafeRequestClient

logger = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)


class SearchProviderConfigurationError(RuntimeError):
    """Raised when a search provider is missing required configuration."""


class SearchResultItem(BaseModel):
    """Normalized search result item."""

    model_config = ConfigDict(extra="forbid")

    title: str = ""
    url: str
    snippet: str = ""
    source: str
    score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Normalized search response."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    query: str
    results: list[SearchResultItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """Typed provider-agnostic search request."""

    query: str
    limit: int = 10
    language: str | None = None
    country: str | None = None
    safe_search: bool | None = None
    include_full_content: bool = False


class BaseSearchProvider:
    """Shared HTTP-backed search provider utilities."""

    provider_name: str = "search"

    def __init__(
        self, *, timeout: httpx.Timeout = _DEFAULT_TIMEOUT, tenant_id: str | None = None
    ) -> None:
        self.tenant_id = tenant_id or "default"
        self._client = httpx.AsyncClient(timeout=timeout)
        self._safe_client = SafeRequestClient(timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()
        await self._safe_client.close()

    def _require_value(self, value: str | None, label: str) -> str:
        if not value or not value.strip():
            raise SearchProviderConfigurationError(
                f"{self.provider_name} {label} is not configured"
            )
        return value.strip()

    def _normalize_limit(self, limit: int) -> int:
        return max(1, min(limit, 20))

    def _result(
        self,
        *,
        title: str,
        url: str,
        snippet: str = "",
        score: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> SearchResultItem:
        return SearchResultItem(
            title=title or "",
            url=url,
            snippet=snippet or "",
            source=self.provider_name,
            score=score,
            metadata=metadata or {},
        )

    async def search(self, request: SearchRequest) -> SearchResponse:
        raise NotImplementedError


class SearXNGProvider(BaseSearchProvider):
    """Self-hosted SearXNG provider."""

    provider_name = "searxng"

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: httpx.Timeout = _DEFAULT_TIMEOUT,
        tenant_id: str | None = None,
    ) -> None:
        super().__init__(timeout=timeout, tenant_id=tenant_id)
        self._base_url = (base_url or os.environ.get("SEARXNG_URL") or "").rstrip("/")

    async def search(self, request: SearchRequest) -> SearchResponse:
        base_url = self._require_value(self._base_url, "base_url")
        params: dict[str, Any] = {
            "q": request.query,
            "format": "json",
            "pageno": 1,
        }

        if request.language:
            params["language"] = request.language
        if request.safe_search is not None:
            params["safesearch"] = 1 if request.safe_search else 0

        if self._safe_client and self.tenant_id:
            response = await self._safe_client.get(
                f"{base_url}/search", self.tenant_id, params=params
            )
        else:
            response = await self._client.get(f"{base_url}/search", params=params)
        response.raise_for_status()
        data = response.json()

        results: list[SearchResultItem] = []
        for item in data.get("results", [])[: self._normalize_limit(request.limit)]:
            url = item.get("url")
            if not url:
                continue
            results.append(
                self._result(
                    title=item.get("title", ""),
                    url=url,
                    snippet=item.get("content", ""),
                    metadata={
                        "engine": item.get("engine"),
                        "category": item.get("category"),
                    },
                )
            )

        return SearchResponse(
            provider=self.provider_name,
            query=request.query,
            results=results,
            metadata={
                "number_of_results": len(results),
                "answers": data.get("answers", []),
                "suggestions": data.get("suggestions", []),
            },
        )


class SerperProvider(BaseSearchProvider):
    """Serper Google Search provider."""

    provider_name = "serper"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://google.serper.dev/search",
        *,
        timeout: httpx.Timeout = _DEFAULT_TIMEOUT,
        tenant_id: str | None = None,
    ) -> None:
        super().__init__(timeout=timeout, tenant_id=tenant_id)
        self._api_key = api_key or os.environ.get("SERPER_API_KEY")
        self._base_url = base_url

    async def search(self, request: SearchRequest) -> SearchResponse:
        api_key = self._require_value(self._api_key, "api key")
        payload: dict[str, Any] = {
            "q": request.query,
            "num": self._normalize_limit(request.limit),
        }
        if request.language:
            payload["hl"] = request.language
        if request.country:
            payload["gl"] = request.country

        headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        }

        if self._safe_client and self.tenant_id:
            response = await self._safe_client.post(
                self._base_url, self.tenant_id, json=payload, headers=headers
            )
        else:
            response = await self._client.post(self._base_url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        results: list[SearchResultItem] = []

        answer_box = data.get("answerBox")
        if isinstance(answer_box, dict):
            answer_url = answer_box.get("link")
            if answer_url:
                results.append(
                    self._result(
                        title=answer_box.get("title", "Answer"),
                        url=answer_url,
                        snippet=answer_box.get("answer", "") or answer_box.get("snippet", ""),
                        score=1.0,
                        metadata={"kind": "answer_box"},
                    )
                )

        for item in data.get("organic", [])[: self._normalize_limit(request.limit)]:
            url = item.get("link")
            if not url:
                continue
            results.append(
                self._result(
                    title=item.get("title", ""),
                    url=url,
                    snippet=item.get("snippet", ""),
                    metadata={
                        "position": item.get("position"),
                        "date": item.get("date"),
                    },
                )
            )

        return SearchResponse(
            provider=self.provider_name,
            query=request.query,
            results=results[: self._normalize_limit(request.limit)],
            metadata={
                "knowledge_graph": data.get("knowledgeGraph"),
                "people_also_ask": data.get("peopleAlsoAsk", []),
            },
        )


class FirecrawlSearchProvider(BaseSearchProvider):
    """Firecrawl search provider.

    Can optionally request scraped full content in the same search call.
    """

    provider_name = "firecrawl"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.firecrawl.dev/v2/search",
        *,
        timeout: httpx.Timeout = _DEFAULT_TIMEOUT,
        tenant_id: str | None = None,
    ) -> None:
        super().__init__(timeout=timeout, tenant_id=tenant_id)
        self._api_key = api_key or os.environ.get("FIRECRAWL_API_KEY")
        self._base_url = base_url

    async def search(self, request: SearchRequest) -> SearchResponse:
        api_key = self._require_value(self._api_key, "api key")

        payload: dict[str, Any] = {
            "query": request.query,
            "limit": self._normalize_limit(request.limit),
        }

        if request.include_full_content:
            payload["scrapeOptions"] = {
                "formats": [{"type": "markdown"}],
            }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        if self._safe_client and self.tenant_id:
            response = await self._safe_client.post(
                self._base_url, self.tenant_id, json=payload, headers=headers
            )
        else:
            response = await self._client.post(self._base_url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        raw_results = data.get("data", []) or data.get("results", [])
        results: list[SearchResultItem] = []

        for item in raw_results[: self._normalize_limit(request.limit)]:
            url = item.get("url")
            if not url:
                continue
            results.append(
                self._result(
                    title=item.get("title", ""),
                    url=url,
                    snippet=item.get("description", "") or item.get("markdown", ""),
                    metadata={
                        "markdown": item.get("markdown"),
                        "html": item.get("html"),
                    },
                )
            )

        return SearchResponse(
            provider=self.provider_name,
            query=request.query,
            results=results,
            metadata={
                "include_full_content": request.include_full_content,
            },
        )


class GoogleCustomSearchProvider(BaseSearchProvider):
    """Google Custom Search JSON API provider.

    Keep this optional. It is still usable, but it should not be Butler's long-term default.
    """

    provider_name = "google_cse"

    def __init__(
        self,
        api_key: str | None = None,
        cx: str | None = None,
        base_url: str = "https://customsearch.googleapis.com/customsearch/v1",
        *,
        timeout: httpx.Timeout = _DEFAULT_TIMEOUT,
        tenant_id: str | None = None,
    ) -> None:
        super().__init__(timeout=timeout, tenant_id=tenant_id)
        self._api_key = api_key or os.environ.get("GOOGLE_CUSTOM_SEARCH_API_KEY")
        self._cx = cx or os.environ.get("GOOGLE_CUSTOM_SEARCH_CX")
        self._base_url = base_url

    async def search(self, request: SearchRequest) -> SearchResponse:
        api_key = self._require_value(self._api_key, "api key")
        cx = self._require_value(self._cx, "cx")

        params: dict[str, Any] = {
            "key": api_key,
            "cx": cx,
            "q": request.query,
            "num": min(self._normalize_limit(request.limit), 10),
        }
        if request.language:
            params["lr"] = f"lang_{request.language}"
        if request.country:
            params["gl"] = request.country
        if request.safe_search is not None:
            params["safe"] = "active" if request.safe_search else "off"

        if self._safe_client and self.tenant_id:
            response = await self._safe_client.get(
                self._base_url, self.tenant_id, params=params
            )
        else:
            response = await self._client.get(self._base_url, params=params)
        response.raise_for_status()
        data = response.json()

        results: list[SearchResultItem] = []
        for item in data.get("items", [])[: self._normalize_limit(request.limit)]:
            url = item.get("link")
            if not url:
                continue
            results.append(
                self._result(
                    title=item.get("title", ""),
                    url=url,
                    snippet=item.get("snippet", ""),
                    metadata={
                        "displayLink": item.get("displayLink"),
                        "mime": item.get("mime"),
                    },
                )
            )

        return SearchResponse(
            provider=self.provider_name,
            query=request.query,
            results=results,
            metadata={
                "search_information": data.get("searchInformation", {}),
            },
        )


class SearchProviderFactory:
    """Simple registry-based search provider factory."""

    _instances: dict[str, BaseSearchProvider] = {}
    _providers = {
        "searxng": SearXNGProvider,
        "serper": SerperProvider,
        "firecrawl": FirecrawlSearchProvider,
        "google_cse": GoogleCustomSearchProvider,
    }

    @classmethod
    def get_provider(cls, provider_type: str) -> BaseSearchProvider:
        key = provider_type.strip().lower()
        if key in cls._instances:
            return cls._instances[key]

        provider_class = cls._providers.get(key)
        if provider_class is None:
            raise ValueError(f"Unsupported search provider: {provider_type}")

        instance = provider_class()
        cls._instances[key] = instance
        return instance

    @classmethod
    def list_provider_types(cls) -> Sequence[str]:
        return tuple(cls._providers.keys())
