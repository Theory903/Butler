"""Web Tools — SearXNG, Webhooks."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)
_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0)


class WebScrapingRequest:
    def __init__(
        self,
        url: str,
        selectors: list[str] = None,
        extract: str = "text",
        metadata: dict = None,
    ):
        self.url = url
        self.selectors = selectors or []
        self.extract = extract
        self.metadata = metadata or {}


class WebScrapingResponse:
    def __init__(
        self,
        content: str = "",
        data: dict = None,
        links: list[str] = None,
        metadata: dict = None,
    ):
        self.content = content
        self.data = data or {}
        self.links = links or []
        self.metadata = metadata or {}


class WebhookRequest:
    def __init__(
        self,
        url: str,
        method: str = "POST",
        headers: dict = None,
        body: Any = None,
        timeout: int = 30,
        metadata: dict = None,
    ):
        self.url = url
        self.method = method.upper()
        self.headers = headers or {"Content-Type": "application/json"}
        self.body = body
        self.timeout = timeout
        self.metadata = metadata or {}


class WebhookResponse:
    def __init__(
        self,
        status_code: int = 200,
        body: Any = None,
        headers: dict = None,
        metadata: dict = None,
    ):
        self.status_code = status_code
        self.body = body
        self.headers = headers or {}
        self.metadata = metadata or {}


class BaseWebTool(ABC):
    @abstractmethod
    async def scrape(self, request: WebScrapingRequest) -> WebScrapingResponse:
        pass

    @abstractmethod
    async def webhook(self, request: WebhookRequest) -> WebhookResponse:
        pass


class SearXNGProvider(BaseWebTool):
    def __init__(
        self,
        base_url: str = "http://localhost:8888",
        api_key: str | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key or os.environ.get("SEARXNG_API_KEY")
        self._client = httpx.AsyncClient(timeout=_TIMEOUT)

    async def scrape(self, request: WebScrapingRequest) -> WebScrapingResponse:
        url = f"{self._base_url}/search"
        params = {"q": request.url, "format": "json"}
        if self._api_key:
            params["api_key"] = self._api_key
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        links = [r.get("url", "") for r in results]
        return WebScrapingResponse(
            content=json.dumps(results[:10]),
            links=links,
        )

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        url = f"{self._base_url}/search"
        params = {"q": query, "format": "json", "num_results": limit}
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])

    async def webhook(self, request: WebhookRequest) -> WebhookResponse:
        headers = dict(request.headers)
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        resp = await self._client.request(
            request.method,
            request.url,
            headers=headers,
            json=request.body,
            timeout=request.timeout,
        )
        return WebhookResponse(status_code=resp.status_code, body=resp.text)


class FirecrawlProvider(BaseWebTool):
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.firecrawl.dev",
    ):
        self._api_key = api_key or os.environ.get("FIRECRAWL_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=_TIMEOUT)

    async def scrape(self, request: WebScrapingRequest) -> WebScrapingResponse:
        url = f"{self._base_url}/v1/scrape"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {"url": request.url, "extract": request.selectors or [request.extract]}
        resp = await self._client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("data", {}).get("markdown", "")
        links = data.get("data", {}).get("links", [])
        return WebScrapingResponse(content=content, links=links)

    async def webhook(self, request: WebhookRequest) -> WebhookResponse:
        url = f"{self._base_url}/v1/webhook"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {"url": request.url, "method": request.method, "body": request.body}
        resp = await self._client.post(url, json=payload, headers=headers)
        return WebhookResponse(status_code=resp.status_code, body=resp.text)


class WebhookProvider(BaseWebTool):
    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.environ.get("WEBHOOK_API_KEY")
        self._client = httpx.AsyncClient(timeout=_TIMEOUT)

    async def scrape(self, request: WebScrapingRequest) -> WebScrapingResponse:
        resp = await self._client.get(request.url)
        resp.raise_for_status()
        content = resp.text
        return WebScrapingResponse(content=content)

    async def webhook(self, request: WebhookRequest) -> WebhookResponse:
        headers = dict(request.headers)
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        resp = await self._client.request(
            request.method,
            request.url,
            headers=headers,
            json=request.body,
            timeout=request.timeout,
        )
        return WebhookResponse(status_code=resp.status_code, body=resp.text)


class WebToolFactory:
    _instances: dict = {}

    @classmethod
    def get_provider(cls, provider_type: str):
        if provider_type in cls._instances:
            return cls._instances[provider_type]
        provider = {
            "searxng": lambda: SearXNGProvider(),
            "firecrawl": lambda: FirecrawlProvider(),
            "webhooks": lambda: WebhookProvider(),
        }.get(provider_type)()
        cls._instances[provider_type] = provider
        return provider
