from datetime import datetime, UTC
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect
from redis.asyncio import Redis
import json

from .events import RealtimeEvent
from .presence import PresenceService

class ConnectionManager:
    """WebSocket connection lifecycle management."""
    
    def __init__(self, redis: Redis, presence: PresenceService):
        self._connections: dict[str, WebSocket] = {}  # account_id → websocket
        self._redis = redis
        self._presence = presence
    
    async def connect(self, websocket: WebSocket, account_id: str, session_id: str):
        """Accept connection and register."""
        await websocket.accept()
        self._connections[account_id] = websocket
        
        # Update presence
        await self._redis.hset(f"presence:{account_id}", mapping={
            "status": "connected",
            "session_id": session_id,
            "connected_at": datetime.now(UTC).isoformat(),
            "device_id": websocket.headers.get("X-Device-ID", "unknown"),
        })
        await self._redis.expire(f"presence:{account_id}", 3600)
    
    async def disconnect(self, account_id: str):
        """Remove connection and update presence."""
        self._connections.pop(account_id, None)
        await self._redis.hset(f"presence:{account_id}", key="status", value="disconnected")
    
    async def send_event(self, account_id: str, event: RealtimeEvent):
        """Send typed event to connected client."""
        ws = self._connections.get(account_id)
        if ws:
            try:
                await ws.send_json(event.to_dict())
            except WebSocketDisconnect:
                await self.disconnect(account_id)
        
        # Always persist durable events for replay
        if event.durable:
            # Stream payload must be mapping of string fields
            msg = {k: str(v) for k, v in event.to_dict().items()}
            await self._redis.xadd(
                f"events:{account_id}",
                msg,
                maxlen=1000,
            )
    
    async def broadcast_to_account(self, account_id: str, event: RealtimeEvent):
        """Send to all devices for an account."""
        await self.send_event(account_id, event)
