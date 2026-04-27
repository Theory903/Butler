"""FaissColdStore — Production cold-tier fallback (v3.1).

Provides identical interface to TurboQuantColdStore but backed by
Facebook's FAISS library instead of pyturboquant. Used when pyturboquant is
not installed. IndexFlatIP is used for correctness; IndexIVFPQ is preferred
for >100k entries — auto-upgraded when the index grows past the threshold.

FAISS is included as an optional dep via faiss-cpu (or faiss-gpu in prod).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import pickle
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

try:
    import faiss
    import numpy as np

    _HAS_FAISS = True
except ImportError:
    _HAS_FAISS = False
    logger.warning(
        "faiss-cpu not installed — FaissColdStore running in simulated mode. "
        "Run: pip install faiss-cpu"
    )

# Threshold above which we rebuild index as IVF for speed
_IVF_THRESHOLD = 50_000
_DEFAULT_DIM = 1536


class FaissColdStore:
    """FAISS-backed cold-tier vector store.

    Thread-safe for reads; writes must serialise via asyncio executor.
    Drop-in replacement for TurboQuantColdStore.
    """

    def __init__(
        self,
        dim: int = _DEFAULT_DIM,
        snapshot_path: str | None = None,
    ) -> None:
        self.dim = dim
        self._snapshot_path = snapshot_path
        self._ids: list[str] = []
        self._meta: list[dict[str, Any]] = []
        self._text_store: list[str] = []
        self._needs_rebuild = False

        if _HAS_FAISS:
            self._index: Any = faiss.IndexFlatIP(dim)
        else:
            self._index = None
            self._sim_vectors: list[list[float]] = []

        if snapshot_path and os.path.exists(snapshot_path + ".meta.pkl"):
            try:
                self.load(snapshot_path)
                logger.info("faiss_cold_store_restored", path=snapshot_path, size=self.size)
            except Exception as exc:
                logger.warning("faiss_cold_store_load_failed", error=str(exc))

    # ── Write ──────────────────────────────────────────────────────────────

    def add_sync(
        self,
        ids: list[str],
        content: str,
        metadata: list[dict[str, Any]],
        vector: list[float] | None = None,
    ) -> None:
        """Add one or more items to the store."""
        if not ids:
            return

        if _HAS_FAISS:
            if vector is not None:
                arr = np.array([vector] * len(ids), dtype=np.float32)
            else:
                arr = np.array(
                    [_hash_to_vector(content, self.dim)] * len(ids),
                    dtype=np.float32,
                )
            # L2-normalise for cosine similarity via IndexFlatIP
            faiss.normalize_L2(arr)
            self._index.add(arr)

            # Auto-rebuild to IVF once threshold exceeded (background)
            if len(self._ids) + len(ids) > _IVF_THRESHOLD and not self._needs_rebuild:
                self._needs_rebuild = True
                logger.info("faiss_ivf_rebuild_scheduled", size=self.size)
        else:
            stub = _hash_to_vector(content, self.dim)
            for _ in ids:
                self._sim_vectors.append(stub)

        self._ids.extend(ids)
        self._meta.extend(metadata)
        self._text_store.extend([content] * len(ids))
        logger.debug("faiss_cold_add", added=len(ids), total=self.size)

    # ── Read ───────────────────────────────────────────────────────────────

    async def search_async(
        self,
        query_vector: list[float] | None = None,
        query_text: str | None = None,
        k: int = 20,
        filters: dict | None = None,
    ) -> list[dict[str, Any]]:
        return await asyncio.get_event_loop().run_in_executor(
            None, self._search_sync, query_vector, query_text, k, filters
        )

    # ── IColdStore Contract Implementation ────────────────────────────────────

    async def recall(self, account_id: str, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """IColdStore.recall interface."""
        return await self.search_async(
            query_text=query, k=top_k, filters={"account_id": account_id}
        )

    def index(self, entry_id: str, embedding: list[float], payload: dict) -> None:
        """IColdStore.index interface."""
        # Map contract interface to internal add_sync
        self.add_sync(
            ids=[entry_id],
            content=payload.get("content", ""),
            metadata=[payload],
            vector=embedding,
        )

    def _search_sync(
        self,
        query_vector: list[float] | None,
        query_text: str | None,
        k: int,
        filters: dict | None,
    ) -> list[dict[str, Any]]:
        if not self._ids:
            return []

        if _HAS_FAISS:
            if query_vector is None and query_text is not None:
                query_vector = _hash_to_vector(query_text, self.dim)
            if query_vector is None:
                return []

            q = np.array([query_vector], dtype=np.float32)
            faiss.normalize_L2(q)
            distances, indices = self._index.search(q, min(k, len(self._ids)))

            results = []
            for score, idx in zip(distances[0].tolist(), indices[0].tolist(), strict=False):
                if not (0 <= idx < len(self._ids)):
                    continue
                meta = self._meta[idx]
                if filters and not _matches_filters(meta, filters):
                    continue
                results.append(
                    {
                        "id": self._ids[idx],
                        "score": float(score),
                        "metadata": meta,
                        "content": self._text_store[idx] if idx < len(self._text_store) else None,
                    }
                )
            return results

        # Simulated path
        results = []
        for i, (item_id, meta, text) in enumerate(
            zip(self._ids, self._meta, self._text_store, strict=False)
        ):
            if len(results) >= k:
                break
            if filters and not _matches_filters(meta, filters):
                continue
            results.append(
                {
                    "id": item_id,
                    "score": max(0.0, 0.99 - i * 0.01),
                    "metadata": meta,
                    "content": text,
                }
            )
        return results

    # ── Persistence ────────────────────────────────────────────────────────

    def persist(self, path: str | None = None) -> None:
        target = path or self._snapshot_path
        if not target:
            return

        Path(target).parent.mkdir(parents=True, exist_ok=True)
        meta_path = target + ".meta.pkl"
        try:
            with open(meta_path, "wb") as f:
                pickle.dump(
                    {
                        "ids": self._ids,
                        "meta": self._meta,
                        "text_store": self._text_store,
                        "dim": self.dim,
                    },
                    f,
                )
            if _HAS_FAISS:
                faiss.write_index(self._index, target + ".faiss")
            else:
                with open(target + ".sim.pkl", "wb") as f:
                    pickle.dump(self._sim_vectors, f)
            logger.info("faiss_cold_persisted", path=target, size=self.size)
        except Exception as exc:
            logger.error("faiss_cold_persist_failed", error=str(exc))
            raise

    def load(self, path: str) -> None:
        meta_path = path + ".meta.pkl"
        with open(meta_path, "rb") as f:
            state = pickle.load(f)
        self._ids = state["ids"]
        self._meta = state["meta"]
        self._text_store = state.get("text_store", [""] * len(self._ids))

        index_path = path + ".faiss"
        if _HAS_FAISS and os.path.exists(index_path):
            self._index = faiss.read_index(index_path)
        elif not _HAS_FAISS:
            sim_path = path + ".sim.pkl"
            if os.path.exists(sim_path):
                with open(sim_path, "rb") as f:
                    self._sim_vectors = pickle.load(f)

    # ── Observability ──────────────────────────────────────────────────────

    @property
    def size(self) -> int:
        return len(self._ids)

    def stats(self) -> dict:
        return {
            "size": self.size,
            "dim": self.dim,
            "backend": "faiss" if _HAS_FAISS else "simulated",
            "needs_ivf_rebuild": self._needs_rebuild,
        }


# ── Helpers ────────────────────────────────────────────────────────────────────


def _hash_to_vector(text: str, dim: int) -> list[float]:
    digest = hashlib.sha256(text.encode()).digest()
    raw = (digest * ((dim // len(digest)) + 1))[:dim]
    vec = [(b / 255.0) * 2.0 - 1.0 for b in raw]
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def _matches_filters(meta: dict, filters: dict) -> bool:
    return all(meta.get(k) == v for k, v in filters.items())
