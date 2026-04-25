"""Redis cache client with tenant namespace support."""

from __future__ import annotations

import logging

import redis.asyncio as aioredis

from infrastructure.config import settings

logger = logging.getLogger(__name__)

_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Return the shared Redis client (lazy init)."""
    global _client  # noqa: PLW0603
    if _client is None:
        try:
            _client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info("redis_client_initialized")
        except Exception as e:
            logger.error("redis_client_init_failed", error=str(e))
            raise
    return _client


def get_redis_sync() -> aioredis.Redis:
    """Return the shared Redis client without async barrier (for middleware init)."""
    global _client  # noqa: PLW0603
    if _client is None:
        try:
            _client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info("redis_client_initialized_sync")
        except Exception as e:
            logger.error("redis_client_init_failed_sync", error=str(e))
            raise
    return _client


async def close_redis() -> None:
    """Close Redis connection pool on shutdown."""
    global _client  # noqa: PLW0603
    if _client is not None:
        try:
            await _client.aclose()
            _client = None
            logger.info("redis_client_closed")
        except Exception as e:
            logger.error("redis_client_close_failed", error=str(e))


class TenantRedisClient:
    """
    Redis client wrapper that enforces tenant namespace scoping.

    All keys are automatically prefixed with tenant namespace.
    Prevents cross-tenant data leakage in Redis.
    """

    def __init__(self, redis_client: aioredis.Redis, tenant_id: str) -> None:
        """
        Initialize tenant-scoped Redis client.

        Args:
            redis_client: Base Redis client
            tenant_id: Tenant UUID for namespace prefixing

        Raises:
            ValueError: If tenant_id is None or empty
        """
        if not tenant_id:
            raise ValueError("tenant_id cannot be None or empty")
        self._redis = redis_client
        self._tenant_id = tenant_id
        self._namespace = f"butler:tenant:{tenant_id}:"

    def _key(self, key: str) -> str:
        """Prefix key with tenant namespace."""
        if key.startswith(self._namespace):
            return key
        return f"{self._namespace}{key}"

    async def get(self, key: str) -> str | None:
        """Get value for tenant-scoped key."""
        try:
            return await self._redis.get(self._key(key))
        except Exception as e:
            logger.error("tenant_redis_get_failed", key=key, tenant_id=self._tenant_id, error=str(e))
            return None

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        """Set value for tenant-scoped key."""
        try:
            return await self._redis.set(self._key(key), value, ex=ex)
        except Exception as e:
            logger.error("tenant_redis_set_failed", key=key, tenant_id=self._tenant_id, error=str(e))
            return False

    async def delete(self, key: str) -> int:
        """Delete tenant-scoped key."""
        return await self._redis.delete(self._key(key))

    async def exists(self, key: str) -> int:
        """Check if tenant-scoped key exists."""
        return await self._redis.exists(self._key(key))

    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiry on tenant-scoped key."""
        return await self._redis.expire(self._key(key), seconds)

    async def ttl(self, key: str) -> int:
        """Get TTL for tenant-scoped key."""
        return await self._redis.ttl(self._key(key))

    async def keys(self, pattern: str = "*") -> list[str]:
        """
        Get keys matching pattern within tenant namespace.

        Pattern is automatically scoped to tenant namespace.
        """
        return await self._redis.keys(self._key(pattern))

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern within tenant namespace."""
        try:
            keys = await self.keys(pattern)
            if keys:
                # Delete in batches to avoid Redis command size limits
                batch_size = 1000
                deleted = 0
                for i in range(0, len(keys), batch_size):
                    batch = keys[i:i + batch_size]
                    deleted += await self._redis.delete(*batch)
                return deleted
            return 0
        except Exception as e:
            logger.error("tenant_redis_delete_pattern_failed", pattern=pattern, tenant_id=self._tenant_id, error=str(e))
            return 0


async def get_tenant_redis(tenant_id: str) -> TenantRedisClient:
    """
    Get a tenant-scoped Redis client.

    Args:
        tenant_id: Tenant UUID for namespace prefixing

    Returns:
        TenantRedisClient with automatic namespace scoping
    """
    redis = await get_redis()
    return TenantRedisClient(redis, tenant_id)
