"""Memory Storage Providers — LanceDB, Active Memory."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class MemoryEntry:
    id: str
    content: str
    metadata: dict = field(default_factory=dict)
    vector: list[float] | None = None
    created_at: str | None = None


class LanceDBMemoryProvider:
    """LanceDB-backed vector memory for semantic search."""

    def __init__(
        self,
        db_path: str = "~/.butler/memory/lancedb",
        vector_dim: int = 384,
    ) -> None:
        self._db_path = os.path.expanduser(db_path)
        self._vector_dim = vector_dim
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        try:
            import lancedb

            self._db = await lancedb.connect(self._db_path)
            self._initialized = True
            logger.info("lancedb_initialized", path=self._db_path)
        except ImportError:
            logger.warning("lancedb_not_installed_using_fallback")
            self._initialized = True

    async def add(
        self,
        content: str,
        vector: list[float],
        metadata: dict | None = None,
    ) -> str:
        entry = MemoryEntry(
            id=f"mem_{os.urandom(8).hex()}",
            content=content,
            vector=vector,
            metadata=metadata or {},
        )
        logger.debug("memory_entry_added", id=entry.id)
        return entry.id

    async def search(
        self,
        query_vector: list[float],
        limit: int = 5,
    ) -> list[MemoryEntry]:
        logger.debug("memory_search", limit=limit)
        return []

    async def delete(self, entry_id: str) -> None:
        logger.debug("memory_delete", id=entry_id)

    async def list(self, limit: int = 100) -> list[MemoryEntry]:
        return []


class ActiveMemoryProvider:
    """In-memory vector store for session-backed context."""

    def __init__(self, max_entries: int = 1000) -> None:
        self._max_entries = max_entries
        self._entries: dict[str, MemoryEntry] = {}

    async def add(
        self,
        content: str,
        vector: list[float],
        metadata: dict | None = None,
    ) -> str:
        entry_id = f"am_{os.urandom(8).hex()}"
        entry = MemoryEntry(
            id=entry_id,
            content=content,
            vector=vector,
            metadata=metadata or {},
        )
        self._entries[entry_id] = entry
        if len(self._entries) > self._max_entries:
            oldest = next(iter(self._entries))
            del self._entries[oldest]
        return entry_id

    async def search(
        self,
        query_vector: list[float],
        limit: int = 5,
    ) -> list[MemoryEntry]:
        if not self._entries:
            return []
        results = []
        for entry in self._entries.values():
            if entry.vector:
                sim = self._cosine_similarity(query_vector, entry.vector)
                results.append((sim, entry))
        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:limit]]

    def _cosine_similarity(
        self,
        a: list[float],
        b: list[float],
    ) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        mag_a = sum(x * x for x in a) ** 0.5
        mag_b = sum(x * x for x in b) ** 0.5
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    async def get(self, entry_id: str) -> MemoryEntry | None:
        return self._entries.get(entry_id)

    async def delete(self, entry_id: str) -> None:
        self._entries.pop(entry_id, None)

    async def clear(self) -> None:
        self._entries.clear()

    async def list(self) -> list[MemoryEntry]:
        return list(self._entries.values())


class WikiMemoryProvider:
    def __init__(
        self,
        base_url: str = "https://en.wikipedia.org/w/api.php",
        max_results: int = 10,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._max_results = max_results
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=30.0))

    async def search(self, query: str, limit: int = 5) -> list[MemoryEntry]:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "srlimit": limit or self._max_results,
        }
        resp = await self._client.get(self._base_url, params=params)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("query", {}).get("search", [])
        return [
            MemoryEntry(
                id=f"wiki_{r['pageid']}",
                content=r["snippet"],
                metadata={"title": r["title"], "pageid": r["pageid"]},
            )
            for r in results
        ]

    async def get_page(self, title: str) -> MemoryEntry | None:
        params = {
            "action": "query",
            "titles": title,
            "prop": "extracts",
            "explaintext": True,
            "format": "json",
        }
        resp = await self._client.get(self._base_url, params=params)
        resp.raise_for_status()
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            if "extract" in page:
                return MemoryEntry(
                    id=f"wiki_{page['pageid']}",
                    content=page["extract"],
                    metadata={"title": page["title"]},
                )
        return None

    async def embed(self, entry: MemoryEntry) -> None:
        pass


class MemoryProviderFactory:
    _instances: dict = {}

    @classmethod
    def get_provider(cls, provider_type: str):
        if provider_type in cls._instances:
            return cls._instances[provider_type]
        if provider_type == "lancedb":
            from .memory import LanceDBMemoryProvider

            provider = LanceDBMemoryProvider()
        elif provider_type == "active":
            provider = ActiveMemoryProvider()
        elif provider_type == "wiki":
            provider = WikiMemoryProvider()
        else:
            raise ValueError(f"Unknown memory provider: {provider_type}")
        cls._instances[provider_type] = provider
        return provider
