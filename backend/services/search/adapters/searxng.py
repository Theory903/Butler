from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
import structlog

from domain.search.contracts import ISearchAdapter
from services.security.safe_request import SafeRequestClient

logger = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
_DEFAULT_LIMITS = httpx.Limits(max_keepalive_connections=20, max_connections=100)


class SearxNGAdapter(ISearchAdapter):
    """Adapter for a SearXNG instance.

    Notes:
    - Uses the documented `/search` JSON API.
    - Keeps one shared AsyncClient for connection pooling.
    - Returns normalized raw search dicts for the search layer.
    - Handles instances where JSON format is disabled or misconfigured.
    """

    def __init__(
        self,
        base_url: str = "http://searxng:8080",
        timeout: httpx.Timeout = _DEFAULT_TIMEOUT,
        limits: httpx.Limits = _DEFAULT_LIMITS,
        max_results_cap: int = 20,
        tenant_id: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._tenant_id = tenant_id
        self._safe_client = SafeRequestClient(timeout=timeout) if tenant_id else None
        # Fallback to direct httpx for non-tenant contexts (e.g., system-level search)
        self._client = httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "ButlerSearxNGAdapter/1.0 (compatible; Butler; +https://butler.lasmoid.ai)"
                )
            },
        )
        self._max_results_cap = max(1, max_results_cap)
        self._closed = False

    async def __aenter__(self) -> SearxNGAdapter:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def search(
        self,
        query: str,
        categories: list[str] | None = None,
        language: str | None = None,
        num_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Perform a search against SearXNG and return normalized result dicts."""
        normalized_query = query.strip()
        if not normalized_query:
            return []

        normalized_categories = [
            item.strip() for item in (categories or ["general"]) if item.strip()
        ]
        if not normalized_categories:
            normalized_categories = ["general"]

        effective_num_results = max(1, min(num_results, self._max_results_cap))

        params: dict[str, Any] = {
            "q": normalized_query,
            "format": "json",
            "categories": ",".join(normalized_categories),
        }
        if language and language.strip():
            params["language"] = language.strip()

        try:
            if self._safe_client and self._tenant_id:
                response = await self._safe_client.get(
                    f"{self._base_url}/search",
                    tenant_id=self._tenant_id,
                    params=params,
                )
            else:
                response = await self._client.get(f"{self._base_url}/search", params=params)
            response.raise_for_status()

            data = self._decode_json_response(response)
            raw_results = data.get("results", [])
            if not isinstance(raw_results, list):
                logger.warning("searxng_results_not_list", query=normalized_query)
                return []

            results = [
                self._normalize_result(item)
                for item in raw_results[:effective_num_results]
                if isinstance(item, dict) and str(item.get("url", "")).strip()
            ]

            logger.info(
                "searxng_search_success",
                query=normalized_query,
                result_count=len(results),
                categories=normalized_categories,
                language=language,
            )
            return results

        except httpx.HTTPStatusError as exc:
            logger.warning(
                "searxng_search_http_error",
                query=normalized_query,
                status_code=exc.response.status_code,
                error=str(exc),
            )
            return []
        except ValueError as exc:
            logger.warning(
                "searxng_search_invalid_json_response",
                query=normalized_query,
                error=str(exc),
            )
            return []
        except Exception as exc:
            logger.error("searxng_search_failed", query=normalized_query, error=str(exc))
            return []

    async def health_check(self) -> bool:
        """Return True if the SearXNG upstream is reachable and returns JSON."""
        try:
            if self._safe_client and self._tenant_id:
                response = await self._safe_client.get(
                    f"{self._base_url}/search",
                    tenant_id=self._tenant_id,
                    params={"q": "ping", "format": "json"},
                )
            else:
                response = await self._client.get(
                    f"{self._base_url}/search",
                    params={"q": "ping", "format": "json"},
                )
            response.raise_for_status()
            data = self._decode_json_response(response)
            return isinstance(data, dict) and "results" in data
        except Exception:
            return False

    async def close(self) -> None:
        if not self._closed:
            await self._client.aclose()
            self._closed = True

    def _decode_json_response(self, response: httpx.Response) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "").lower()

        try:
            data = response.json()
        except Exception as exc:
            raise ValueError("SearXNG response was not valid JSON") from exc

        if not isinstance(data, dict):
            raise ValueError("SearXNG JSON response was not an object")

        # Some instances may not have JSON enabled and can behave unexpectedly.
        # Keep the guard explicit instead of assuming every 200 is usable.
        if "results" not in data and "answers" not in data and "corrections" not in data:
            raise ValueError(
                f"SearXNG JSON response missing expected keys; content-type={content_type or 'unknown'}"
            )

        return data

    def _normalize_result(self, item: dict[str, Any]) -> dict[str, Any]:
        title = str(item.get("title", "")).strip()
        url = str(item.get("url", "")).strip()
        snippet = str(item.get("content", "") or item.get("snippet", "") or "").strip()

        return {
            "url": url,
            "title": title,
            "content": snippet,
            "snippet": snippet,
            "engine": str(item.get("engine", "searxng")).strip() or "searxng",
            "score": float(item.get("score", 0.0) or 0.0),
            "published_date": self._parse_date(
                item.get("publishedDate") or item.get("published_date")
            ),
            "metadata": {
                "category": item.get("category"),
                "parsed_url": item.get("parsed_url"),
            },
        }

    def _parse_date(self, date_str: str | None) -> str | None:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00")).isoformat()
        except ValueError:
            return None
