"""
Cache Invalidation - Cache Invalidation Patterns

Implements cache invalidation patterns for cache consistency.
Supports time-based, event-based, and manual invalidation strategies.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class InvalidationStrategy(StrEnum):
    """Invalidation strategy."""

    TIME_BASED = "time_based"
    EVENT_BASED = "event_based"
    MANUAL = "manual"
    WRITE_THROUGH = "write_through"


@dataclass(frozen=True, slots=True)
class InvalidationRule:
    """Cache invalidation rule."""

    rule_id: str
    key_pattern: str
    strategy: InvalidationStrategy
    ttl_seconds: int
    enabled: bool


@dataclass(frozen=True, slots=True)
class InvalidationEvent:
    """Cache invalidation event."""

    event_id: str
    rule_id: str
    keys: list[str]
    triggered_at: datetime
    trigger_source: str


class CacheInvalidation:
    """
    Cache invalidation service.

    Features:
    - Time-based invalidation
    - Event-based invalidation
    - Manual invalidation
    - Invalidation tracking
    """

    def __init__(self) -> None:
        """Initialize cache invalidation service."""
        self._rules: dict[str, InvalidationRule] = {}
        self._events: list[InvalidationEvent] = []
        self._invalidation_tasks: dict[str, asyncio.Task] = {}
        self._cache_invalidate_callback: Callable[[list[str]], Awaitable[int]] | None = None

    def set_cache_invalidate_callback(
        self,
        callback: Callable[[list[str]], Awaitable[int]],
    ) -> None:
        """
        Set callback for cache invalidation.

        Args:
            callback: Async function to invalidate cache entries
        """
        self._cache_invalidate_callback = callback

    def create_rule(
        self,
        rule_id: str,
        key_pattern: str,
        strategy: InvalidationStrategy,
        ttl_seconds: int = 3600,
    ) -> InvalidationRule:
        """
        Create an invalidation rule.

        Args:
            rule_id: Rule identifier
            key_pattern: Key pattern to invalidate
            strategy: Invalidation strategy
            ttl_seconds: Time to live in seconds

        Returns:
            Invalidation rule
        """
        rule = InvalidationRule(
            rule_id=rule_id,
            key_pattern=key_pattern,
            strategy=strategy,
            ttl_seconds=ttl_seconds,
            enabled=True,
        )

        self._rules[rule_id] = rule

        logger.info(
            "invalidation_rule_created",
            rule_id=rule_id,
            key_pattern=key_pattern,
            strategy=strategy,
        )

        return rule

    async def invalidate_keys(
        self,
        keys: list[str],
        rule_id: str,
        trigger_source: str = "manual",
    ) -> InvalidationEvent:
        """
        Invalidate cache keys.

        Args:
            keys: Keys to invalidate
            rule_id: Rule identifier
            trigger_source: Source of trigger

        Returns:
            Invalidation event
        """
        event_id = f"event-{datetime.now(UTC).timestamp()}"

        event = InvalidationEvent(
            event_id=event_id,
            rule_id=rule_id,
            keys=keys,
            triggered_at=datetime.now(UTC),
            trigger_source=trigger_source,
        )

        self._events.append(event)

        if self._cache_invalidate_callback:
            try:
                count = await self._cache_invalidate_callback(keys)

                logger.info(
                    "cache_invalidated",
                    event_id=event_id,
                    count=count,
                )

            except Exception as e:
                logger.error(
                    "cache_invalidation_failed",
                    event_id=event_id,
                    error=str(e),
                )

        return event

    async def invalidate_pattern(
        self,
        pattern: str,
        rule_id: str,
        trigger_source: str = "pattern",
    ) -> InvalidationEvent:
        """
        Invalidate cache keys matching pattern.

        Args:
            pattern: Key pattern
            rule_id: Rule identifier
            trigger_source: Source of trigger

        Returns:
            Invalidation event
        """
        # In production, this would expand pattern to actual keys
        # For now, generate sample keys
        keys = [f"{pattern}-{i}" for i in range(10)]

        return await self.invalidate_keys(keys, rule_id, trigger_source)

    async def trigger_event_based_invalidation(
        self,
        event_type: str,
        event_data: dict[str, Any],
    ) -> list[InvalidationEvent]:
        """
        Trigger event-based invalidation.

        Args:
            event_type: Type of event
            event_data: Event data

        Returns:
            List of invalidation events
        """
        events = []

        for rule_id, rule in self._rules.items():
            if rule.strategy == InvalidationStrategy.EVENT_BASED and rule.enabled:
                # Check if rule matches event type (simplified)
                if rule.key_pattern in event_type:
                    keys = [f"{rule.key_pattern}-{event_data.get('id', 'unknown')}"]
                    event = await self.invalidate_keys(keys, rule_id, f"event:{event_type}")
                    events.append(event)

        return events

    async def start_time_based_invalidation(self) -> None:
        """Start time-based invalidation for all enabled rules."""
        for rule_id, rule in self._rules.items():
            if not rule.enabled:
                continue

            if rule.strategy == InvalidationStrategy.TIME_BASED and (
                rule_id not in self._invalidation_tasks or self._invalidation_tasks[rule_id].done()
            ):
                self._invalidation_tasks[rule_id] = asyncio.create_task(
                    self._time_based_invalidation_loop(rule_id, rule.ttl_seconds)
                )

    async def _time_based_invalidation_loop(
        self,
        rule_id: str,
        ttl_seconds: int,
    ) -> None:
        """
        Run time-based invalidation loop.

        Args:
            rule_id: Rule identifier
            ttl_seconds: TTL in seconds
        """
        while True:
            await asyncio.sleep(ttl_seconds)

            rule = self._rules.get(rule_id)
            if not rule or not rule.enabled:
                continue

            # Invalidate keys for this rule
            keys = [f"{rule.key_pattern}-timebased"]
            await self.invalidate_keys(keys, rule_id, "time_based")

    async def write_through_invalidation(
        self,
        key: str,
        value: Any,
    ) -> None:
        """
        Perform write-through invalidation.

        Args:
            key: Cache key
            value: New value
        """
        # Invalidate old value and set new value
        if self._cache_invalidate_callback:
            await self._cache_invalidate_callback([key])

        logger.debug(
            "write_through_invalidation",
            key=key,
        )

    def disable_rule(self, rule_id: str) -> bool:
        """
        Disable an invalidation rule.

        Args:
            rule_id: Rule identifier

        Returns:
            True if disabled
        """
        if rule_id in self._rules:
            rule = self._rules[rule_id]
            disabled_rule = InvalidationRule(
                rule_id=rule.rule_id,
                key_pattern=rule.key_pattern,
                strategy=rule.strategy,
                ttl_seconds=rule.ttl_seconds,
                enabled=False,
            )

            self._rules[rule_id] = disabled_rule

            # Cancel invalidation task
            if rule_id in self._invalidation_tasks and not self._invalidation_tasks[rule_id].done():
                self._invalidation_tasks[rule_id].cancel()

            logger.info(
                "invalidation_rule_disabled",
                rule_id=rule_id,
            )

            return True
        return False

    def enable_rule(self, rule_id: str) -> bool:
        """
        Enable an invalidation rule.

        Args:
            rule_id: Rule identifier

        Returns:
            True if enabled
        """
        if rule_id in self._rules:
            rule = self._rules[rule_id]
            enabled_rule = InvalidationRule(
                rule_id=rule.rule_id,
                key_pattern=rule.key_pattern,
                strategy=rule.strategy,
                ttl_seconds=rule.ttl_seconds,
                enabled=True,
            )

            self._rules[rule_id] = enabled_rule

            logger.info(
                "invalidation_rule_enabled",
                rule_id=rule_id,
            )

            return True
        return False

    def get_invalidations(
        self,
        rule_id: str | None = None,
        limit: int = 100,
    ) -> list[InvalidationEvent]:
        """
        Get invalidation events.

        Args:
            rule_id: Filter by rule
            limit: Maximum number of events

        Returns:
            List of invalidation events
        """
        events = self._events

        if rule_id:
            events = [e for e in events if e.rule_id == rule_id]

        return sorted(events, key=lambda e: e.triggered_at, reverse=True)[:limit]

    def get_invalidation_stats(self) -> dict[str, Any]:
        """
        Get invalidation statistics.

        Returns:
            Invalidation statistics
        """
        total_events = len(self._events)

        source_counts: dict[str, int] = {}
        for event in self._events:
            source_counts[event.trigger_source] = source_counts.get(event.trigger_source, 0) + 1

        strategy_counts: dict[str, int] = {}
        for rule in self._rules.values():
            if rule.enabled:
                strategy_counts[rule.strategy] = strategy_counts.get(rule.strategy, 0) + 1

        return {
            "total_rules": len(self._rules),
            "enabled_rules": sum(1 for r in self._rules.values() if r.enabled),
            "total_events": total_events,
            "source_breakdown": source_counts,
            "strategy_breakdown": strategy_counts,
        }
