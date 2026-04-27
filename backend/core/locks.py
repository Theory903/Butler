from __future__ import annotations

import asyncio
import random
import time
import uuid
from typing import Final

import structlog
from redis.asyncio import Redis

from core.middleware import get_tenant_context
from services.tenant.namespace import TenantNamespace

logger = structlog.get_logger(__name__)

_UNLOCK_SCRIPT: Final[str] = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

_EXTEND_SCRIPT: Final[str] = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("pexpire", KEYS[1], ARGV[2])
else
    return 0
end
"""

_GET_IF_OWNER_SCRIPT: Final[str] = """
local value = redis.call("get", KEYS[1])
if value == ARGV[1] then
    return value
else
    return nil
end
"""


class ButlerLockTimeoutError(TimeoutError):
    """Raised when a distributed lock cannot be acquired in time."""


class ButlerLockOwnershipError(RuntimeError):
    """Raised when an operation requires lock ownership but ownership is absent."""


class ButlerLock:
    """Redis-backed distributed lock with optional lease auto-renewal.

    Safety model:
    - acquire uses SET key value NX PX ttl_ms
    - release uses compare-and-delete Lua script
    - extend uses compare-and-pexpire Lua script
    - owner token is unique per lock instance

    Notes:
    - This is a single-Redis-instance lock, not Redlock.
    - Correctness depends on Redis availability and sensible TTL sizing.
    """

    def __init__(
        self,
        redis: Redis,
        name: str,
        *,
        tenant_id: str | None = None,
        ttl_ms: int = 10_000,
        timeout_ms: int = 5_000,
        retry_interval_ms: int = 100,
        retry_jitter_ms: int = 50,
        auto_renew: bool = False,
        renew_interval_ms: int | None = None,
    ) -> None:
        if not name or not name.strip():
            raise ValueError("Lock name must not be empty")
        if ttl_ms <= 0:
            raise ValueError("ttl_ms must be > 0")
        if timeout_ms < 0:
            raise ValueError("timeout_ms must be >= 0")
        if retry_interval_ms <= 0:
            raise ValueError("retry_interval_ms must be > 0")
        if retry_jitter_ms < 0:
            raise ValueError("retry_jitter_ms must be >= 0")

        if renew_interval_ms is None:
            renew_interval_ms = max(1_000, ttl_ms // 3)
        if renew_interval_ms <= 0:
            raise ValueError("renew_interval_ms must be > 0")
        if renew_interval_ms >= ttl_ms:
            raise ValueError("renew_interval_ms must be smaller than ttl_ms")

        self._redis = redis
        self._name_raw = name.strip()

        # Use tenant-scoped key if tenant_id provided, otherwise fall back to legacy format
        if tenant_id:
            namespace = TenantNamespace(tenant_id=tenant_id)
            self._name = namespace.lock("lock", self._name_raw)
        else:
            # Fallback to legacy format for backward compatibility
            # TODO: Remove this fallback once all callers provide tenant_id
            self._name = f"butler:lock:{self._name_raw}"

        self._ttl_ms = ttl_ms
        self._timeout_ms = timeout_ms
        self._retry_interval_ms = retry_interval_ms
        self._retry_jitter_ms = retry_jitter_ms
        self._auto_renew = auto_renew
        self._renew_interval_ms = renew_interval_ms

        self._id = str(uuid.uuid4())
        self._owned = False
        self._renew_task: asyncio.Task[None] | None = None

    @property
    def key(self) -> str:
        return self._name

    @property
    def owner_token(self) -> str:
        return self._id

    @property
    def owned(self) -> bool:
        return self._owned

    async def __aenter__(self) -> ButlerLock:
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            await self.release()
        except Exception:
            logger.exception("butler_lock_release_failed", lock_name=self._name)

    async def acquire(self) -> None:
        """Acquire the lock or raise ButlerLockTimeoutError."""
        if self._owned:
            logger.debug("butler_lock_already_owned", lock_name=self._name)
            return

        started = time.perf_counter()

        while True:
            ok = await self._redis.set(
                self._name,
                self._id,
                px=self._ttl_ms,
                nx=True,
            )
            if ok:
                self._owned = True
                logger.info(
                    "butler_lock_acquired",
                    lock_name=self._name,
                    ttl_ms=self._ttl_ms,
                    wait_ms=round((time.perf_counter() - started) * 1000, 2),
                    auto_renew=self._auto_renew,
                )
                if self._auto_renew:
                    self._start_renew_loop()
                return

            elapsed_ms = (time.perf_counter() - started) * 1000
            if elapsed_ms >= self._timeout_ms:
                logger.warning(
                    "butler_lock_acquire_timeout",
                    lock_name=self._name,
                    timeout_ms=self._timeout_ms,
                )
                raise ButlerLockTimeoutError(f"Could not acquire lock: {self._name}")

            sleep_ms = self._retry_interval_ms + random.randint(0, self._retry_jitter_ms)
            remaining_ms = max(0.0, self._timeout_ms - elapsed_ms)
            await asyncio.sleep(min(sleep_ms, remaining_ms) / 1000.0)

    async def release(self) -> bool:
        """Release the lock if owned by this instance."""
        if self._renew_task is not None:
            self._renew_task.cancel()
            try:
                await self._renew_task
            except asyncio.CancelledError:
                pass
            finally:
                self._renew_task = None

        if not self._owned:
            return False

        result = await self._redis.eval(_UNLOCK_SCRIPT, 1, self._name, self._id)
        released = bool(result)
        self._owned = False

        logger.info(
            "butler_lock_released",
            lock_name=self._name,
            released=released,
        )
        return released

    async def extend(self, ttl_ms: int | None = None) -> bool:
        """Extend the lease if this instance still owns the lock."""
        if not self._owned:
            raise ButlerLockOwnershipError(f"Lock is not owned: {self._name}")

        lease_ms = ttl_ms if ttl_ms is not None else self._ttl_ms
        if lease_ms <= 0:
            raise ValueError("ttl_ms must be > 0")

        result = await self._redis.eval(
            _EXTEND_SCRIPT,
            1,
            self._name,
            self._id,
            str(lease_ms),
        )
        extended = bool(result)

        if not extended:
            self._owned = False
            logger.warning(
                "butler_lock_extend_failed",
                lock_name=self._name,
                ttl_ms=lease_ms,
            )
            return False

        logger.debug(
            "butler_lock_extended",
            lock_name=self._name,
            ttl_ms=lease_ms,
        )
        return True

    async def is_owner(self) -> bool:
        """Return whether this lock instance still owns the Redis key."""
        result = await self._redis.eval(_GET_IF_OWNER_SCRIPT, 1, self._name, self._id)
        owned = result is not None
        if self._owned and not owned:
            self._owned = False
        return owned

    def _start_renew_loop(self) -> None:
        if self._renew_task is None:
            self._renew_task = asyncio.create_task(self._renew_loop())

    async def _renew_loop(self) -> None:
        try:
            while self._owned:
                await asyncio.sleep(self._renew_interval_ms / 1000.0)
                if not self._owned:
                    break

                extended = await self.extend()
                if not extended:
                    logger.warning(
                        "butler_lock_lost_during_renew",
                        lock_name=self._name,
                    )
                    break
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "butler_lock_renew_loop_failed",
                lock_name=self._name,
            )


class LockManager:
    """Factory for Butler distributed locks."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def get_lock(self, name: str, tenant_id: str | None = None, **kwargs) -> ButlerLock:
        """Get a tenant-scoped lock.

        Args:
            name: Lock resource name
            tenant_id: Optional tenant ID for multi-tenant isolation. If not provided,
                      will attempt to get from current TenantContext.
            **kwargs: Additional arguments passed to ButlerLock
        """
        if tenant_id is None:
            # Try to get tenant_id from current context
            ctx = get_tenant_context()
            if ctx is not None:
                tenant_id = ctx.tenant_id

        return ButlerLock(self._redis, name, tenant_id=tenant_id, **kwargs)
