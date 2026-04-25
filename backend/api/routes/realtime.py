"""Realtime routes — Phase 6b.

Endpoints:
  WS  /realtime/ws                  — Primary WebSocket connection (ticket auth)
  GET /realtime/stream/{account_id} — SSE replay stream (cursor-based)
  GET /realtime/events/{account_id} — JSON snapshot of recent events
  GET /realtime/presence/{account_id} — Presence state
  POST /realtime/publish             — Admin: push event to account stream

All routes use Butler's ButlerStreamDispatcher for event delivery.
Auth is ticket-based (short-lived RS256 token in query param) to
avoid sending Authorization header over WebSocket upgrade.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, WebSocket
from fastapi.responses import StreamingResponse
from starlette.websockets import WebSocketDisconnect

from core.deps import (
    get_connection_manager,
    get_redis,
)
from services.realtime.manager import ConnectionManager
from services.realtime.presence import PresenceService
from services.realtime.stream_dispatcher import ButlerStreamDispatcher

# ── Dependency factories ───────────────────────────────────────────────────────


def get_presence(redis=Depends(get_redis)):
    return PresenceService(redis)


def get_stream_dispatcher(
    redis=Depends(get_redis),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> ButlerStreamDispatcher:
    return ButlerStreamDispatcher(redis=redis, manager=manager)


# ── Router ────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/realtime", tags=["realtime"])


# ── 1. WebSocket — primary connection ─────────────────────────────────────────


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="Short-lived RS256 access token for WS upgrade"),
    manager: ConnectionManager = Depends(get_connection_manager),
    dispatcher: ButlerStreamDispatcher = Depends(get_stream_dispatcher),
):
    """WebSocket endpoint with ticket-based authentication.

    Client sends heartbeat and resume messages:
      {"type": "heartbeat"}
      {"type": "resume", "cursor": "<last_seen_event_id>"}
    """
    # Authenticate the upgrade ticket
    try:
        from services.auth.jwt import get_jwks_manager

        jwks = get_jwks_manager()
        claims = jwks.verify_token(token)
        account_id: str = claims["sub"]
        session_id: str = claims.get("sid", account_id)
    except Exception:
        await websocket.close(code=1008)  # Policy Violation — bad token
        return

    await manager.connect(websocket, account_id, session_id)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "heartbeat":
                await manager._presence.heartbeat(account_id)
                await websocket.send_json({"type": "heartbeat.ack", "ts": str(data.get("ts", ""))})

            elif msg_type == "resume":
                # Client reconnected — replay missed events from cursor
                cursor = data.get("cursor", "0")
                replayed = await dispatcher.replay(account_id, cursor=cursor, count=50)
                for entry in replayed:
                    await websocket.send_json(entry)
                await websocket.send_json({"type": "replay.complete", "count": len(replayed)})

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        await manager.disconnect(account_id)


# ── 2. GET /realtime/stream/{account_id} — SSE cursor replay ──────────────────


@router.get(
    "/stream/{account_id}",
    summary="SSE cursor-based event replay",
    response_class=StreamingResponse,
)
async def sse_replay(
    account_id: str,
    cursor: str = Query("0", description="Last seen Redis Stream event ID"),
    count: int = Query(50, le=200, description="Max events to replay"),
    dispatcher: ButlerStreamDispatcher = Depends(get_stream_dispatcher),
):
    """Stream missed events as SSE starting from cursor.

    After replaying historical events, emits `event: replay.complete`.
    Client should switch to primary WebSocket after replay is done.
    """
    return StreamingResponse(
        dispatcher.sse_replay_stream(account_id, cursor=cursor, count=count),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── 3. GET /realtime/events/{account_id} — JSON snapshot ─────────────────────


@router.get(
    "/events/{account_id}",
    summary="Recent events as JSON (up to 50)",
)
async def get_recent_events(
    account_id: str,
    cursor: str = Query("0", description="Start cursor (Redis Stream ID)"),
    count: int = Query(50, le=200),
    dispatcher: ButlerStreamDispatcher = Depends(get_stream_dispatcher),
) -> dict:
    entries = await dispatcher.replay(account_id, cursor=cursor, count=count)
    return {
        "account_id": account_id,
        "events": entries,
        "count": len(entries),
        "next_cursor": entries[-1]["id"] if entries else cursor,
    }


# ── 4. GET /realtime/presence/{account_id} ────────────────────────────────────


@router.get("/presence/{account_id}", summary="Account presence state")
async def get_presence_endpoint(
    account_id: str,
    presence: PresenceService = Depends(get_presence),
) -> dict:
    return await presence.get_presence(account_id)


# ── 5. POST /realtime/publish — admin event push ─────────────────────────────


@router.post("/publish", summary="Push a Butler event to an account's stream (admin)")
async def publish_event(
    account_id: str = Query(...),
    event_type: str = Query("workflow.update"),
    payload: dict = None,
    dispatcher: ButlerStreamDispatcher = Depends(get_stream_dispatcher),
) -> dict:
    """Admin-only: push a synthetic event to an account's realtime stream."""
    from domain.events.schemas import ButlerEvent

    if payload is None:
        payload = {}

    event = ButlerEvent(event_type=event_type, payload=payload)
    await dispatcher.dispatch(event, account_id)
    return {"published": True, "event_type": event_type, "account_id": account_id}
