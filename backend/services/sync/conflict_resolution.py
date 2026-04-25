"""
Conflict Resolution - Conflict Resolution Strategies

Implements conflict resolution strategies for data synchronization.
Supports last-write-wins, merge strategies, and custom resolvers.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ResolutionStrategy(StrEnum):
    """Conflict resolution strategy."""

    LAST_WRITE_WINS = "last_write_wins"
    FIRST_WRITE_WINS = "first_write_wins"
    MERGE = "merge"
    CUSTOM = "custom"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class ResolutionRule:
    """Conflict resolution rule."""

    rule_id: str
    data_type: str
    strategy: ResolutionStrategy
    custom_resolver: Callable[[Any, Any], Awaitable[Any]] | None
    auto_resolve: bool


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    """Conflict resolution result."""

    resolution_id: str
    conflict_id: str
    strategy: ResolutionStrategy
    resolved_data: Any
    resolved_at: datetime
    successful: bool
    reason: str | None


class ConflictResolver:
    """
    Conflict resolution service.

    Features:
    - Multiple resolution strategies
    - Custom resolvers
    - Automatic resolution
    - Manual resolution
    """

    def __init__(self) -> None:
        """Initialize conflict resolver."""
        self._rules: dict[str, ResolutionRule] = {}
        self._results: dict[str, ResolutionResult] = {}

    def add_rule(
        self,
        rule_id: str,
        data_type: str,
        strategy: ResolutionStrategy,
        custom_resolver: Callable[[Any, Any], Awaitable[Any]] | None = None,
        auto_resolve: bool = True,
    ) -> ResolutionRule:
        """
        Add a resolution rule.

        Args:
            rule_id: Rule identifier
            data_type: Data type
            strategy: Resolution strategy
            custom_resolver: Custom resolver function
            auto_resolve: Whether to auto-resolve

        Returns:
            Resolution rule
        """
        rule = ResolutionRule(
            rule_id=rule_id,
            data_type=data_type,
            strategy=strategy,
            custom_resolver=custom_resolver,
            auto_resolve=auto_resolve,
        )

        self._rules[rule_id] = rule

        logger.info(
            "resolution_rule_added",
            rule_id=rule_id,
            data_type=data_type,
            strategy=strategy,
        )

        return rule

    async def resolve_conflict(
        self,
        conflict_id: str,
        source_data: Any,
        target_data: Any,
        data_type: str,
        source_timestamp: datetime,
        target_timestamp: datetime,
    ) -> ResolutionResult:
        """
        Resolve a conflict.

        Args:
            conflict_id: Conflict identifier
            source_data: Source data
            target_data: Target data
            data_type: Data type
            source_timestamp: Source timestamp
            target_timestamp: Target timestamp

        Returns:
            Resolution result
        """
        resolution_id = f"res-{datetime.now(UTC).timestamp()}"

        # Find applicable rule
        rule = self._find_rule(data_type)

        if not rule or not rule.auto_resolve:
            # Manual resolution required
            result = ResolutionResult(
                resolution_id=resolution_id,
                conflict_id=conflict_id,
                strategy=ResolutionStrategy.MANUAL,
                resolved_data=None,
                resolved_at=datetime.now(UTC),
                successful=False,
                reason="Manual resolution required",
            )

            self._results[resolution_id] = result

            return result

        # Apply strategy
        try:
            if rule.strategy == ResolutionStrategy.LAST_WRITE_WINS:
                resolved_data = source_data if source_timestamp > target_timestamp else target_data
                reason = "Last write wins based on timestamp"

            elif rule.strategy == ResolutionStrategy.FIRST_WRITE_WINS:
                resolved_data = source_data if source_timestamp < target_timestamp else target_data
                reason = "First write wins based on timestamp"

            elif rule.strategy == ResolutionStrategy.MERGE:
                resolved_data = await self._merge_data(source_data, target_data)
                reason = "Merged data from both sources"

            elif rule.strategy == ResolutionStrategy.CUSTOM and rule.custom_resolver:
                resolved_data = await rule.custom_resolver(source_data, target_data)
                reason = "Custom resolver applied"

            else:
                raise ValueError(f"Unsupported strategy: {rule.strategy}")

            result = ResolutionResult(
                resolution_id=resolution_id,
                conflict_id=conflict_id,
                strategy=rule.strategy,
                resolved_data=resolved_data,
                resolved_at=datetime.now(UTC),
                successful=True,
                reason=reason,
            )

            self._results[resolution_id] = result

            logger.info(
                "conflict_resolved",
                resolution_id=resolution_id,
                conflict_id=conflict_id,
                strategy=rule.strategy,
            )

            return result

        except Exception as e:
            result = ResolutionResult(
                resolution_id=resolution_id,
                conflict_id=conflict_id,
                strategy=rule.strategy if rule else ResolutionStrategy.MANUAL,
                resolved_data=None,
                resolved_at=datetime.now(UTC),
                successful=False,
                reason=f"Resolution failed: {str(e)}",
            )

            self._results[resolution_id] = result

            logger.error(
                "conflict_resolution_failed",
                resolution_id=resolution_id,
                conflict_id=conflict_id,
                error=str(e),
            )

            return result

    def _find_rule(self, data_type: str) -> ResolutionRule | None:
        """
        Find resolution rule for data type.

        Args:
            data_type: Data type

        Returns:
            Resolution rule or None
        """
        # Exact match first
        for rule in self._rules.values():
            if rule.data_type == data_type:
                return rule

        # Wildcard match
        for rule in self._rules.values():
            if rule.data_type == "*":
                return rule

        return None

    async def _merge_data(self, source_data: Any, target_data: Any) -> Any:
        """
        Merge data from both sources.

        Args:
            source_data: Source data
            target_data: Target data

        Returns:
            Merged data
        """
        # Simplified merge logic
        # In production, this would handle various data types

        if isinstance(source_data, dict) and isinstance(target_data, dict):
            merged = target_data.copy()
            for key, value in source_data.items():
                if key not in merged:
                    merged[key] = value
                elif isinstance(value, dict) and isinstance(merged[key], dict):
                    merged[key] = await self._merge_data(value, merged[key])
            return merged

        # Default: prefer source
        return source_data

    async def manual_resolve(
        self,
        conflict_id: str,
        resolved_data: Any,
        reason: str,
    ) -> ResolutionResult:
        """
        Manually resolve a conflict.

        Args:
            conflict_id: Conflict identifier
            resolved_data: Resolved data
            reason: Resolution reason

        Returns:
            Resolution result
        """
        resolution_id = f"res-{datetime.now(UTC).timestamp()}"

        result = ResolutionResult(
            resolution_id=resolution_id,
            conflict_id=conflict_id,
            strategy=ResolutionStrategy.MANUAL,
            resolved_data=resolved_data,
            resolved_at=datetime.now(UTC),
            successful=True,
            reason=reason,
        )

        self._results[resolution_id] = result

        logger.info(
            "manual_conflict_resolved",
            resolution_id=resolution_id,
            conflict_id=conflict_id,
        )

        return result

    def get_resolution(self, resolution_id: str) -> ResolutionResult | None:
        """
        Get a resolution result.

        Args:
            resolution_id: Resolution identifier

        Returns:
            Resolution result or None
        """
        return self._results.get(resolution_id)

    def get_rule(self, rule_id: str) -> ResolutionRule | None:
        """
        Get a resolution rule.

        Args:
            rule_id: Rule identifier

        Returns:
            Resolution rule or None
        """
        return self._rules.get(rule_id)

    def remove_rule(self, rule_id: str) -> bool:
        """
        Remove a resolution rule.

        Args:
            rule_id: Rule identifier

        Returns:
            True if removed
        """
        if rule_id in self._rules:
            del self._rules[rule_id]

            logger.info(
                "resolution_rule_removed",
                rule_id=rule_id,
            )

            return True
        return False

    def get_resolver_stats(self) -> dict[str, Any]:
        """
        Get resolver statistics.

        Returns:
            Resolver statistics
        """
        total_resolutions = len(self._results)
        successful_resolutions = sum(1 for r in self._results.values() if r.successful)

        strategy_counts: dict[str, int] = {}
        for result in self._results.values():
            strategy_counts[result.strategy] = strategy_counts.get(result.strategy, 0) + 1

        return {
            "total_rules": len(self._rules),
            "auto_resolve_rules": sum(1 for r in self._rules.values() if r.auto_resolve),
            "total_resolutions": total_resolutions,
            "successful_resolutions": successful_resolutions,
            "failed_resolutions": total_resolutions - successful_resolutions,
            "strategy_breakdown": strategy_counts,
        }
