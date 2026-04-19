from datetime import datetime, UTC
from redis.asyncio import Redis
from pydantic import BaseModel
from typing import Optional

class PresenceInfo(BaseModel):
    status: str
    session_id: Optional[str] = None
    connected_at: Optional[str] = None
    device_id: Optional[str] = None
    last_heartbeat: Optional[str] = None

class PresenceService:
    """Track connection presence per account/device."""
    
    def __init__(self, redis: Redis):
        self._redis = redis

    async def get_presence(self, account_id: str) -> PresenceInfo:
        data = await self._redis.hgetall(f"presence:{account_id}")
        # Note: Redis returns bytes usually unless decode_responses=True. Assume it's handled or strings here based on asyncpg/redis usage pattern
        # If it returns an empty dict, user is offline.
        if not data:
            return PresenceInfo(status="offline")
            
        # Decode strings if necessary safely
        def dec(val):
            return val.decode("utf-8") if isinstance(val, bytes) else str(val)

        decoded = {dec(k): dec(v) for k, v in data.items()}
        return PresenceInfo(**decoded)
    
    async def set_idle(self, account_id: str):
        await self._redis.hset(f"presence:{account_id}", "status", "idle")
    
    async def heartbeat(self, account_id: str):
        """Client sends periodic heartbeat to keep connection alive."""
        await self._redis.hset(f"presence:{account_id}", mapping={
            "status": "connected",
            "last_heartbeat": datetime.now(UTC).isoformat(),
        })
        await self._redis.expire(f"presence:{account_id}", 300)  # 5 min timeout
