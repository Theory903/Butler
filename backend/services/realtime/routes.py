"""Realtime service - WebSocket and SSE streaming."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/realtime", tags=["realtime"])

active_connections: dict[str, set[WebSocket]] = {}


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    if session_id not in active_connections:
        active_connections[session_id] = set()
    active_connections[session_id].add(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            for conn in active_connections.get(session_id, set()):
                if conn != websocket:
                    await conn.send_text(f"echo: {data}")
    except WebSocketDisconnect:
        active_connections.get(session_id, set()).discard(websocket)


@router.get("/stream/{session_id}")
async def sse_stream(session_id: str):
    async def event_generator():
        yield "data: connected\n\n"
        yield "data: session ready\n\n"

    return event_generator()


@router.get("/health")
async def health():
    return {"status": "healthy", "active_sessions": len(active_connections)}
