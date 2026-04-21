"""Search Providers — Brave, Exa, Tavily, DuckDuckGo."""

from __future__ import annotations

import os
import json
from typing import Optional, List, Dict, Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)


class SearchResult:
    """Result of a web search."""
    
    def __init__(
        self,
        title: str,
        url: str,
        snippet: str,
        source: Optional[str] = None,
        score: Optional[float] = None,
    ):
        self.title = title
        self.url = url
        self.snippet = snippet
        self.source = source
        self.score = score


class SearchResponse:
    """Response from a search provider."""
    
    def __init__(self, results: List[SearchResult], query: str):
        self.results = results
        self.query = query


# ── Brave Search Provider ───────────────────────────────────────────────────

class BraveSearchProvider:
    """Brave Search API Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.search.brave.com/res/v1/web",
    ) -> None:
        self._api_key = api_key or os.environ.get("BRAVE_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def search(self, query: str, num_results: int = 10) -> SearchResponse:
        """Perform a web search."""
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self._api_key,
        }
        
        params = {
            "q": query,
            "count": num_results,
        }
        
        response = await self._client.get(
            f"{self._base_url}/search",
            headers=headers,
            params=params
        )
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get("web", {}).get("results", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("description", ""),
                source="brave",
            ))
        
        return SearchResponse(results=results, query=query)


# ── Exa Search Provider ────────────────────────────────────────────────────

class ExaSearchProvider:
    """Exa AI Search API Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.exa.ai/search",
    ) -> None:
        self._api_key = api_key or os.environ.get("EXA_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def search(self, query: str, num_results: int = 10) -> SearchResponse:
        """Perform a web search using Exa."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        
        payload = {
            "query": query,
            "num_results": num_results,
            "type": "auto",
        }
        
        response = await self._client.post(
            self._base_url,
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get("results", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("text", ""),
                source="exa",
                score=item.get("score"),
            ))
        
        return SearchResponse(results=results, query=query)

    async def search_contents(self, query: str, urls: List[str], num_results: int = 5) -> SearchResponse:
        """Search within specific URLs."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        
        payload = {
            "query": query,
            "urls": urls,
            "num_results": num_results,
            "type": "content",
        }
        
        response = await self._client.post(
            self._base_url,
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get("results", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("text", ""),
                source="exa",
            ))
        
        return SearchResponse(results=results, query=query)


# ── Tavily Search Provider ─────────────────────────────────────────────────

class TavilySearchProvider:
    """Tavily Search API Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.tavily.com/search",
    ) -> None:
        self._api_key = api_key or os.environ.get("TAVILY_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def search(self, query: str, num_results: int = 10) -> SearchResponse:
        """Perform a web search using Tavily."""
        headers = {
            "Content-Type": "application/json",
        }
        
        payload = {
            "api_key": self._api_key,
            "query": query,
            "max_results": num_results,
            "include_answer": True,
            "include_images": False,
            "include_raw_content": False,
        }
        
        response = await self._client.post(
            self._base_url,
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get("results", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", ""),
                source="tavily",
            ))
        
        return SearchResponse(results=results, query=query)


# ── DuckDuckGo Search Provider ────────────────────────────────────────────

class DuckDuckGoSearchProvider:
    """DuckDuckGo Search Provider (HTML/API)."""

    def __init__(
        self,
        base_url: str = "https://duckduckgo.com",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def search(self, query: str, num_results: int = 10) -> SearchResponse:
        """Perform a web search using DuckDuckGo."""
        params = {
            "q": query,
            "format": "json",
            "no_html": "1",
        }
        
        response = await self._client.get(
            f"{self._base_url}/",
            params=params
        )
        response.raise_for_status()
        
        # DuckDuckGo returns malformed JSON lines
        text = response.text
        lines = text.strip().split("\n")
        
        results = []
        count = 0
        for line in lines:
            if count >= num_results:
                break
            try:
                item = json.loads(line)
                if item.get("Result"):
                    results.append(SearchResult(
                        title=item.get("Text", ""),
                        url=item.get("URL", ""),
                        snippet=item.get("Text", ""),
                        source="duckduckgo",
                    ))
                    count += 1
            except Exception:
                continue
        
        return SearchResponse(results=results, query=query)


# ── Search Provider Factory ────────────────────────────────────────────────

class SearchProviderFactory:
    """Factory for search providers."""
    
    _instances = {}
    
    @classmethod
    def get_provider(cls, provider_type: str):
        """Return a singleton instance of the requested search provider."""
        if provider_type in cls._instances:
            return cls._instances[provider_type]
        
        provider = None
        if provider_type == "brave":
            from services.ml.providers.search import BraveSearchProvider
            provider = BraveSearchProvider()
        elif provider_type == "exa":
            from services.ml.providers.search import ExaSearchProvider
            provider = ExaSearchProvider()
        elif provider_type == "tavily":
            from services.ml.providers.search import TavilySearchProvider
            provider = TavilySearchProvider()
        elif provider_type == "duckduckgo":
            from services.ml.providers.search import DuckDuckGoSearchProvider
            provider = DuckDuckGoSearchProvider()
        else:
            raise ValueError(f"Unsupported search provider: {provider_type}")
        
        cls._instances[provider_type] = provider
        return provider