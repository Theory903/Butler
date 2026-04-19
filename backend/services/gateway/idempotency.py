"""Idempotency enforcement using Redis.

Clients send Idempotency-Key header.
First request executes + response cached alongside the structural Request Hash.
Duplicate requests with same key AND same hash → return cached response safely.
Duplicate requests with same key BUT different hash → 409 Conflict.
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from typing import Dict, Any

from redis.asyncio import Redis

from domain.auth.exceptions import GatewayErrors

def generate_request_hash(payload: Dict[str, Any]) -> str:
    """Canonicalize and hash the body parameters safely."""
    # sort_keys guarantees identical JSON maps hash deterministically
    canonical_str = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

@dataclass
class CachedResponse:
    request_hash: str
    body: dict
    status_code: int

    def to_json(self) -> str:
        return json.dumps({
            "request_hash": self.request_hash,
            "body": self.body, 
            "status_code": self.status_code
        })

    @classmethod
    def from_json(cls, data: str) -> "CachedResponse":
        parsed = json.loads(data)
        return cls(
            request_hash=parsed["request_hash"],
            body=parsed["body"], 
            status_code=parsed["status_code"]
        )

class IdempotencyService:
    """Cache mutating request results structurally against their request boundaries.

    TTL default: 24 hours (86400 seconds).
    Key namespace: idempotent:{key}
    """

    def __init__(self, redis: Redis, ttl_seconds: int = 86400) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    async def check(self, key: str | None, current_payload: Dict[str, Any]) -> CachedResponse | None:
        """
        Return cached response if key was seen before.
        Raises 409 Conflict if key matches but the generated payload hash diverges indicating a hijack.
        """
        if not key:
            return None
            
        cached_raw = await self._redis.get(f"idempotent:{key}")
        if not cached_raw:
            return None
            
        cached = CachedResponse.from_json(cached_raw)
        current_hash = generate_request_hash(current_payload)
        
        if cached.request_hash != current_hash:
            raise GatewayErrors.IDEMPOTENCY_CONFLICT

        # Emit replay counter — this response came from cache, not orchestrator
        try:
            from core.observability import get_metrics
            get_metrics().inc_idempotency_replay(endpoint="gateway")
        except Exception:
            pass

        return cached


    async def store(self, key: str | None, payload: Dict[str, Any], response: dict, status_code: int = 200) -> None:
        """Cache response for key locked structurally to the payload hash."""
        if not key:
            return
            
        request_hash = generate_request_hash(payload)
        cached = CachedResponse(request_hash=request_hash, body=response, status_code=status_code)
        
        await self._redis.setex(f"idempotent:{key}", self._ttl, cached.to_json())

    async def acquire_lock(self, key: str | None) -> bool:
        """Acquire lock to prevent concurrent processing of same key."""
        if not key:
            return True
        result = await self._redis.set(
            f"idempotent_lock:{key}",
            "1",
            nx=True,    # Only set if absent
            ex=30,      # 30-second processing timeout
        )
        return bool(result)

    async def release_lock(self, key: str | None) -> None:
        if key:
            await self._redis.delete(f"idempotent_lock:{key}")
