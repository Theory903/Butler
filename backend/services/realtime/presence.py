from datetime import UTC, datetime

from pydantic import BaseModel
from redis.asyncio import Redis

from core.state_sync import GlobalStateSyncer


class PresenceInfo(BaseModel):
    status: str
    session_id: str | None = None
    connected_at: str | None = None
    device_id: str | None = None
    last_heartbeat: str | None = None


class PresenceService:
    """Track connection presence per account/device."""

    def __init__(self, redis: Redis, syncer: GlobalStateSyncer | None = None):
        self._redis = redis
        self._syncer = syncer

    async def get_presence(self, account_id: str) -> PresenceInfo:
        data = await self._redis.hgetall(f"presence:{account_id}")
        if not data:
            return PresenceInfo(status="offline")

        def dec(val):
            return val.decode("utf-8") if isinstance(val, bytes) else str(val)

        decoded = {dec(k): dec(v) for k, v in data.items()}
        return PresenceInfo(**decoded)

    async def set_idle(self, account_id: str):
        await self._redis.hset(f"presence:{account_id}", "status", "idle")
        if self._syncer:
            await self._syncer.broadcast_presence(account_id, "idle")

    async def heartbeat(self, account_id: str):
        """Client sends periodic heartbeat to keep connection alive."""
        now = datetime.now(UTC).isoformat()
        await self._redis.hset(
            f"presence:{account_id}",
            mapping={
                "status": "connected",
                "last_heartbeat": now,
            },
        )
        await self._redis.expire(f"presence:{account_id}", 300)  # 5 min timeout
        if self._syncer:
            await self._syncer.broadcast_presence(account_id, "connected", {"last_heartbeat": now})
