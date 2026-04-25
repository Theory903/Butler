"""
Tenant Quota Service - Rate Limit, Quota, and Concurrency Control

Enforces per-tenant rate limits, quotas, and concurrency limits.
Uses shared worker pools with tenant-level semaphores - no per-tenant thread pools.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from services.tenant.namespace import get_tenant_namespace

logger = structlog.get_logger(__name__)


class ResourceType(StrEnum):
    """Resource types for quota enforcement."""

    API_REQUESTS = "api_requests"
    MODEL_CALLS = "model_calls"
    TOOL_EXECUTIONS = "tool_executions"
    CODE_SANDBOXES = "code_sandboxes"
    WORKFLOW_EXECUTIONS = "workflow_executions"


class QuotaExceededError(Exception):
    """Raised when tenant quota is exceeded."""

    def __init__(self, resource: str, limit: int, current: int) -> None:
        self.resource = resource
        self.limit = limit
        self.current = current
        super().__init__(f"Quota exceeded for {resource}: {current}/{limit}")


class RateLimitExceededError(Exception):
    """Raised when tenant rate limit is exceeded."""

    def __init__(self, resource: str, limit: int, window: str) -> None:
        self.resource = resource
        self.limit = limit
        self.window = window
        super().__init__(f"Rate limit exceeded for {resource}: {limit} per {window}")


class ConcurrencyLimitExceededError(Exception):
    """Raised when tenant concurrency limit is exceeded."""

    def __init__(self, resource: str, limit: int, active: int) -> None:
        self.resource = resource
        self.limit = limit
        self.active = active
        super().__init__(f"Concurrency limit exceeded for {resource}: {active}/{limit}")


@dataclass(frozen=True, slots=True)
class QuotaLimit:
    """Quota limit configuration."""

    resource: ResourceType
    limit: int
    period: str  # e.g., "daily", "monthly", "unlimited"


@dataclass(frozen=True, slots=True)
class RateLimit:
    """Rate limit configuration."""

    resource: ResourceType
    requests: int
    window: str  # e.g., "1m", "1h", "1d"


@dataclass(frozen=True, slots=True)
class ConcurrencyLimit:
    """Concurrency limit configuration."""

    resource: ResourceType
    limit: int


# Default limits per plan
DEFAULT_QUOTA_LIMITS: dict[str, list[QuotaLimit]] = {
    "free": [
        QuotaLimit(ResourceType.API_REQUESTS, 1000, "daily"),
        QuotaLimit(ResourceType.MODEL_CALLS, 100, "daily"),
        QuotaLimit(ResourceType.TOOL_EXECUTIONS, 50, "daily"),
        QuotaLimit(ResourceType.CODE_SANDBOXES, 0, "daily"),
        QuotaLimit(ResourceType.WORKFLOW_EXECUTIONS, 10, "daily"),
    ],
    "pro": [
        QuotaLimit(ResourceType.API_REQUESTS, 10000, "daily"),
        QuotaLimit(ResourceType.MODEL_CALLS, 1000, "daily"),
        QuotaLimit(ResourceType.TOOL_EXECUTIONS, 500, "daily"),
        QuotaLimit(ResourceType.CODE_SANDBOXES, 10, "daily"),
        QuotaLimit(ResourceType.WORKFLOW_EXECUTIONS, 100, "daily"),
    ],
    "operator": [
        QuotaLimit(ResourceType.API_REQUESTS, 100000, "daily"),
        QuotaLimit(ResourceType.MODEL_CALLS, 10000, "daily"),
        QuotaLimit(ResourceType.TOOL_EXECUTIONS, 5000, "daily"),
        QuotaLimit(ResourceType.CODE_SANDBOXES, 100, "daily"),
        QuotaLimit(ResourceType.WORKFLOW_EXECUTIONS, 1000, "daily"),
    ],
    "enterprise": [
        QuotaLimit(ResourceType.API_REQUESTS, 0, "unlimited"),
        QuotaLimit(ResourceType.MODEL_CALLS, 0, "unlimited"),
        QuotaLimit(ResourceType.TOOL_EXECUTIONS, 0, "unlimited"),
        QuotaLimit(ResourceType.CODE_SANDBOXES, 0, "unlimited"),
        QuotaLimit(ResourceType.WORKFLOW_EXECUTIONS, 0, "unlimited"),
    ],
}


DEFAULT_RATE_LIMITS: dict[str, list[RateLimit]] = {
    "free": [
        RateLimit(ResourceType.API_REQUESTS, 10, "1m"),
        RateLimit(ResourceType.MODEL_CALLS, 5, "1m"),
    ],
    "pro": [
        RateLimit(ResourceType.API_REQUESTS, 100, "1m"),
        RateLimit(ResourceType.MODEL_CALLS, 50, "1m"),
    ],
    "operator": [
        RateLimit(ResourceType.API_REQUESTS, 1000, "1m"),
        RateLimit(ResourceType.MODEL_CALLS, 500, "1m"),
    ],
    "enterprise": [
        RateLimit(ResourceType.API_REQUESTS, 0, "unlimited"),
        RateLimit(ResourceType.MODEL_CALLS, 0, "unlimited"),
    ],
}


DEFAULT_CONCURRENCY_LIMITS: dict[str, list[ConcurrencyLimit]] = {
    "free": [
        ConcurrencyLimit(ResourceType.WORKFLOW_EXECUTIONS, 1),
        ConcurrencyLimit(ResourceType.CODE_SANDBOXES, 0),
    ],
    "pro": [
        ConcurrencyLimit(ResourceType.WORKFLOW_EXECUTIONS, 3),
        ConcurrencyLimit(ResourceType.CODE_SANDBOXES, 1),
    ],
    "operator": [
        ConcurrencyLimit(ResourceType.WORKFLOW_EXECUTIONS, 10),
        ConcurrencyLimit(ResourceType.CODE_SANDBOXES, 3),
    ],
    "enterprise": [
        ConcurrencyLimit(ResourceType.WORKFLOW_EXECUTIONS, 0),  # 0 = unlimited
        ConcurrencyLimit(ResourceType.CODE_SANDBOXES, 0),  # 0 = unlimited
    ],
}


class TenantQuotaService:
    """
    Tenant quota and rate limit enforcement service.

    Uses Redis for distributed rate limiting and concurrency control.
    Uses database for quota tracking.
    """

    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        plan: str = "free",
    ) -> None:
        """Initialize quota service with plan-based limits."""
        self._db = db
        self._redis = redis
        self.plan = plan
        self.quota_limits = DEFAULT_QUOTA_LIMITS.get(plan, DEFAULT_QUOTA_LIMITS["free"])
        self.rate_limits = DEFAULT_RATE_LIMITS.get(plan, DEFAULT_RATE_LIMITS["free"])
        self.concurrency_limits = DEFAULT_CONCURRENCY_LIMITS.get(
            plan, DEFAULT_CONCURRENCY_LIMITS["free"]
        )

    def _rate_limit_key(self, tenant_id: str, resource: ResourceType) -> str:
        """Generate Redis key for rate limiting using TenantNamespace."""
        namespace = get_tenant_namespace(tenant_id)
        return f"{namespace.prefix}:ratelimit:{resource}"

    def _quota_key(self, tenant_id: str, resource: ResourceType, period: str) -> str:
        """Generate Redis key for quota tracking using TenantNamespace."""
        namespace = get_tenant_namespace(tenant_id)
        return f"{namespace.prefix}:quota:{resource}:{period}"

    def _concurrency_key(self, tenant_id: str, resource: ResourceType) -> str:
        """Generate Redis key for concurrency semaphore using TenantNamespace."""
        namespace = get_tenant_namespace(tenant_id)
        return f"{namespace.prefix}:concurrency:{resource}"

    def _parse_window(self, window: str) -> int:
        """Parse window string to seconds."""
        if window == "1m":
            return 60
        if window == "1h":
            return 3600
        if window == "1d":
            return 86400
        return 60  # default to 1 minute

    async def check_rate(
        self,
        resource: ResourceType,
        tenant_id: str,
        units: int = 1,
    ) -> None:
        """
        Check if tenant is within rate limit.

        Uses Redis sliding window rate limiting.

        Args:
            resource: Resource type to check
            tenant_id: Tenant UUID
            units: Number of units to consume

        Raises:
            RateLimitExceededError: If rate limit exceeded
        """
        rate_limit = self.get_rate_limit(resource)

        if not rate_limit:
            # No rate limit configured
            return

        if rate_limit.requests == 0 and rate_limit.window == "unlimited":
            # Unlimited rate
            return

        key = self._rate_limit_key(tenant_id, resource)
        window_seconds = self._parse_window(rate_limit.window)
        current_time = datetime.now().timestamp()

        # Use Redis sliding window
        pipe = self._redis.pipeline()

        # Remove old entries outside the window
        pipe.zremrangebyscore(key, 0, current_time - window_seconds)

        # Count current requests in window
        pipe.zcard(key)

        # Add current request
        pipe.zadd(key, {str(current_time): current_time})

        # Set expiry
        pipe.expire(key, window_seconds + 1)

        results = await pipe.execute()

        current_count = results[1]

        if current_count + units > rate_limit.requests:
            logger.warning(
                "rate_limit_exceeded",
                tenant_id=tenant_id,
                resource=resource,
                current=current_count,
                limit=rate_limit.requests,
                window=rate_limit.window,
            )
            raise RateLimitExceededError(resource, rate_limit.requests, rate_limit.window)

        logger.debug(
            "rate_limit_check_passed",
            tenant_id=tenant_id,
            resource=resource,
            current=current_count,
            limit=rate_limit.requests,
        )

    async def check_quota(
        self,
        resource: ResourceType,
        tenant_id: str,
        units: int = 1,
    ) -> None:
        """
        Check if tenant has quota available.

        Uses Redis for quota tracking with daily/monthly reset.

        Args:
            resource: Resource type to check
            tenant_id: Tenant UUID
            units: Number of units to consume

        Raises:
            QuotaExceededError: If quota exceeded
        """
        quota_limit = self.get_quota_limit(resource)

        if not quota_limit:
            # No quota limit configured
            return

        if quota_limit.limit == 0 and quota_limit.period == "unlimited":
            # Unlimited quota
            return

        key = self._quota_key(tenant_id, resource, quota_limit.period)

        # Get current usage
        current = await self._redis.get(key)
        current_count = int(current) if current else 0

        if current_count + units > quota_limit.limit:
            logger.warning(
                "quota_exceeded",
                tenant_id=tenant_id,
                resource=resource,
                current=current_count,
                limit=quota_limit.limit,
                period=quota_limit.period,
            )
            raise QuotaExceededError(resource, quota_limit.limit, current_count)

        # Increment usage
        await self._redis.incrby(key, units)

        # Set expiry based on period
        if quota_limit.period == "daily":
            await self._redis.expire(key, 86400)
        elif quota_limit.period == "monthly":
            await self._redis.expire(key, 2592000)  # 30 days

        logger.debug(
            "quota_check_passed",
            tenant_id=tenant_id,
            resource=resource,
            current=current_count,
            limit=quota_limit.limit,
        )

    async def acquire_concurrency(
        self,
        resource: ResourceType,
        tenant_id: str,
        timeout: int = 30,
    ) -> str:
        """
        Acquire concurrency permit for resource.

        Uses Redis semaphore for distributed concurrency control.

        Args:
            resource: Resource type
            tenant_id: Tenant UUID
            timeout: Maximum time to wait for permit (in seconds)

        Returns:
            Permit ID for later release

        Raises:
            ConcurrencyLimitExceededError: If concurrency limit exceeded
        """
        concurrency_limit = self.get_concurrency_limit(resource)

        if not concurrency_limit:
            # No concurrency limit configured
            return "no-limit"

        if concurrency_limit.limit == 0:
            # Unlimited concurrency
            return "unlimited"

        key = self._concurrency_key(tenant_id, resource)

        # Try to acquire permit
        permit_key = f"{key}:permit:{datetime.now().timestamp()}"
        acquired = await self._redis.set(
            f"{key}:lock",
            "1",
            nx=True,
            ex=timeout,
        )

        if not acquired:
            # Check current active count
            active = await self._redis.zcard(key)
            logger.warning(
                "concurrency_limit_exceeded",
                tenant_id=tenant_id,
                resource=resource,
                active=active,
                limit=concurrency_limit.limit,
            )
            raise ConcurrencyLimitExceededError(resource, concurrency_limit.limit, active)

        # Add to active set
        await self._redis.zadd(key, {permit_key: datetime.now().timestamp()})

        # Check if we're over limit
        active_count = await self._redis.zcard(key)
        if active_count > concurrency_limit.limit:
            # Rollback
            await self._redis.zrem(key, permit_key)
            await self._redis.delete(f"{key}:lock")
            logger.warning(
                "concurrency_limit_exceeded_after_acquire",
                tenant_id=tenant_id,
                resource=resource,
                active=active_count,
                limit=concurrency_limit.limit,
            )
            raise ConcurrencyLimitExceededError(resource, concurrency_limit.limit, active_count)

        logger.debug(
            "concurrency_permit_acquired",
            tenant_id=tenant_id,
            resource=resource,
            active=active_count,
            limit=concurrency_limit.limit,
        )

        return permit_key

    async def release_concurrency(
        self,
        resource: ResourceType,
        tenant_id: str,
        permit_id: str,
    ) -> None:
        """
        Release concurrency permit.

        Args:
            resource: Resource type
            tenant_id: Tenant UUID
            permit_id: Permit ID from acquire_concurrency
        """
        if permit_id in ("no-limit", "unlimited"):
            return

        key = self._concurrency_key(tenant_id, resource)

        # Remove from active set
        await self._redis.zrem(key, permit_id)
        await self._redis.delete(f"{key}:lock")

        logger.debug(
            "concurrency_permit_released",
            tenant_id=tenant_id,
            resource=resource,
        )

    def get_quota_limit(self, resource: ResourceType) -> QuotaLimit | None:
        """Get quota limit for resource."""
        for limit in self.quota_limits:
            if limit.resource == resource:
                return limit
        return None

    def get_rate_limit(self, resource: ResourceType) -> RateLimit | None:
        """Get rate limit for resource."""
        for limit in self.rate_limits:
            if limit.resource == resource:
                return limit
        return None

    def get_concurrency_limit(self, resource: ResourceType) -> ConcurrencyLimit | None:
        """Get concurrency limit for resource."""
        for limit in self.concurrency_limits:
            if limit.resource == resource:
                return limit
        return None

    async def get_usage(
        self,
        tenant_id: str,
        resource: ResourceType,
    ) -> dict[str, Any]:
        """
        Get current usage statistics for a tenant and resource.

        Args:
            tenant_id: Tenant UUID
            resource: Resource type

        Returns:
            Dictionary with current usage, limits, and remaining
        """
        quota_limit = self.get_quota_limit(resource)
        rate_limit = self.get_rate_limit(resource)
        concurrency_limit = self.get_concurrency_limit(resource)

        # Get current quota usage
        if quota_limit and quota_limit.period != "unlimited":
            quota_key = self._quota_key(tenant_id, resource, quota_limit.period)
            quota_used = await self._redis.get(quota_key)
            quota_used = int(quota_used) if quota_used else 0
        else:
            quota_used = 0

        # Get current rate usage (last minute)
        if rate_limit and rate_limit.window != "unlimited":
            rate_key = self._rate_limit_key(tenant_id, resource)
            window_seconds = self._parse_window(rate_limit.window)
            current_time = datetime.now().timestamp()
            rate_used = await self._redis.zcount(
                rate_key,
                current_time - window_seconds,
                current_time,
            )
        else:
            rate_used = 0

        # Get current concurrency usage
        if concurrency_limit and concurrency_limit.limit != 0:
            concurrency_key = self._concurrency_key(tenant_id, resource)
            concurrency_used = await self._redis.zcard(concurrency_key)
        else:
            concurrency_used = 0

        return {
            "resource": resource,
            "tenant_id": tenant_id,
            "quota_limit": quota_limit.limit if quota_limit else 0,
            "quota_used": quota_used,
            "quota_remaining": (quota_limit.limit - quota_used) if quota_limit else 0,
            "quota_period": quota_limit.period if quota_limit else "unlimited",
            "rate_limit": rate_limit.requests if rate_limit else 0,
            "rate_used": rate_used,
            "rate_remaining": (rate_limit.requests - rate_used) if rate_limit else 0,
            "rate_window": rate_limit.window if rate_limit else "unlimited",
            "concurrency_limit": concurrency_limit.limit if concurrency_limit else 0,
            "concurrency_used": concurrency_used,
            "concurrency_remaining": (concurrency_limit.limit - concurrency_used)
            if concurrency_limit
            else 0,
        }
