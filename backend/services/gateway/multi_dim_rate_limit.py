"""
Multi-Dimensional Rate Limiting

Rate limiting across multiple dimensions:
- Tenant level
- User level
- IP level
- Tool level
- API endpoint level
- Resource level

Uses Redis with sliding window algorithm.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

import structlog
from redis.asyncio import Redis

from services.tenant.namespace import get_tenant_namespace

logger = structlog.get_logger(__name__)


class RateLimitDimension(StrEnum):
    """Rate limiting dimensions."""

    TENANT = "tenant"
    USER = "user"
    IP = "ip"
    TOOL = "tool"
    API = "api"
    RESOURCE = "resource"


class RateLimitExceededError(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        dimension: RateLimitDimension,
        identifier: str,
        limit: int,
        window: str,
    ) -> None:
        self.dimension = dimension
        self.identifier = identifier
        self.limit = limit
        self.window = window
        super().__init__(
            f"Rate limit exceeded for {dimension.value}:{identifier} - {limit} per {window}"
        )


@dataclass(frozen=True, slots=True)
class RateLimitRule:
    """Rate limit rule configuration."""

    dimension: RateLimitDimension
    limit: int
    window: str  # e.g., "1m", "1h", "1d"


# Default rate limit rules
DEFAULT_RATE_LIMIT_RULES = {
    # Tenant-level limits
    RateLimitDimension.TENANT: [
        RateLimitRule(RateLimitDimension.TENANT, 1000, "1m"),
        RateLimitRule(RateLimitDimension.TENANT, 10000, "1h"),
        RateLimitRule(RateLimitDimension.TENANT, 100000, "1d"),
    ],
    # User-level limits
    RateLimitDimension.USER: [
        RateLimitRule(RateLimitDimension.USER, 100, "1m"),
        RateLimitRule(RateLimitDimension.USER, 1000, "1h"),
        RateLimitRule(RateLimitDimension.USER, 10000, "1d"),
    ],
    # IP-level limits
    RateLimitDimension.IP: [
        RateLimitRule(RateLimitDimension.IP, 50, "1m"),
        RateLimitRule(RateLimitDimension.IP, 500, "1h"),
    ],
    # Tool-level limits
    RateLimitDimension.TOOL: [
        RateLimitRule(RateLimitDimension.TOOL, 20, "1m"),
        RateLimitRule(RateLimitDimension.TOOL, 200, "1h"),
    ],
    # API-level limits
    RateLimitDimension.API: [
        RateLimitRule(RateLimitDimension.API, 1000, "1m"),
    ],
    # Resource-level limits
    RateLimitDimension.RESOURCE: [
        RateLimitRule(RateLimitDimension.RESOURCE, 50, "1m"),
    ],
}


class MultiDimensionRateLimiter:
    """Multi-dimensional rate limiter using Redis sliding window."""

    def __init__(
        self,
        redis: Redis,
        rules: dict[RateLimitDimension, list[RateLimitRule]] | None = None,
    ) -> None:
        """
        Initialize multi-dimensional rate limiter.

        Args:
            redis: Redis client
            rules: Custom rate limit rules (uses defaults if None)
        """
        self._redis = redis
        self._rules = rules or DEFAULT_RATE_LIMIT_RULES

    def _get_rate_limit_key(
        self,
        dimension: RateLimitDimension,
        identifier: str,
        tenant_id: str | None = None,
    ) -> str:
        """Generate Redis key for rate limiting."""
        if tenant_id:
            namespace = get_tenant_namespace(tenant_id)
            return f"{namespace.prefix}:ratelimit:{dimension.value}:{identifier}"
        return f"global:ratelimit:{dimension.value}:{identifier}"

    def _parse_window(self, window: str) -> int:
        """Parse window string to seconds."""
        if window == "1m":
            return 60
        if window == "1h":
            return 3600
        if window == "1d":
            return 86400
        return 60  # default to 1 minute

    async def check(
        self,
        dimensions: dict[RateLimitDimension, str],
        tenant_id: str | None = None,
    ) -> None:
        """
        Check rate limits across multiple dimensions.

        Args:
            dimensions: Dictionary of dimension -> identifier
            tenant_id: Optional tenant ID for tenant-scoped limits

        Raises:
            RateLimitExceededError: If any dimension exceeds limit
        """
        for dimension, identifier in dimensions.items():
            rules = self._rules.get(dimension, [])
            for rule in rules:
                await self._check_single_rule(
                    dimension,
                    identifier,
                    rule,
                    tenant_id,
                )

    async def _check_single_rule(
        self,
        dimension: RateLimitDimension,
        identifier: str,
        rule: RateLimitRule,
        tenant_id: str | None = None,
    ) -> None:
        """Check a single rate limit rule."""
        key = self._get_rate_limit_key(dimension, identifier, tenant_id)
        window_seconds = self._parse_window(rule.window)
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

        if current_count >= rule.limit:
            logger.warning(
                "rate_limit_exceeded",
                dimension=dimension.value,
                identifier=identifier,
                current=current_count,
                limit=rule.limit,
                window=rule.window,
                tenant_id=tenant_id,
            )
            raise RateLimitExceededError(
                dimension,
                identifier,
                rule.limit,
                rule.window,
            )

        logger.debug(
            "rate_limit_check_passed",
            dimension=dimension.value,
            identifier=identifier,
            current=current_count,
            limit=rule.limit,
            window=rule.window,
        )

    async def get_usage(
        self,
        dimension: RateLimitDimension,
        identifier: str,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Get current usage statistics for a dimension.

        Args:
            dimension: Rate limit dimension
            identifier: Identifier for the dimension
            tenant_id: Optional tenant ID

        Returns:
            Dictionary with usage statistics
        """
        rules = self._rules.get(dimension, [])
        usage_stats = []

        for rule in rules:
            key = self._get_rate_limit_key(dimension, identifier, tenant_id)
            window_seconds = self._parse_window(rule.window)
            current_time = datetime.now().timestamp()

            # Count requests in window
            current_count = await self._redis.zcount(
                key,
                current_time - window_seconds,
                current_time,
            )

            usage_stats.append(
                {
                    "window": rule.window,
                    "limit": rule.limit,
                    "current": current_count,
                    "remaining": max(0, rule.limit - current_count),
                }
            )

        return {
            "dimension": dimension.value,
            "identifier": identifier,
            "rules": usage_stats,
        }

    async def reset(
        self,
        dimension: RateLimitDimension,
        identifier: str,
        tenant_id: str | None = None,
    ) -> None:
        """
        Reset rate limit for a specific dimension and identifier.

        Args:
            dimension: Rate limit dimension
            identifier: Identifier for the dimension
            tenant_id: Optional tenant ID
        """
        rules = self._rules.get(dimension, [])
        for rule in rules:
            key = self._get_rate_limit_key(dimension, identifier, tenant_id)
            await self._redis.delete(key)

        logger.info(
            "rate_limit_reset",
            dimension=dimension.value,
            identifier=identifier,
            tenant_id=tenant_id,
        )


# Singleton instance
_rate_limiter: MultiDimensionRateLimiter | None = None


def get_multi_dim_rate_limiter(redis: Redis) -> MultiDimensionRateLimiter:
    """Get the singleton multi-dimensional rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = MultiDimensionRateLimiter(redis)
    return _rate_limiter
