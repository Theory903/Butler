"""Phase 6b/6c — Realtime Dispatcher and Search Provider tests.

Tests ButlerStreamDispatcher (event mapping, Redis Stream persistence,
SSE replay, batch dispatch, durable/ephemeral split) and
ButlerWebSearchProvider (query rewriting, ranking, EvidencePack structure,
provider selection, freshness scoring, stub backend).

All fully mocked — no real Redis, no real HTTP calls.

Verifies:
  1. StreamDispatcher: stream.token → response.chunk (ephemeral, not persisted)
  2. StreamDispatcher: workflow.complete → durable RealtimeEvent (persisted)
  3. StreamDispatcher: tool.call → durable (persisted)
  4. StreamDispatcher: approval.request → durable (persisted)
  5. StreamDispatcher: error → durable (persisted)
  6. StreamDispatcher: unknown event type → skipped (no persist)
  7. StreamDispatcher: dispatch() calls manager.send_event
  8. StreamDispatcher: persist_to_stream calls xadd with string fields
  9. StreamDispatcher: replay() decodes bytes from Redis xrange
  10. StreamDispatcher: replay() returns empty on Redis error
  11. StreamDispatcher: sse_replay_stream() yields SSE-formatted lines
  12. StreamDispatcher: sse_replay_stream() ends with replay.complete
  13. StreamDispatcher: batch_dispatch sends all events
  14. WebSearchProvider: stub backend returns empty EvidencePack
  15. WebSearchProvider: _rank_and_package scores and sorts results
  16. WebSearchProvider: freshness_score = 1.0 for today's content
  17. WebSearchProvider: freshness_score decays over 90 days
  18. WebSearchProvider: freshness_score = 0.5 for unknown date
  19. WebSearchProvider: results capped at MAX_RESULTS=5
  20. WebSearchProvider: citations include id, url, title
  21. WebSearchProvider: query rewriting for "news" mode
  22. WebSearchProvider: query rewriting for "technical" mode
  23. WebSearchProvider: query rewriting for "general" mode (no transform)
  24. WebSearchProvider: combined score = 0.7*relevance + 0.3*freshness
  25. WebSearchProvider: snippet truncated at 2000 chars
  26. WebSearchProvider: EvidencePack has provider name
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from domain.events.schemas import ButlerEvent
from services.realtime.stream_dispatcher import ButlerStreamDispatcher
from services.search.web_provider import (
    ButlerWebSearchProvider,
    RawSearchResult,
    _StubProvider,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_redis(xadd_return=b"1-0", xrange_return=None) -> AsyncMock:
    redis = AsyncMock()
    redis.xadd = AsyncMock(return_value=xadd_return)
    redis.expire = AsyncMock()
    redis.xrange = AsyncMock(return_value=xrange_return or [])
    return redis


def _make_manager() -> AsyncMock:
    mgr = AsyncMock()
    mgr.send_event = AsyncMock()
    return mgr


def _dispatcher(redis=None, manager=None) -> ButlerStreamDispatcher:
    return ButlerStreamDispatcher(
        redis=redis or _make_redis(),
        manager=manager or _make_manager(),
    )


def _event(event_type: str, payload: dict | None = None) -> ButlerEvent:
    return ButlerEvent(event_type=event_type, payload=payload or {})


def _raw_result(
    url="https://example.com",
    title="Test",
    snippet="Some snippet",
    score=0.8,
    published_date=None,
) -> RawSearchResult:
    return RawSearchResult(
        url=url,
        title=title,
        snippet=snippet,
        score=score,
        published_date=published_date,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 23: ButlerStreamDispatcher
# ─────────────────────────────────────────────────────────────────────────────


class TestButlerStreamDispatcher:
    # ── Event mapping ─────────────────────────────────────────────────────────

    def test_stream_token_maps_to_response_chunk(self):
        d = _dispatcher()
        rt = d._map_to_realtime(_event("stream.token", {"content": "hello", "final": False}))
        assert rt is not None
        assert rt.event_type == "response.chunk"
        assert rt.durable is False

    def test_workflow_complete_maps_durable(self):
        d = _dispatcher()
        rt = d._map_to_realtime(
            _event("workflow.complete", {"workflow_id": "wf1", "content": "done"})
        )
        assert rt is not None
        assert rt.event_type == "workflow.complete"
        assert rt.durable is True

    def test_tool_call_maps_durable(self):
        d = _dispatcher()
        rt = d._map_to_realtime(_event("tool.call", {"tool_name": "search", "status": "done"}))
        assert rt is not None
        assert rt.event_type == "tool.call"
        assert rt.durable is True

    def test_approval_request_maps_durable(self):
        d = _dispatcher()
        rt = d._map_to_realtime(
            _event("approval.request", {"approval_id": "ap1", "description": "Allow?"})
        )
        assert rt is not None
        assert rt.event_type == "approval.request"
        assert rt.durable is True

    def test_error_event_maps_durable(self):
        d = _dispatcher()
        rt = d._map_to_realtime(
            _event("error", {"type": "internal-error", "title": "Oops", "status": 500})
        )
        assert rt is not None
        assert rt.event_type == "error"
        assert rt.durable is True

    def test_unknown_event_type_returns_none(self):
        d = _dispatcher()
        rt = d._map_to_realtime(_event("some.unknown.internal.event", {}))
        assert rt is None

    # ── Dispatch + persistence ────────────────────────────────────────────────

    def test_dispatch_calls_manager_send_event(self):
        manager = _make_manager()
        redis = _make_redis()
        d = _dispatcher(redis=redis, manager=manager)
        asyncio.run(d.dispatch(_event("workflow.complete", {"workflow_id": "wf1"}), "acct_1"))
        manager.send_event.assert_called_once()

    def test_dispatch_durable_calls_xadd(self):
        redis = _make_redis()
        d = _dispatcher(redis=redis)
        asyncio.run(d.dispatch(_event("workflow.complete", {"workflow_id": "wf1"}), "acct_1"))
        redis.xadd.assert_called_once()
        # Verify stream key
        args = redis.xadd.call_args.args
        assert "butler:events:acct_1" in args[0]

    def test_dispatch_ephemeral_does_not_call_xadd(self):
        redis = _make_redis()
        d = _dispatcher(redis=redis)
        asyncio.run(d.dispatch(_event("stream.token", {"content": "tok"}), "acct_1"))
        # xadd should NOT be called for ephemeral events
        redis.xadd.assert_not_called()

    def test_persist_stream_fields_are_strings(self):
        """All Redis Stream fields must be strings (xadd requirement)."""
        redis = _make_redis()
        d = _dispatcher(redis=redis)
        asyncio.run(d.dispatch(_event("tool.call", {"tool_name": "search"}), "acct_1"))
        _, _kwargs_or_args = redis.xadd.call_args.args, redis.xadd.call_args
        # Check the entry dict (second positional arg)
        entry = redis.xadd.call_args.args[1]
        for k, v in entry.items():
            assert isinstance(k, str), f"key {k!r} is not str"
            assert isinstance(v, str), f"value for {k!r} is not str"

    def test_dispatch_expire_called_after_xadd(self):
        redis = _make_redis()
        d = _dispatcher(redis=redis)
        asyncio.run(d.dispatch(_event("workflow.complete", {"workflow_id": "wf1"}), "acct_1"))
        redis.expire.assert_called_once()

    def test_dispatch_manager_error_does_not_raise(self):
        """WS send failure must not break dispatch pipeline."""
        manager = _make_manager()
        manager.send_event = AsyncMock(side_effect=Exception("ws_closed"))
        redis = _make_redis()
        d = _dispatcher(redis=redis, manager=manager)
        # Should not raise
        asyncio.run(d.dispatch(_event("workflow.complete", {"workflow_id": "wf99"}), "acct_fail"))
        # Redis persist still happens
        redis.xadd.assert_called_once()

    def test_dispatch_persist_failure_does_not_raise(self):
        """Redis failure must not break the streaming hot path."""
        redis = _make_redis()
        redis.xadd = AsyncMock(side_effect=ConnectionError("redis_down"))
        d = _dispatcher(redis=redis)
        # Should not raise
        asyncio.run(d.dispatch(_event("workflow.complete", {"workflow_id": "wf99"}), "acct_fail"))

    # ── Replay ────────────────────────────────────────────────────────────────

    def test_replay_decodes_bytes_from_redis(self):
        entry_id = b"1713456789000-0"
        fields = {
            b"type": b"workflow.complete",
            b"payload": b'{"content":"done"}',
            b"timestamp": b"2026-04-19T00:00:00+00:00",
            b"event_id": b"evt_123",
        }
        redis = _make_redis(xrange_return=[(entry_id, fields)])
        d = _dispatcher(redis=redis)
        entries = asyncio.run(d.replay("acct_1", cursor="0"))
        assert len(entries) == 1
        assert entries[0]["id"] == "1713456789000-0"
        assert entries[0]["type"] == "workflow.complete"

    def test_replay_returns_empty_on_redis_error(self):
        redis = _make_redis()
        redis.xrange = AsyncMock(side_effect=ConnectionError("redis_down"))
        d = _dispatcher(redis=redis)
        entries = asyncio.run(d.replay("acct_1"))
        assert entries == []

    def test_replay_empty_stream_returns_empty(self):
        redis = _make_redis(xrange_return=[])
        d = _dispatcher(redis=redis)
        entries = asyncio.run(d.replay("acct_1"))
        assert entries == []

    def test_sse_replay_stream_yields_sse_format(self):
        entry_id = b"1713456789000-0"
        fields = {
            b"type": b"workflow.complete",
            b"payload": b'{"content":"done"}',
            b"timestamp": b"2026-04-19T00:00:00+00:00",
            b"event_id": b"evt_1",
        }
        redis = _make_redis(xrange_return=[(entry_id, fields)])
        d = _dispatcher(redis=redis)

        async def _collect():
            chunks = []
            async for chunk in d.sse_replay_stream("acct_1"):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(_collect())
        # At least one event chunk + the replay.complete sentinel
        assert any("workflow.complete" in c for c in chunks)
        assert any("replay.complete" in c for c in chunks)

    def test_sse_replay_stream_ends_with_replay_complete(self):
        redis = _make_redis(xrange_return=[])
        d = _dispatcher(redis=redis)

        async def _collect():
            result = []
            async for chunk in d.sse_replay_stream("acct_1"):
                result.append(chunk)
            return result

        chunks = asyncio.run(_collect())
        last = chunks[-1]
        assert "replay.complete" in last

    def test_dispatch_batch_sends_all_events(self):
        redis = _make_redis()
        d = _dispatcher(redis=redis)
        events = [_event("workflow.complete", {"workflow_id": f"wf{i}"}) for i in range(3)]
        asyncio.run(d.dispatch_batch(events, "acct_1"))
        assert redis.xadd.call_count == 3


# ─────────────────────────────────────────────────────────────────────────────
# Test 24: ButlerWebSearchProvider
# ─────────────────────────────────────────────────────────────────────────────


class TestButlerWebSearchProvider:
    def _provider(self, results: list[RawSearchResult] | None = None) -> ButlerWebSearchProvider:
        backend = _StubProvider()
        provider = ButlerWebSearchProvider(backend=backend, provider_name="stub")
        if results is not None:
            # Patch the backend search to return controlled results
            async def _mock_search(query, max_results=5):
                return results[:max_results]

            backend.search = _mock_search
        return provider

    def test_stub_returns_empty_evidence_pack(self):
        p = self._provider(results=[])
        pack = asyncio.run(p.search("python async patterns"))
        assert pack.result_count == 0
        assert pack.results == []
        assert pack.provider == "stub"

    def test_results_sorted_by_combined_score(self):
        raw = [
            _raw_result(url="https://a.com", score=0.9),
            _raw_result(url="https://b.com", score=0.4),
            _raw_result(url="https://c.com", score=0.7),
        ]
        p = self._provider(results=raw)
        pack = asyncio.run(p.search("test"))
        scores = [r.combined_score for r in pack.results]
        assert scores == sorted(scores, reverse=True)

    def test_freshness_today_is_one(self):
        today = datetime.now(UTC)
        raw = [_raw_result(published_date=today, score=0.8)]
        p = self._provider(results=raw)
        pack = asyncio.run(p.search("test"))
        assert pack.results[0].freshness_score == pytest.approx(1.0, abs=0.01)

    def test_freshness_90_days_ago_is_zero(self):
        old = datetime.now(UTC) - timedelta(days=90)
        raw = [_raw_result(published_date=old, score=0.8)]
        p = self._provider(results=raw)
        pack = asyncio.run(p.search("test"))
        assert pack.results[0].freshness_score == pytest.approx(0.0, abs=0.05)

    def test_freshness_unknown_date_is_half(self):
        raw = [_raw_result(published_date=None, score=0.6)]
        p = self._provider(results=raw)
        pack = asyncio.run(p.search("test"))
        assert pack.results[0].freshness_score == pytest.approx(0.5, abs=0.01)

    def test_results_capped_at_five(self):
        raw = [_raw_result(url=f"https://ex{i}.com", score=0.5) for i in range(10)]
        p = self._provider(results=raw)
        pack = asyncio.run(p.search("test"))
        assert len(pack.results) <= 5

    def test_citations_have_id_url_title(self):
        raw = [_raw_result(url="https://example.com", title="Example", score=0.8)]
        p = self._provider(results=raw)
        pack = asyncio.run(p.search("test"))
        assert len(pack.citations) == 1
        assert pack.citations[0]["id"] in ("[1]", "[2]", "[3]", "[4]", "[5]")
        assert pack.citations[0]["url"] == "https://example.com"
        assert pack.citations[0]["title"] == "Example"

    def test_query_rewrite_news_mode(self):
        rewritten = ButlerWebSearchProvider._rewrite_query("latest AI news", "news")
        assert "reuters.com" in rewritten or "bbc.com" in rewritten

    def test_query_rewrite_technical_mode(self):
        rewritten = ButlerWebSearchProvider._rewrite_query("asyncio tutorial", "technical")
        assert "github.com" in rewritten or "stackoverflow.com" in rewritten

    def test_query_rewrite_general_mode_unchanged(self):
        q = "what is the capital of France"
        rewritten = ButlerWebSearchProvider._rewrite_query(q, "general")
        assert rewritten == q

    def test_combined_score_formula(self):
        """combined = 0.7 * relevance + 0.3 * freshness."""
        today = datetime.now(UTC)
        raw = [_raw_result(published_date=today, score=0.8)]
        p = self._provider(results=raw)
        pack = asyncio.run(p.search("test"))
        expected = 0.7 * 0.8 + 0.3 * 1.0
        assert pack.results[0].combined_score == pytest.approx(expected, abs=0.02)

    def test_snippet_truncated_at_2000_chars(self):
        long_snippet = "x" * 5000
        raw = [_raw_result(snippet=long_snippet, score=0.6)]
        p = self._provider(results=raw)
        pack = asyncio.run(p.search("test"))
        assert len(pack.results[0].snippet) <= 2000

    def test_evidence_pack_has_latency(self):
        p = self._provider(results=[])
        pack = asyncio.run(p.search("test"))
        assert isinstance(pack.latency_ms, float)
        assert pack.latency_ms >= 0

    def test_from_env_stub_default(self, monkeypatch):
        monkeypatch.delenv("BUTLER_SEARCH_PROVIDER", raising=False)
        p = ButlerWebSearchProvider.from_env()
        assert p._provider_name == "stub"
