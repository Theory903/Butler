"""Phase 3 — Session and Stream Transplant tests.

Tests ButlerSessionManager, ButlerStreamBridge (SSE + WS), and
the gateway route layer. Fully mocked — no DB, no Redis network calls,
no real WebSockets.
"""

from __future__ import annotations

import asyncio
import json
import re
from unittest.mock import AsyncMock, MagicMock

from domain.events.schemas import (
    StreamErrorEvent,
    StreamFinalEvent,
    StreamTokenEvent,
)
from services.gateway.stream_bridge import ButlerStreamBridge

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _token_event(text: str) -> StreamTokenEvent:
    e = StreamTokenEvent.__new__(StreamTokenEvent)
    object.__setattr__(e, "event_type", "stream_token")
    object.__setattr__(e, "payload", {"token": text})
    return e


def _final_event() -> StreamFinalEvent:
    e = StreamFinalEvent.__new__(StreamFinalEvent)
    object.__setattr__(e, "event_type", "stream_final")
    object.__setattr__(e, "payload", {"input_tokens": 10, "output_tokens": 20, "duration_ms": 500})
    return e


def _error_event(status: int = 500) -> StreamErrorEvent:
    e = StreamErrorEvent.__new__(StreamErrorEvent)
    object.__setattr__(e, "event_type", "stream_error")
    object.__setattr__(
        e,
        "payload",
        {
            "type": "https://butler.lasmoid.ai/errors/internal-error",
            "status": status,
            "detail": "test error",
            "retryable": False,
        },
    )
    return e


async def _make_stream(*events):
    for e in events:
        yield e


def _make_redis_mock() -> AsyncMock:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.xrange = AsyncMock(return_value=[])
    redis.xadd = AsyncMock()
    redis.expire = AsyncMock()
    redis.pipeline = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=AsyncMock()),
            __aexit__=AsyncMock(return_value=False),
            execute=AsyncMock(return_value=[1, True]),
        )
    )
    return redis


# ─────────────────────────────────────────────────────────────────────────────
# Test 11: ButlerStreamBridge
# ─────────────────────────────────────────────────────────────────────────────


class TestStreamBridgeSSE:
    def _make_bridge(self, session_id="00000000-0000-0000-0000-000000000002") -> ButlerStreamBridge:
        return ButlerStreamBridge(
            session_id=session_id,
            account_id="00000000-0000-0000-0000-000000000001",
            redis=_make_redis_mock(),
            request_id="req_test",
        )

    def _parse_frame(self, frame: str) -> dict:
        """Surgical extraction of JSON from multi-line SSE frame."""
        match = re.search(r"data: (\{.*\})", frame)
        if match:
            return json.loads(match.group(1))
        return {}

    async def _collect_sse(self, bridge, stream) -> list[dict]:
        events = []
        async for frame in bridge.as_sse(stream):
            if "data: {" in frame:
                events.append(self._parse_frame(frame))
        return events

    def test_sse_frame_format(self):
        bridge = self._make_bridge()
        frame = bridge._sse_frame({"event": "test", "val": 1})
        assert 'data: {"event":"test","val":1}' in frame

    def test_as_sse_sequence(self):
        bridge = self._make_bridge()
        events = asyncio.run(
            self._collect_sse(bridge, _make_stream(_token_event("Hi"), _final_event()))
        )

        assert events[0]["event"] == "stream_start"
        assert events[1]["event"] == "stream_token"
        assert events[1]["payload"]["token"] == "Hi"
        assert events[2]["event"] == "stream_final"
        assert events[3]["event"] == "done"

    def test_as_sse_stops_after_error(self):
        bridge = self._make_bridge()

        async def _err_stream():
            yield _error_event(503)
            yield _token_event("no")

        events = asyncio.run(self._collect_sse(bridge, _err_stream()))
        assert any(e["event"] == "stream_error" for e in events)
        assert not any(e["event"] == "stream_token" for e in events)
        assert events[-1]["event"] == "done"

    def test_as_sse_exception(self):
        bridge = self._make_bridge()

        async def _fail():
            raise RuntimeError("crash")

        events = asyncio.run(self._collect_sse(bridge, _fail()))
        assert any(e["event"] == "error" for e in events)
        assert events[-1]["event"] == "done"


class TestStreamBridgeWebSocket:
    def _make_bridge(self) -> ButlerStreamBridge:
        return ButlerStreamBridge(
            session_id="00000000-0000-0000-0000-000000000002",
            account_id="00000000-0000-0000-0000-000000000001",
            redis=_make_redis_mock(),
        )

    def test_ws_flow(self):
        bridge = self._make_bridge()
        ws = AsyncMock()
        ws.send_text = AsyncMock()

        asyncio.run(bridge.forward_to_ws(ws, _make_stream(_token_event("Hi"), _final_event())))

        sent = [json.loads(c.args[0]) for c in ws.send_text.call_args_list]
        assert sent[0]["event"] == "stream_start"
        assert sent[1]["event"] == "stream_token"
        assert sent[1]["payload"]["token"] == "Hi"
        assert sent[-1]["event"] == "done"
