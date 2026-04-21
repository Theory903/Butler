import asyncio
import uuid
import time
from typing import Optional
from redis.asyncio import Redis
import structlog

logger = structlog.get_logger(__name__)

class ButlerLock:
    """
    Distributed Redis-backed lock.
    Uses SET NX PX for atomic acquisition.
    """
    def __init__(
        self, 
        redis: Redis, 
        name: str, 
        ttl_ms: int = 10000, 
        timeout_ms: int = 5000,
        retry_interval_ms: int = 100
    ):
        self._redis = redis
        self._name = f"butler:lock:{name}"
        self._ttl_ms = ttl_ms
        self._timeout_ms = timeout_ms
        self._retry_interval_ms = retry_interval_ms
        self._id = str(uuid.uuid4())
        self._owned = False

    async def __aenter__(self):
        start_time = time.perf_counter()
        while (time.perf_counter() - start_time) * 1000 < self._timeout_ms:
            # Atomic SET if Not Exists with TTL
            ok = await self._redis.set(
                self._name, 
                self._id, 
                px=self._ttl_ms, 
                nx=True
            )
            if ok:
                self._owned = True
                return self
            await asyncio.sleep(self._retry_interval_ms / 1000.0)
        
        raise TimeoutError(f"Could not acquire lock: {self._name}")

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if not self._owned:
            return

        # Lua script for atomic unlock (only if we own it)
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        await self._redis.eval(script, 1, self._name, self._id)
        self._owned = False

class LockManager:
    """Factory for distributed locks."""
    def __init__(self, redis: Redis):
        self._redis = redis

    def get_lock(self, name: str, **kwargs) -> ButlerLock:
        return ButlerLock(self._redis, name, **kwargs)
