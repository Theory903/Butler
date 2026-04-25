"""Remote embedding provider.

Uses external API for embeddings.
"""

from __future__ import annotations

import httpx

import structlog

logger = structlog.get_logger(__name__)


class RemoteEmbeddingProvider:
    """Remote embedding provider using external API."""

    def __init__(
        self,
        api_url: str,
        api_key: str | None = None,
        model: str = "text-embedding-3-small",
        timeout: float = 30.0,
    ) -> None:
        self._api_url = api_url
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._client = None

    async def initialize(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)

    async def embed_one(self, text: str) -> list[float]:
        vectors = await self.embed_many([text])
        return vectors[0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        await self.initialize()

        if self._client is None:
            raise RuntimeError("HTTP client was not initialized.")

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        response = await self._client.post(
            self._api_url,
            json={"texts": texts, "model": self._model},
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("embeddings", [])

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
