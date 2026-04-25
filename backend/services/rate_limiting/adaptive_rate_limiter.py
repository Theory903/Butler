"""
Adaptive Rate Limiter - Load-Aware Rate Limiting

Implements adaptive rate limiting that adjusts based on system load.
Supports dynamic limit adjustment and load-aware throttling.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class LoadLevel(StrEnum):
    """System load level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class RateLimitConfig:
    """Rate limit configuration."""

    requests_per_second: int
    burst_size: int
    adaptive: bool
    load_adjustment_factor: float


@dataclass(frozen=True, slots=True)
class RateLimitState:
    """Rate limit state."""

    current_limit: int
    current_load: LoadLevel
    last_adjusted_at: datetime
    requests_in_window: int
    window_start: datetime


class AdaptiveRateLimiter:
    """
    Adaptive rate limiter with load-aware limits.

    Features:
    - Load-aware limit adjustment
    - Burst handling
    - Dynamic scaling
    - Per-key limits
    """

    def __init__(
        self,
        default_rps: int = 100,
        default_burst: int = 200,
        adaptive: bool = True,
    ) -> None:
        """Initialize adaptive rate limiter."""
        self._default_config = RateLimitConfig(
            requests_per_second=default_rps,
            burst_size=default_burst,
            adaptive=adaptive,
            load_adjustment_factor=0.5,
        )
        self._states: dict[str, RateLimitState] = {}
        self._system_load = LoadLevel.LOW
        self._load_monitor_task: asyncio.Task | None = None

    async def check_rate_limit(
        self,
        key: str,
        config: RateLimitConfig | None = None,
    ) -> tuple[bool, int, str]:
        """
        Check if request is allowed under rate limit.

        Args:
            key: Rate limit key (user_id, tenant_id, etc.)
            config: Custom configuration (uses default if None)

        Returns:
            Tuple of (allowed, remaining, reset_time)
        """
        config = config or self._default_config
        now = datetime.now(UTC)

        # Get or create state
        if key not in self._states:
            self._states[key] = RateLimitState(
                current_limit=config.requests_per_second,
                current_load=self._system_load,
                last_adjusted_at=now,
                requests_in_window=0,
                window_start=now,
            )

        state = self._states[key]

        # Adjust limit if adaptive and load changed
        if config.adaptive and state.current_load != self._system_load:
            state = self._adjust_limit(state, config, self._system_load)
            self._states[key] = state

        # Check if window expired
        window_age = (now - state.window_start).total_seconds()
        if window_age >= 1.0:
            state = RateLimitState(
                current_limit=state.current_limit,
                current_load=state.current_load,
                last_adjusted_at=state.last_adjusted_at,
                requests_in_window=0,
                window_start=now,
            )
            self._states[key] = state

        # Check if request allowed
        if state.requests_in_window < state.current_limit:
            state = RateLimitState(
                current_limit=state.current_limit,
                current_load=state.current_load,
                last_adjusted_at=state.last_adjusted_at,
                requests_in_window=state.requests_in_window + 1,
                window_start=state.window_start,
            )
            self._states[key] = state

            remaining = state.current_limit - state.requests_in_window
            reset_time = state.window_start.strftime("%Y-%m-%dT%H:%M:%SZ")

            return True, remaining, reset_time
        remaining = 0
        reset_time = state.window_start.strftime("%Y-%m-%dT%H:%M:%SZ")

        logger.debug(
            "rate_limit_exceeded",
            key=key,
            limit=state.current_limit,
            requests=state.requests_in_window,
        )

        return False, remaining, reset_time

    def _adjust_limit(
        self,
        state: RateLimitState,
        config: RateLimitConfig,
        new_load: LoadLevel,
    ) -> RateLimitState:
        """
        Adjust rate limit based on load.

        Args:
            state: Current state
            config: Rate limit configuration
            new_load: New load level

        Returns:
            Updated state
        """
        base_limit = config.requests_per_second
        adjustment_factor = config.load_adjustment_factor

        if new_load == LoadLevel.LOW:
            new_limit = int(base_limit * 1.5)
        elif new_load == LoadLevel.MEDIUM:
            new_limit = base_limit
        elif new_load == LoadLevel.HIGH:
            new_limit = int(base_limit * (1 - adjustment_factor))
        else:  # CRITICAL
            new_limit = int(base_limit * (1 - adjustment_factor * 2))

        new_limit = max(new_limit, 10)  # Minimum limit

        return RateLimitState(
            current_limit=new_limit,
            current_load=new_load,
            last_adjusted_at=datetime.now(UTC),
            requests_in_window=state.requests_in_window,
            window_start=state.window_start,
        )

    def set_system_load(self, load: LoadLevel) -> None:
        """
        Set current system load level.

        Args:
            load: System load level
        """
        self._system_load = load

        logger.info(
            "system_load_updated",
            load=load,
        )

    async def monitor_load(
        self,
        check_interval_seconds: int = 30,
    ) -> None:
        """
        Monitor system load and adjust limits.

        Args:
            check_interval_seconds: Check interval
        """

        async def _monitor_loop():
            while True:
                await asyncio.sleep(check_interval_seconds)

                # In production, this would check actual system metrics
                # For now, simulate load changes
                current_load = self._system_load

                # Simple load simulation
                if current_load == LoadLevel.LOW:
                    self.set_system_load(LoadLevel.MEDIUM)
                elif current_load == LoadLevel.MEDIUM:
                    self.set_system_load(LoadLevel.HIGH)
                elif current_load == LoadLevel.HIGH:
                    self.set_system_load(LoadLevel.LOW)

        if self._load_monitor_task is None or self._load_monitor_task.done():
            self._load_monitor_task = asyncio.create_task(_monitor_loop())

            logger.info(
                "load_monitoring_started",
                interval_seconds=check_interval_seconds,
            )

    def stop_load_monitoring(self) -> None:
        """Stop load monitoring."""
        if self._load_monitor_task and not self._load_monitor_task.done():
            self._load_monitor_task.cancel()

            logger.info("load_monitoring_stopped")

    def get_rate_limit_stats(self) -> dict[str, Any]:
        """
        Get rate limiting statistics.

        Returns:
            Rate limiting statistics
        """
        total_keys = len(self._states)

        load_counts: dict[str, int] = {}
        for state in self._states.values():
            load_counts[state.current_load] = load_counts.get(state.current_load, 0) + 1

        return {
            "total_rate_limited_keys": total_keys,
            "system_load": self._system_load,
            "load_distribution": load_counts,
            "default_rps": self._default_config.requests_per_second,
            "adaptive_enabled": self._default_config.adaptive,
        }
