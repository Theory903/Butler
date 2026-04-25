"""
Cache Warming - Cache Warming Strategies

Implements cache warming strategies for proactive cache population.
Supports scheduled warming, predictive warming, and on-demand warming.
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


class WarmingStrategy(StrEnum):
    """Warming strategy."""

    SCHEDULED = "scheduled"
    PREDICTIVE = "predictive"
    ON_DEMAND = "on_demand"
    TRIGGERED = "triggered"


@dataclass(frozen=True, slots=True)
class WarmingRule:
    """Cache warming rule."""

    rule_id: str
    key_pattern: str  # Pattern for keys to warm
    strategy: WarmingStrategy
    interval_seconds: int
    priority: int
    enabled: bool


@dataclass(frozen=True, slots=True)
class WarmingJob:
    """Cache warming job."""

    job_id: str
    rule_id: str
    keys: list[str]
    started_at: datetime
    completed_at: datetime | None
    success_count: int
    failure_count: int


class CacheWarming:
    """
    Cache warming service.

    Features:
    - Scheduled warming
    - Predictive warming
    - On-demand warming
    - Job tracking
    """

    def __init__(self) -> None:
        """Initialize cache warming service."""
        self._rules: dict[str, WarmingRule] = {}
        self._jobs: list[WarmingJob] = []
        self._warming_tasks: dict[str, asyncio.Task] = {}
        self._data_loader: Callable[[list[str]], Awaitable[dict[str, Any]]] | None = None

    def create_rule(
        self,
        rule_id: str,
        key_pattern: str,
        strategy: WarmingStrategy,
        interval_seconds: int,
        priority: int = 5,
    ) -> WarmingRule:
        """
        Create a warming rule.

        Args:
            rule_id: Rule identifier
            key_pattern: Key pattern for warming
            strategy: Warming strategy
            interval_seconds: Interval in seconds
            priority: Job priority (lower = higher priority)

        Returns:
            Warming rule
        """
        rule = WarmingRule(
            rule_id=rule_id,
            key_pattern=key_pattern,
            strategy=strategy,
            interval_seconds=interval_seconds,
            priority=priority,
            enabled=True,
        )

        self._rules[rule_id] = rule

        logger.info(
            "warming_rule_created",
            rule_id=rule_id,
            key_pattern=key_pattern,
            strategy=strategy,
        )

        return rule

    def set_data_loader(
        self,
        loader: Callable[[list[str]], Awaitable[dict[str, Any]]],
    ) -> None:
        """
        Set data loader for cache warming.

        Args:
            loader: Async function to load data for keys
        """
        self._data_loader = loader

    async def warm_cache(
        self,
        keys: list[str],
        rule_id: str,
    ) -> WarmingJob:
        """
        Warm cache for given keys.

        Args:
            keys: Keys to warm
            rule_id: Rule identifier

        Returns:
            Warming job
        """
        job_id = f"job-{datetime.now(UTC).timestamp()}"

        job = WarmingJob(
            job_id=job_id,
            rule_id=rule_id,
            keys=keys,
            started_at=datetime.now(UTC),
            completed_at=None,
            success_count=0,
            failure_count=0,
        )

        self._jobs.append(job)

        if self._data_loader:
            try:
                data = await self._data_loader(keys)

                # In production, this would populate the actual cache
                # For now, just track success
                success_count = len(data)
                failure_count = len(keys) - success_count

                # Update job
                updated_job = WarmingJob(
                    job_id=job.job_id,
                    rule_id=job.rule_id,
                    keys=job.keys,
                    started_at=job.started_at,
                    completed_at=datetime.now(UTC),
                    success_count=success_count,
                    failure_count=failure_count,
                )

                self._jobs[-1] = updated_job

                logger.info(
                    "cache_warmed",
                    job_id=job_id,
                    success_count=success_count,
                    failure_count=failure_count,
                )

            except Exception as e:
                logger.error(
                    "cache_warming_failed",
                    job_id=job_id,
                    error=str(e),
                )

                updated_job = WarmingJob(
                    job_id=job.job_id,
                    rule_id=job.rule_id,
                    keys=job.keys,
                    started_at=job.started_at,
                    completed_at=datetime.now(UTC),
                    success_count=0,
                    failure_count=len(keys),
                )

                self._jobs[-1] = updated_job

        return job

    async def start_scheduled_warming(self) -> None:
        """Start scheduled warming for all enabled rules."""
        for rule_id, rule in self._rules.items():
            if not rule.enabled:
                continue

            if rule.strategy == WarmingStrategy.SCHEDULED:
                if rule_id not in self._warming_tasks or self._warming_tasks[rule_id].done():
                    self._warming_tasks[rule_id] = asyncio.create_task(
                        self._scheduled_warming_loop(rule_id, rule.interval_seconds)
                    )

    async def _scheduled_warming_loop(
        self,
        rule_id: str,
        interval_seconds: int,
    ) -> None:
        """
        Run scheduled warming loop.

        Args:
            rule_id: Rule identifier
            interval_seconds: Interval in seconds
        """
        while True:
            await asyncio.sleep(interval_seconds)

            rule = self._rules.get(rule_id)
            if not rule or not rule.enabled:
                continue

            # Generate keys from pattern (simplified)
            # In production, this would expand the pattern
            keys = [f"{rule.key_pattern}-{i}" for i in range(10)]

            await self.warm_cache(keys, rule_id)

    async def predict_and_warm(self, context: dict[str, Any]) -> list[str]:
        """
        Predict keys to warm based on context.

        Args:
            context: Context for prediction

        Returns:
            List of keys warmed
        """
        # Simplified prediction logic
        # In production, this would use ML models or access patterns

        predicted_keys = []

        for rule_id, rule in self._rules.items():
            if rule.strategy == WarmingStrategy.PREDICTIVE and rule.enabled:
                # Generate keys based on context
                keys = [f"{rule.key_pattern}-predicted"]

                job = await self.warm_cache(keys, rule_id)
                predicted_keys.extend(job.keys)

        return predicted_keys

    async def trigger_warming(
        self,
        rule_id: str,
        keys: list[str] | None = None,
    ) -> WarmingJob:
        """
        Trigger manual warming.

        Args:
            rule_id: Rule identifier
            keys: Optional keys to warm (uses pattern if None)

        Returns:
            Warming job
        """
        rule = self._rules.get(rule_id)

        if not rule:
            raise ValueError(f"Rule not found: {rule_id}")

        if not keys:
            keys = [f"{rule.key_pattern}-manual"]

        return await self.warm_cache(keys, rule_id)

    def disable_rule(self, rule_id: str) -> bool:
        """
        Disable a warming rule.

        Args:
            rule_id: Rule identifier

        Returns:
            True if disabled
        """
        if rule_id in self._rules:
            rule = self._rules[rule_id]
            disabled_rule = WarmingRule(
                rule_id=rule.rule_id,
                key_pattern=rule.key_pattern,
                strategy=rule.strategy,
                interval_seconds=rule.interval_seconds,
                priority=rule.priority,
                enabled=False,
            )

            self._rules[rule_id] = disabled_rule

            # Cancel warming task
            if rule_id in self._warming_tasks and not self._warming_tasks[rule_id].done():
                self._warming_tasks[rule_id].cancel()

            logger.info(
                "warming_rule_disabled",
                rule_id=rule_id,
            )

            return True
        return False

    def enable_rule(self, rule_id: str) -> bool:
        """
        Enable a warming rule.

        Args:
            rule_id: Rule identifier

        Returns:
            True if enabled
        """
        if rule_id in self._rules:
            rule = self._rules[rule_id]
            enabled_rule = WarmingRule(
                rule_id=rule.rule_id,
                key_pattern=rule.key_pattern,
                strategy=rule.strategy,
                interval_seconds=rule.interval_seconds,
                priority=rule.priority,
                enabled=True,
            )

            self._rules[rule_id] = enabled_rule

            logger.info(
                "warming_rule_enabled",
                rule_id=rule_id,
            )

            return True
        return False

    def get_warming_stats(self) -> dict[str, Any]:
        """
        Get warming statistics.

        Returns:
            Warming statistics
        """
        total_jobs = len(self._jobs)
        total_successes = sum(job.success_count for job in self._jobs)
        total_failures = sum(job.failure_count for job in self._jobs)

        strategy_counts: dict[str, int] = {}
        for rule in self._rules.values():
            if rule.enabled:
                strategy_counts[rule.strategy] = strategy_counts.get(rule.strategy, 0) + 1

        return {
            "total_rules": len(self._rules),
            "enabled_rules": sum(1 for r in self._rules.values() if r.enabled),
            "total_jobs": total_jobs,
            "total_successes": total_successes,
            "total_failures": total_failures,
            "strategy_breakdown": strategy_counts,
        }
