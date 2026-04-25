"""Redis abstractions for tenant-scoped operations.

This module provides protocol-defined abstractions for Redis operations
to ensure all Redis usage is properly tenant-scoped through TenantNamespace.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from redis.asyncio import Redis


class SandboxStatus(str, Enum):
    """Sandbox execution status."""

    CREATING = "creating"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"
    DESTROYED = "destroyed"


class WorkflowStatus(str, Enum):
    """Workflow execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@runtime_checkable
class CacheAbstraction(Protocol):
    """Cache abstraction for tenant-scoped cache operations."""

    async def get(self, namespace: str, key: str) -> Any | None:
        """Get value from cache."""
        ...

    async def set(self, namespace: str, key: str, value: Any, ttl: int) -> None:
        """Set value in cache with TTL."""
        ...

    async def delete(self, namespace: str, key: str) -> None:
        """Delete value from cache."""
        ...

    async def exists(self, namespace: str, key: str) -> bool:
        """Check if key exists in cache."""
        ...


@runtime_checkable
class LockAbstraction(Protocol):
    """Lock abstraction for tenant-scoped lock operations."""

    async def acquire(self, namespace: str, lock_name: str, ttl: int) -> bool:
        """Acquire lock with TTL."""
        ...

    async def release(self, namespace: str, lock_name: str) -> None:
        """Release lock."""
        ...

    async def is_locked(self, namespace: str, lock_name: str) -> bool:
        """Check if lock is held."""
        ...


@runtime_checkable
class RateLimitAbstraction(Protocol):
    """Rate limit abstraction for tenant-scoped rate limiting."""

    async def check(self, namespace: str, limit_id: str, limit: int, window: int) -> bool:
        """Check if rate limit allows operation."""
        ...

    async def increment(self, namespace: str, limit_id: str) -> int:
        """Increment rate limit counter."""
        ...

    async def reset(self, namespace: str, limit_id: str) -> None:
        """Reset rate limit counter."""
        ...


@runtime_checkable
class ArtifactAbstraction(Protocol):
    """Artifact abstraction for tenant-scoped artifact storage."""

    async def store(self, namespace: str, artifact_id: str, data: bytes, ttl: int) -> None:
        """Store artifact data."""
        ...

    async def retrieve(self, namespace: str, artifact_id: str) -> bytes | None:
        """Retrieve artifact data."""
        ...

    async def delete(self, namespace: str, artifact_id: str) -> None:
        """Delete artifact."""
        ...

    async def list(self, namespace: str) -> list[str]:
        """List artifact IDs."""
        ...


@runtime_checkable
class SandboxAbstraction(Protocol):
    """Sandbox abstraction for tenant-scoped sandbox management."""

    async def create(self, namespace: str, sandbox_id: str, config: dict) -> str:
        """Create sandbox."""
        ...

    async def destroy(self, namespace: str, sandbox_id: str) -> None:
        """Destroy sandbox."""
        ...

    async def get_status(self, namespace: str, sandbox_id: str) -> SandboxStatus:
        """Get sandbox status."""
        ...


@runtime_checkable
class WorkflowAbstraction(Protocol):
    """Workflow abstraction for tenant-scoped workflow management."""

    async def start(self, namespace: str, workflow_id: str, input: dict) -> str:
        """Start workflow execution."""
        ...

    async def get_status(self, namespace: str, execution_id: str) -> WorkflowStatus:
        """Get workflow execution status."""
        ...

    async def cancel(self, namespace: str, execution_id: str) -> None:
        """Cancel workflow execution."""
        ...


@dataclass
class RedisCache:
    """Redis-based cache implementation using tenant-scoped namespaces."""

    redis: Redis

    async def get(self, namespace: str, key: str) -> Any | None:
        """Get value from cache."""
        full_key = f"{namespace}:{key}"
        raw = await self.redis.get(full_key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    async def set(self, namespace: str, key: str, value: Any, ttl: int) -> None:
        """Set value in cache with TTL."""
        full_key = f"{namespace}:{key}"
        if isinstance(value, (str, int, float, bool)):
            await self.redis.setex(full_key, ttl, str(value))
        else:
            await self.redis.setex(full_key, ttl, json.dumps(value))

    async def delete(self, namespace: str, key: str) -> None:
        """Delete value from cache."""
        full_key = f"{namespace}:{key}"
        await self.redis.delete(full_key)

    async def exists(self, namespace: str, key: str) -> bool:
        """Check if key exists in cache."""
        full_key = f"{namespace}:{key}"
        return await self.redis.exists(full_key) == 1


@dataclass
class RedisLock:
    """Redis-based lock implementation using tenant-scoped namespaces."""

    redis: Redis

    async def acquire(self, namespace: str, lock_name: str, ttl: int) -> bool:
        """Acquire lock with TTL."""
        full_key = f"{namespace}:lock:{lock_name}"
        result = await self.redis.set(full_key, "1", nx=True, ex=ttl)
        return result is True

    async def release(self, namespace: str, lock_name: str) -> None:
        """Release lock."""
        full_key = f"{namespace}:lock:{lock_name}"
        await self.redis.delete(full_key)

    async def is_locked(self, namespace: str, lock_name: str) -> bool:
        """Check if lock is held."""
        full_key = f"{namespace}:lock:{lock_name}"
        return await self.redis.exists(full_key) == 1


@dataclass
class RedisRateLimit:
    """Redis-based rate limit implementation using tenant-scoped namespaces."""

    redis: Redis

    async def check(self, namespace: str, limit_id: str, limit: int, window: int) -> bool:
        """Check if rate limit allows operation."""
        full_key = f"{namespace}:rate_limit:{limit_id}"
        current = await self.redis.incr(full_key)
        if current == 1:
            await self.redis.expire(full_key, window)
        return current <= limit

    async def increment(self, namespace: str, limit_id: str) -> int:
        """Increment rate limit counter."""
        full_key = f"{namespace}:rate_limit:{limit_id}"
        return await self.redis.incr(full_key)

    async def reset(self, namespace: str, limit_id: str) -> None:
        """Reset rate limit counter."""
        full_key = f"{namespace}:rate_limit:{limit_id}"
        await self.redis.delete(full_key)


@dataclass
class RedisArtifact:
    """Redis-based artifact storage implementation using tenant-scoped namespaces."""

    redis: Redis

    async def store(self, namespace: str, artifact_id: str, data: bytes, ttl: int) -> None:
        """Store artifact data."""
        full_key = f"{namespace}:artifact:{artifact_id}"
        await self.redis.setex(full_key, ttl, data)

    async def retrieve(self, namespace: str, artifact_id: str) -> bytes | None:
        """Retrieve artifact data."""
        full_key = f"{namespace}:artifact:{artifact_id}"
        return await self.redis.get(full_key)

    async def delete(self, namespace: str, artifact_id: str) -> None:
        """Delete artifact."""
        full_key = f"{namespace}:artifact:{artifact_id}"
        await self.redis.delete(full_key)

    async def list(self, namespace: str) -> list[str]:
        """List artifact IDs."""
        pattern = f"{namespace}:artifact:*"
        keys = []
        async for key in self.redis.scan_iter(match=pattern):
            key_str = key.decode() if isinstance(key, bytes) else str(key)
            artifact_id = key_str.split(":")[-1]
            keys.append(artifact_id)
        return keys


@dataclass
class RedisSandbox:
    """Redis-based sandbox management implementation using tenant-scoped namespaces."""

    redis: Redis

    async def create(self, namespace: str, sandbox_id: str, config: dict) -> str:
        """Create sandbox."""
        full_key = f"{namespace}:sandbox:{sandbox_id}"
        status_key = f"{full_key}:status"
        config_key = f"{full_key}:config"
        await self.redis.set(status_key, SandboxStatus.CREATING.value)
        await self.redis.set(config_key, json.dumps(config))
        return sandbox_id

    async def destroy(self, namespace: str, sandbox_id: str) -> None:
        """Destroy sandbox."""
        full_key = f"{namespace}:sandbox:{sandbox_id}"
        status_key = f"{full_key}:status"
        config_key = f"{full_key}:config"
        await self.redis.set(status_key, SandboxStatus.DESTROYED.value)
        await self.redis.delete(config_key)

    async def get_status(self, namespace: str, sandbox_id: str) -> SandboxStatus:
        """Get sandbox status."""
        full_key = f"{namespace}:sandbox:{sandbox_id}"
        status_key = f"{full_key}:status"
        status_raw = await self.redis.get(status_key)
        if status_raw is None:
            return SandboxStatus.FAILED
        return SandboxStatus(status_raw.decode() if isinstance(status_raw, bytes) else status_raw)


@dataclass
class RedisWorkflow:
    """Redis-based workflow management implementation using tenant-scoped namespaces."""

    redis: Redis

    async def start(self, namespace: str, workflow_id: str, input: dict) -> str:
        """Start workflow execution."""
        execution_id = f"exec_{workflow_id}_{hash(str(input))}"
        full_key = f"{namespace}:workflow:{execution_id}"
        status_key = f"{full_key}:status"
        input_key = f"{full_key}:input"
        await self.redis.set(status_key, WorkflowStatus.PENDING.value)
        await self.redis.set(input_key, json.dumps(input))
        return execution_id

    async def get_status(self, namespace: str, execution_id: str) -> WorkflowStatus:
        """Get workflow execution status."""
        full_key = f"{namespace}:workflow:{execution_id}"
        status_key = f"{full_key}:status"
        status_raw = await self.redis.get(status_key)
        if status_raw is None:
            return WorkflowStatus.FAILED
        return WorkflowStatus(status_raw.decode() if isinstance(status_raw, bytes) else status_raw)

    async def cancel(self, namespace: str, execution_id: str) -> None:
        """Cancel workflow execution."""
        full_key = f"{namespace}:workflow:{execution_id}"
        status_key = f"{full_key}:status"
        await self.redis.set(status_key, WorkflowStatus.CANCELLED.value)
