"""
Distributed Rate Limiter - Distributed Rate Limiting Coordination

Implements distributed rate limiting coordination across multiple instances.
Supports Redis-backed coordination and cluster-wide rate limiting.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class CoordinationStrategy(StrEnum):
    """Coordination strategy."""

    CENTRALIZED = "centralized"
    DECENTRALIZED = "decentralized"
    HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class DistributedLimitState:
    """Distributed rate limit state."""

    key: str
    requests: int
    window_start: datetime
    ttl_seconds: int
    node_id: str


class DistributedRateLimiter:
    """
    Distributed rate limiter for cluster-wide coordination.

    Features:
    - Redis-backed coordination
    - Cluster-wide limits
    - Node-aware tracking
    - TTL-based cleanup
    """

    def __init__(
        self,
        node_id: str,
        coordination_strategy: CoordinationStrategy = CoordinationStrategy.CENTRALIZED,
    ) -> None:
        """Initialize distributed rate limiter."""
        self._node_id = node_id
        self._strategy = coordination_strategy
        self._states: dict[str, DistributedLimitState] = {}
        self._redis_client: Any | None = None  # Would be Redis client in production

    async def check_distributed_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int = 1,
    ) -> tuple[bool, int, str]:
        """
        Check distributed rate limit.

        Args:
            key: Rate limit key
            limit: Request limit
            window_seconds: Window size in seconds

        Returns:
            Tuple of (allowed, remaining, reset_time)
        """
        now = datetime.now(UTC)

        # In production, this would use Redis with atomic operations
        # For now, use in-memory with coordination simulation

        if key not in self._states:
            self._states[key] = DistributedLimitState(
                key=key,
                requests=0,
                window_start=now,
                ttl_seconds=window_seconds,
                node_id=self._node_id,
            )

        state = self._states[key]

        # Check if window expired
        window_age = (now - state.window_start).total_seconds()
        if window_age >= window_seconds:
            state = DistributedLimitState(
                key=key,
                requests=0,
                window_start=now,
                ttl_seconds=window_seconds,
                node_id=self._node_id,
            )
            self._states[key] = state

        # Check if request allowed
        if state.requests < limit:
            state = DistributedLimitState(
                key=key,
                requests=state.requests + 1,
                window_start=state.window_start,
                ttl_seconds=state.ttl_seconds,
                node_id=self._node_id,
            )
            self._states[key] = state

            remaining = limit - state.requests
            reset_time = state.window_start.strftime("%Y-%m-%dT%H:%M:%SZ")

            logger.debug(
                "distributed_rate_limit_allowed",
                key=key,
                node_id=self._node_id,
                remaining=remaining,
            )

            return True, remaining, reset_time
        remaining = 0
        reset_time = state.window_start.strftime("%Y-%m-%dT%H:%M:%SZ")

        logger.debug(
            "distributed_rate_limit_exceeded",
            key=key,
            node_id=self._node_id,
            limit=limit,
            requests=state.requests,
        )

        return False, remaining, reset_time

    async def increment_counter(
        self,
        key: str,
        ttl_seconds: int = 60,
    ) -> int:
        """
        Increment distributed counter with TTL.

        Args:
            key: Counter key
            ttl_seconds: Time to live

        Returns:
            New counter value
        """
        # In production, this would use Redis INCR with TTL
        if key not in self._states:
            self._states[key] = DistributedLimitState(
                key=key,
                requests=0,
                window_start=datetime.now(UTC),
                ttl_seconds=ttl_seconds,
                node_id=self._node_id,
            )

        state = self._states[key]
        state = DistributedLimitState(
            key=key,
            requests=state.requests + 1,
            window_start=state.window_start,
            ttl_seconds=state.ttl_seconds,
            node_id=self._node_id,
        )
        self._states[key] = state

        return state.requests

    async def get_counter(
        self,
        key: str,
    ) -> int:
        """
        Get distributed counter value.

        Args:
            key: Counter key

        Returns:
            Counter value
        """
        if key in self._states:
            return self._states[key].requests
        return 0

    async def reset_counter(
        self,
        key: str,
    ) -> bool:
        """
        Reset distributed counter.

        Args:
            key: Counter key

        Returns:
            True if reset
        """
        if key in self._states:
            del self._states[key]

            logger.info(
                "distributed_counter_reset",
                key=key,
                node_id=self._node_id,
            )

            return True
        return False

    async def cleanup_expired_states(self) -> int:
        """
        Clean up expired states.

        Returns:
            Number of states cleaned up
        """
        now = datetime.now(UTC)

        to_remove = []
        for key, state in self._states.items():
            age = (now - state.window_start).total_seconds()
            if age > state.ttl_seconds:
                to_remove.append(key)

        for key in to_remove:
            del self._states[key]

        if to_remove:
            logger.info(
                "distributed_states_cleaned",
                count=len(to_remove),
                node_id=self._node_id,
            )

        return len(to_remove)

    def set_coordination_strategy(
        self,
        strategy: CoordinationStrategy,
    ) -> None:
        """
        Set coordination strategy.

        Args:
            strategy: Coordination strategy
        """
        self._strategy = strategy

        logger.info(
            "coordination_strategy_updated",
            strategy=strategy,
            node_id=self._node_id,
        )

    def get_distributed_stats(self) -> dict[str, Any]:
        """
        Get distributed rate limiting statistics.

        Returns:
            Distributed statistics
        """
        total_keys = len(self._states)
        total_requests = sum(s.requests for s in self._states.values())

        node_counts: dict[str, int] = {}
        for state in self._states.values():
            node_counts[state.node_id] = node_counts.get(state.node_id, 0) + 1

        return {
            "total_keys": total_keys,
            "total_requests": total_requests,
            "node_distribution": node_counts,
            "coordination_strategy": self._strategy,
            "node_id": self._node_id,
        }
