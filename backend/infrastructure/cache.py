"""Redis cache client."""

from __future__ import annotations

import redis.asyncio as aioredis

from infrastructure.config import settings

_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Return the shared Redis client (lazy init)."""
    global _client  # noqa: PLW0603
    if _client is None:
        _client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _client


def get_redis_sync() -> aioredis.Redis:
    """Return the shared Redis client without async barrier (for middleware init)."""
    global _client  # noqa: PLW0603
    if _client is None:
        _client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _client


async def close_redis() -> None:
    """Close Redis connection pool on shutdown."""
    global _client  # noqa: PLW0603
    if _client is not None:
        await _client.aclose()
        _client = None