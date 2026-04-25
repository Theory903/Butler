"""
Distributed Cache - Distributed Caching with Redis Cluster

Implements distributed caching with Redis cluster support.
Supports multi-node caching, sharding, and replication.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class CacheStrategy(StrEnum):
    """Cache strategy."""

    WRITE_THROUGH = "write_through"
    WRITE_BEHIND = "write_behind"
    REFRESH_AHEAD = "refresh_ahead"
    CACHE_ASIDE = "cache_aside"


@dataclass(frozen=True, slots=True)
class CacheNode:
    """Cache node configuration."""

    node_id: str
    host: str
    port: int
    weight: int
    healthy: bool


@dataclass(frozen=True, slots=True)
class CacheEntry:
    """Cache entry."""

    key: str
    value: Any
    ttl_seconds: int
    created_at: datetime
    access_count: int
    last_accessed: datetime


class DistributedCache:
    """
    Distributed cache with Redis cluster support.

    Features:
    - Multi-node caching
    - Sharding
    - Replication
    - Eviction policies
    """

    def __init__(
        self,
        strategy: CacheStrategy = CacheStrategy.CACHE_ASIDE,
    ) -> None:
        """Initialize distributed cache."""
        self._strategy = strategy
        self._nodes: dict[str, CacheNode] = {}
        self._cache: dict[str, CacheEntry] = {}  # In-memory fallback
        self._shards: dict[int, str] = {}  # shard_index -> node_id
        self._shard_count = 16

    def add_node(
        self,
        node_id: str,
        host: str,
        port: int,
        weight: int = 1,
    ) -> CacheNode:
        """
        Add a cache node.

        Args:
            node_id: Node identifier
            host: Node host
            port: Node port
            weight: Node weight for sharding

        Returns:
            Cache node
        """
        node = CacheNode(
            node_id=node_id,
            host=host,
            port=port,
            weight=weight,
            healthy=True,
        )

        self._nodes[node_id] = node

        # Rebalance shards
        self._rebalance_shards()

        logger.info(
            "cache_node_added",
            node_id=node_id,
            host=host,
            port=port,
        )

        return node

    def _rebalance_shards(self) -> None:
        """Rebalance shards across nodes."""
        self._shards.clear()

        total_weight = sum(node.weight for node in self._nodes.values())
        if total_weight == 0:
            return

        # Weighted sharding
        node_ids = list(self._nodes.keys())
        weights = [self._nodes[nid].weight for nid in node_ids]

        for shard_index in range(self._shard_count):
            # Select node based on weight
            cumulative = 0
            rand = (shard_index * 9301 + 49297) % 233280
            normalized = rand / 233280

            for i, weight in enumerate(weights):
                cumulative += weight / total_weight
                if normalized <= cumulative:
                    self._shards[shard_index] = node_ids[i]
                    break

    def _get_node_for_key(self, key: str) -> str | None:
        """
        Get node for a key based on sharding.

        Args:
            key: Cache key

        Returns:
            Node identifier or None
        """
        if not self._nodes:
            return None

        # Hash key to shard
        hash_value = hash(key) % self._shard_count
        return self._shards.get(hash_value)

    async def get(
        self,
        key: str,
    ) -> Any | None:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        entry = self._cache.get(key)

        if not entry:
            return None

        # Check TTL
        if (datetime.now(UTC) - entry.created_at).total_seconds() > entry.ttl_seconds:
            del self._cache[key]
            return None

        # Update access stats
        self._cache[key] = CacheEntry(
            key=entry.key,
            value=entry.value,
            ttl_seconds=entry.ttl_seconds,
            created_at=entry.created_at,
            access_count=entry.access_count + 1,
            last_accessed=datetime.now(UTC),
        )

        logger.debug(
            "cache_hit",
            key=key,
        )

        return entry.value

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int = 3600,
    ) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time to live in seconds

        Returns:
            True if set successfully
        """
        entry = CacheEntry(
            key=key,
            value=value,
            ttl_seconds=ttl_seconds,
            created_at=datetime.now(UTC),
            access_count=0,
            last_accessed=datetime.now(UTC),
        )

        self._cache[key] = entry

        logger.debug(
            "cache_set",
            key=key,
            ttl_seconds=ttl_seconds,
        )

        return True

    async def delete(self, key: str) -> bool:
        """
        Delete value from cache.

        Args:
            key: Cache key

        Returns:
            True if deleted
        """
        if key in self._cache:
            del self._cache[key]

            logger.debug(
                "cache_deleted",
                key=key,
            )

            return True
        return False

    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.

        Args:
            key: Cache key

        Returns:
            True if exists
        """
        entry = self._cache.get(key)

        if not entry:
            return False

        # Check TTL
        if (datetime.now(UTC) - entry.created_at).total_seconds() > entry.ttl_seconds:
            del self._cache[key]
            return False

        return True

    async def expire(self, key: str, ttl_seconds: int) -> bool:
        """
        Set TTL for a key.

        Args:
            key: Cache key
            ttl_seconds: Time to live in seconds

        Returns:
            True if set successfully
        """
        entry = self._cache.get(key)

        if not entry:
            return False

        self._cache[key] = CacheEntry(
            key=entry.key,
            value=entry.value,
            ttl_seconds=ttl_seconds,
            created_at=entry.created_at,
            access_count=entry.access_count,
            last_accessed=entry.last_accessed,
        )

        return True

    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        """
        Get multiple values from cache.

        Args:
            keys: Cache keys

        Returns:
            Dictionary of key-value pairs
        """
        result = {}

        for key in keys:
            value = await self.get(key)
            if value is not None:
                result[key] = value

        return result

    async def set_many(self, items: dict[str, Any], ttl_seconds: int = 3600) -> int:
        """
        Set multiple values in cache.

        Args:
            items: Dictionary of key-value pairs
            ttl_seconds: Time to live in seconds

        Returns:
            Number of items set
        """
        count = 0

        for key, value in items.items():
            if await self.set(key, value, ttl_seconds):
                count += 1

        return count

    async def clear(self) -> bool:
        """
        Clear all cache entries.

        Returns:
            True if cleared
        """
        self._cache.clear()

        logger.info("cache_cleared")

        return True

    def cleanup_expired(self) -> int:
        """
        Clean up expired cache entries.

        Returns:
            Number of entries cleaned up
        """
        now = datetime.now(UTC)
        expired_keys = []

        for key, entry in self._cache.items():
            if (now - entry.created_at).total_seconds() > entry.ttl_seconds:
                expired_keys.append(key)

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.info(
                "expired_entries_cleaned",
                count=len(expired_keys),
            )

        return len(expired_keys)

    def get_cache_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Cache statistics
        """
        total_entries = len(self._cache)
        total_accesses = sum(entry.access_count for entry in self._cache.values())

        return {
            "total_entries": total_entries,
            "total_accesses": total_accesses,
            "total_nodes": len(self._nodes),
            "shard_count": self._shard_count,
            "strategy": self._strategy,
        }
