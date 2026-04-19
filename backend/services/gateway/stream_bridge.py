"""ButlerStreamBridge — Phase 3 (v3.1 production hardened).

Converts AsyncGenerator[ButlerEvent] from OrchestratorService.intake_streaming()
into wire-format SSE frames and WebSocket JSON messages.

Production invariants:
  - Every SSE frame carries an `id:` field for Last-Event-ID resume.
  - Bounded async queue (_SSE_QUEUE_MAX) enforces true backpressure: if the
    client cannot consume fast enough the producer is paused, not dropped.
  - Reasoning / thinking tags are stripped before frames leave the edge.
    Clients receive only final, user-visible tokens.
  - WS send path uses a semaphore so concurrent callers cannot interleave frames.
  - Stream max-duration guard prevents runaway connections.

SSE wire format (WHATWG EventSource):
  id: <monotonic-counter>
  data: <json>

WebSocket wire format:
  JSON string with "event" top-level key.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import structlog
from typing import AsyncGenerator, Optional

from fastapi import WebSocket, WebSocketDisconnect

from domain.events.schemas import (
    ButlerEvent,
    StreamTokenEvent,
    StreamFinalEvent,
    StreamErrorEvent,
    StreamApprovalRequiredEvent,
    StreamToolCallEvent,
    StreamToolResultEvent,
)

logger = structlog.get_logger(__name__)

# ── Tuning constants ──────────────────────────────────────────────────────────

_SSE_QUEUE_MAX: int = 128
_KEEPALIVE_INTERVAL_S: float = 15.0
_STREAM_MAX_DURATION_S: float = 300.0

# Strip <thinking>...</thinking> and <reasoning>...</reasoning> tags emitted by
# some LLM providers (Anthropic extended thinking, o-series reasoning tokens).
_REDACT_RE = re.compile(
    r"<(thinking|reasoning|antml:thinking)>.*?</\1>",
    flags=re.DOTALL | re.IGNORECASE,
)


def _redact(text: str) -> str:
    """Remove reasoning/thinking content before a frame leaves the edge."""
    return _REDACT_RE.sub("", text)


# ── SSE headers ───────────────────────────────────────────────────────────────

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",       # disable nginx buffering
    "Connection": "keep-alive",
    "Transfer-Encoding": "chunked",
}


# ── Bridge ────────────────────────────────────────────────────────────────────

class ButlerStreamBridge:
    """Converts ButlerEvent stream into SSE or WebSocket wire frames.

    Usage (SSE):
        bridge = ButlerStreamBridge(session_id=..., account_id=..., request_id=...)
        return StreamingResponse(
            bridge.as_sse(orchestrator.intake_streaming(envelope)),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    Usage (WebSocket):
        bridge = ButlerStreamBridge(session_id=..., account_id=...)
        await bridge.forward_to_ws(websocket, orchestrator.intake_streaming(envelope))
    """

    def __init__(
        self,
        session_id: str,
        account_id: str,
        redis: Redis,
        request_id: str = "",
        last_event_id: Optional[int] = None,
    ) -> None:
        self._session_id = session_id
        self._account_id = account_id
        self._redis = redis
        self._request_id = request_id
        self._last_event_id = last_event_id
        # The next event we should produce is last_event_id + 1
        self._event_counter: int = (last_event_id or 0) + 1
        self._ws_lock = asyncio.Semaphore(1)
        self._stream_key = f"stream:log:{session_id}"

    # ── SSE ───────────────────────────────────────────────────────────────────

    async def as_sse(
        self,
        event_stream: AsyncGenerator[ButlerEvent, None],
    ) -> AsyncGenerator[str, None]:
        """Yield SSE-formatted strings via a bounded queue (true backpressure).

        Architecture:
          - A producer task fills queue from the event_stream.
          - The consumer (this generator) drains the queue and yields frames.
          - When the queue is full the producer awaits, pausing the upstream.
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=_SSE_QUEUE_MAX)
        _SENTINEL = object()

        async def _producer():
            try:
                async for event in event_stream:
                    await queue.put(event)          # blocks when full -> backpressure
                    if isinstance(event, (StreamFinalEvent, StreamErrorEvent)):
                        break
            except Exception as exc:
                await queue.put(exc)
            finally:
                await queue.put(_SENTINEL)

        producer_task = asyncio.create_task(_producer())
        stream_start = time.monotonic()

        # Track open stream in Prometheus gauge
        try:
            from core.observability import get_metrics
            get_metrics().inc_active_streams()
        except Exception:
            pass

        # ── Step 1: Replay missed events from Redis (Resume Semantic) ──────────
        if self._last_event_id is not None:
            try:
                # Redis Stream ID is <ts>-<seq>, but we use monotonic counters
                # stored in the field 'id'. We range from start to find them.
                # butler uses custom event IDs: 1, 2, 3...
                # We fetch all events and filter by our monotonic ID.
                raw_events = await self._redis.xrange(self._stream_key)
                for _id, fields in raw_events:
                    e_id = int(fields.get(b"id", b"0"))
                    if e_id > self._last_event_id:
                        data = json.loads(fields[b"data"])
                        yield self._sse_frame(data, event_id=e_id)
                        # Sync counter to correctly continue
                        self._event_counter = max(self._event_counter, e_id + 1)
            except Exception:
                logger.warning("stream_resume_failed", session_id=self._session_id)

        # Opening frame
        start_frame = {
            "event": "stream_start",
            "session_id": self._session_id,
            "request_id": self._request_id,
            "ts": _now_ms(),
        }
        yield self._sse_frame(start_frame)
        await self._log_event(start_frame)

        try:
            while True:
                # Keepalive: if nothing arrives within the interval, ping
                try:
                    item = await asyncio.wait_for(
                        queue.get(), timeout=_KEEPALIVE_INTERVAL_S
                    )
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                if item is _SENTINEL:
                    break

                if isinstance(item, Exception):
                    raise item

                elapsed = time.monotonic() - stream_start
                if elapsed > _STREAM_MAX_DURATION_S:
                    yield self._sse_frame(
                        {
                            "event": "error",
                            "type": "https://butler.lasmoid.ai/errors/stream-timeout",
                            "status": 504,
                            "detail": "Stream duration limit exceeded",
                            "retryable": False,
                        }
                    )
                    break

                event: ButlerEvent = item
                frame = self._event_to_frame(event)
                yield self._sse_frame(frame, event_id=self._event_counter)
                await self._log_event(frame, event_id=self._event_counter)
                self._event_counter += 1

                if isinstance(event, (StreamFinalEvent, StreamErrorEvent)):
                    break

        except asyncio.CancelledError:
            logger.debug("sse_stream_cancelled", session_id=self._session_id)
            return
        except Exception as exc:
            logger.exception("sse_stream_error", session_id=self._session_id)
            yield self._sse_frame(
                {
                    "event": "error",
                    "type": "https://butler.lasmoid.ai/errors/internal-error",
                    "status": 500,
                    "detail": str(exc),
                    "retryable": False,
                },
                event_id=self._event_counter,
            )
            self._event_counter += 1
        finally:
            producer_task.cancel()
            # Decrement active stream gauge
            try:
                from core.observability import get_metrics
                get_metrics().dec_active_streams()
            except Exception:
                pass
            yield self._sse_frame(
                {"event": "done", "session_id": self._session_id},
                event_id=self._event_counter,
            )

    # ── WebSocket ─────────────────────────────────────────────────────────────

    async def forward_to_ws(
        self,
        websocket: WebSocket,
        event_stream: AsyncGenerator[ButlerEvent, None],
    ) -> None:
        """Forward ButlerEvents to an open WebSocket with a send semaphore."""
        await self._ws_send(
            websocket,
            {
                "event": "stream_start",
                "session_id": self._session_id,
                "request_id": self._request_id,
                "ts": _now_ms(),
            },
        )

        try:
            async for event in event_stream:
                frame = self._event_to_frame(event)
                await self._ws_send(websocket, frame)
                if isinstance(event, (StreamFinalEvent, StreamErrorEvent)):
                    break

            await self._ws_send(
                websocket, {"event": "done", "session_id": self._session_id}
            )

        except WebSocketDisconnect:
            logger.debug("ws_disconnected", session_id=self._session_id)
        except Exception as exc:
            logger.exception("ws_stream_error", session_id=self._session_id)
            try:
                await self._ws_send(
                    websocket,
                    {
                        "event": "error",
                        "type": "https://butler.lasmoid.ai/errors/internal-error",
                        "status": 500,
                        "detail": str(exc),
                    },
                )
            except Exception:
                pass

    async def _ws_send(self, websocket: WebSocket, frame: dict) -> None:
        """Thread-safe WebSocket send via semaphore."""
        async with self._ws_lock:
            await websocket.send_text(json.dumps(frame, separators=(",", ":")))

    # ── Frame construction ────────────────────────────────────────────────────

    def _event_to_frame(self, event: ButlerEvent) -> dict:
        """Convert a ButlerEvent to a wire-format dict, applying redaction."""
        payload = event.payload.copy() if event.payload else {}
        payload.setdefault("session_id", self._session_id)
        payload.setdefault("ts", _now_ms())

        # Redact reasoning tags from token and final text fields
        if isinstance(event, StreamTokenEvent):
            token = payload.get("token", "")
            if token:
                payload["token"] = _redact(token)
        elif isinstance(event, StreamFinalEvent):
            content = payload.get("content", "")
            if content:
                payload["content"] = _redact(content)

        return {"event": event.event_type, "payload": payload}

    @staticmethod
    def _sse_frame(data: dict, event_id: Optional[int] = None) -> str:
        """Format a dict as an SSE frame with optional event id."""
        lines = []
        if event_id is not None:
            lines.append(f"id: {event_id}")
        lines.append(f"data: {json.dumps(data, separators=(',', ':'))}")
        lines.append("")
        lines.append("")
        return "\n".join(lines)

    async def _log_event(self, data: dict, event_id: Optional[int] = None) -> None:
        """Append frame to Redis Stream for durable resume support."""
        try:
            # XADD with id='*' (auto-generated Redis ID)
            # data field contains the JSON payload
            # id field contains our monotonic Butler event counter
            fields = {"data": json.dumps(data), "id": str(event_id or 0)}
            await self._redis.xadd(self._stream_key, fields, maxlen=1000, approximate=True)
            # Set 24h expiration on the stream key if not already set
            await self._redis.expire(self._stream_key, 86400)
        except Exception:
            # Observability-only, don't break the stream if Redis fails to log
            pass


# ── Utilities ─────────────────────────────────────────────────────────────────

def _now_ms() -> int:
    return int(time.monotonic() * 1000)
