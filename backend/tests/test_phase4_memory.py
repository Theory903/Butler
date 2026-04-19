"""Phase 4 — Memory Transplant tests.

Tests ButlerMemoryStore (policy dispatch + PII gate + tier routing),
TurboQuantColdStore (index, recall, persist/load, simulated mode),
and ButlerSessionStore (append_turn, get_context, flush_to_long_term).

All fully mocked — no real Redis, no DB, no pyturboquant, no network.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import uuid
import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch, call

from domain.memory.write_policy import (
    MemoryWritePolicy,
    MemoryWriteRequest,
    StorageTier,
)
from services.memory.turboquant_store import TurboQuantColdStore, _hash_to_vector
from services.memory.memory_store import ButlerMemoryStore
from services.memory.session_store import ButlerSessionStore


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.lrange = AsyncMock(return_value=[])
    pipe = MagicMock()
    pipe.lpush = MagicMock(return_value=pipe)
    pipe.ltrim = MagicMock(return_value=pipe)
    pipe.expire = MagicMock(return_value=pipe)
    pipe.execute = AsyncMock(return_value=[1, True, True])
    redis.pipeline = MagicMock(return_value=pipe)
    return redis


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def _make_cold_store(dim: int = 8) -> TurboQuantColdStore:
    return TurboQuantColdStore(dim=dim)


def _make_memory_store(redis=None, db=None, cold=None) -> ButlerMemoryStore:
    return ButlerMemoryStore(
        db=db or _make_db(),
        redis=redis or _make_redis(),
        cold_store=cold or _make_cold_store(),
    )


def _req(**kwargs) -> MemoryWriteRequest:
    defaults = dict(
        memory_type="episode",
        content="Test memory content",
        account_id="00000000-0000-0000-0000-000000000001",
        session_id="00000000-0000-0000-0000-000000000002",
        importance=0.5,
        age_days=0.0,
        has_pii=False,
        provenance="conversation",
        metadata={},
    )
    defaults.update(kwargs)
    return MemoryWriteRequest(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# Test 14: TurboQuantColdStore — simulated mode
# ─────────────────────────────────────────────────────────────────────────────

class TestTurboQuantColdStore:

    def test_add_sync_increases_size(self):
        store = _make_cold_store()
        assert store.size == 0
        store.index("id1", [0.1]*8, {"content": "hello world", "account_id": "00000000-0000-0000-0000-000000000001"})
        assert store.size == 1

    def test_search_returns_results(self):
        store = _make_cold_store()
        store.index("id1", [0.1]*8, {"content": "python", "account_id": "00000000-0000-0000-0000-000000000001"})
        results = asyncio.run(store.recall("00000000-0000-0000-0000-000000000001", "python"))
        assert len(results) == 1

    def test_stats_returns_dict(self):
        store = _make_cold_store(dim=64)
        stats = store.stats()
        assert stats["dim"] == 64
        assert "size" in stats


# ─────────────────────────────────────────────────────────────────────────────
# Test 15: ButlerMemoryStore — tier routing and PII gate
# ─────────────────────────────────────────────────────────────────────────────

class TestButlerMemoryStore:

    def test_session_message_writes_hot(self):
        redis = _make_redis()
        store = _make_memory_store(redis=redis)
        result = asyncio.run(store.write(_req(memory_type="session_message")))
        assert result.success
        assert StorageTier.HOT in result.tiers_written

    def test_pii_blocked_from_cold(self):
        cold = MagicMock()
        store = _make_memory_store(cold=cold)
        result = asyncio.run(store.write(_req(
            memory_type="episode",
            age_days=45,
            has_pii=True,
        )))
        assert result.success
        assert StorageTier.COLD not in result.tiers_written
        cold.index.assert_not_called()

    @patch("services.ml.embeddings.EmbeddingService.embed", new_callable=AsyncMock)
    def test_non_pii_cold_allowed(self, mock_embed):
        mock_embed.return_value = [0.1]*1536
        cold = MagicMock()
        store = _make_memory_store(cold=cold)
        result = asyncio.run(store.write(_req(
            memory_type="episode",
            age_days=45,
            has_pii=False,
        )))
        assert result.success
        assert StorageTier.COLD in result.tiers_written
        cold.index.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Test 16: ButlerSessionStore
# ─────────────────────────────────────────────────────────────────────────────

class TestButlerSessionStore:

    def _make_store(self, redis=None, cold=None) -> ButlerSessionStore:
        r = redis or _make_redis()
        c = cold or _make_cold_store()
        mem_store = _make_memory_store(redis=r, cold=c)
        return ButlerSessionStore(
            session_id="00000000-0000-0000-0000-000000000002",
            account_id="00000000-0000-0000-0000-000000000001",
            memory_store=mem_store,
            redis=r,
            cold_store=c,
        )

    def test_append_turn_user_writes_hot(self):
        redis = _make_redis()
        store = self._make_store(redis=redis)
        asyncio.run(store.append_turn("user", "Hello Butler"))
        redis.pipeline.assert_called()

    def test_get_context_returns_context_pack(self):
        from domain.memory.contracts import ContextPack
        store = self._make_store()
        ctx = asyncio.run(store.get_context("python question"))
        assert isinstance(ctx, ContextPack)

    def test_flush_to_long_term_routes_episode(self):
        db = _make_db()
        mem_store = _make_memory_store(db=db)
        store = ButlerSessionStore(
            session_id="00000000-0000-0000-0000-000000000002",
            account_id="00000000-0000-0000-0000-000000000001",
            memory_store=mem_store,
            redis=_make_redis(),
        )
        asyncio.run(store.flush_to_long_term(
            content="User asked about Python 3.13",
            memory_type="episode",
            importance=0.7,
        ))
        db.add.assert_called()
