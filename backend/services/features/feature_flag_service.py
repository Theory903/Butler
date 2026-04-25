"""
Feature Flag Service - Feature Management with Targeting Rules

Implements feature flag management with targeting rules and rollout strategies.
Supports percentage-based rollouts, user targeting, and environment-specific flags.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class FlagType(StrEnum):
    """Feature flag type."""

    BOOLEAN = "boolean"
    PERCENTAGE = "percentage"
    MULTIVARIATE = "multivariate"


class RolloutStrategy(StrEnum):
    """Rollout strategy."""

    ALL_OR_NOTHING = "all_or_nothing"
    GRADUAL = "gradual"
    CANARY = "canary"
    PERCENTAGE = "percentage"


@dataclass(frozen=True, slots=True)
class TargetingRule:
    """Targeting rule for feature flags."""

    rule_id: str
    attribute: str  # user_id, tenant_id, email, etc.
    operator: str  # eq, ne, in, contains, regex
    values: list[str]


@dataclass(frozen=True, slots=True)
class FeatureFlag:
    """Feature flag definition."""

    flag_key: str
    flag_type: FlagType
    enabled: bool
    rollout_strategy: RolloutStrategy
    percentage: int  # For percentage-based flags
    targeting_rules: list[TargetingRule]
    created_at: datetime
    updated_at: datetime
    description: str


class FeatureFlagService:
    """
    Feature flag service for feature management.

    Features:
    - Flag registration
    - Targeting rules
    - Percentage-based rollouts
    - User/tenant targeting
    - Environment isolation
    """

    def __init__(self) -> None:
        """Initialize feature flag service."""
        self._flags: dict[str, FeatureFlag] = {}
        self._overrides: dict[str, dict[str, bool]] = {}  # flag_key -> {user_id: enabled}

    def register_flag(
        self,
        flag_key: str,
        flag_type: FlagType = FlagType.BOOLEAN,
        enabled: bool = False,
        rollout_strategy: RolloutStrategy = RolloutStrategy.ALL_OR_NOTHING,
        percentage: int = 0,
        targeting_rules: list[TargetingRule] | None = None,
        description: str = "",
    ) -> FeatureFlag:
        """
        Register a feature flag.

        Args:
            flag_key: Flag identifier
            flag_type: Flag type
            enabled: Default enabled state
            rollout_strategy: Rollout strategy
            percentage: Percentage for percentage-based flags
            targeting_rules: Targeting rules
            description: Flag description

        Returns:
            Feature flag
        """
        now = datetime.now(UTC)

        flag = FeatureFlag(
            flag_key=flag_key,
            flag_type=flag_type,
            enabled=enabled,
            rollout_strategy=rollout_strategy,
            percentage=percentage,
            targeting_rules=targeting_rules or [],
            created_at=now,
            updated_at=now,
            description=description,
        )

        self._flags[flag_key] = flag

        logger.info(
            "feature_flag_registered",
            flag_key=flag_key,
            flag_type=flag_type,
            enabled=enabled,
        )

        return flag

    def is_enabled(
        self,
        flag_key: str,
        user_id: str | None = None,
        tenant_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> bool:
        """
        Check if a feature flag is enabled for a user.

        Args:
            flag_key: Flag identifier
            user_id: User identifier
            tenant_id: Tenant identifier
            attributes: Additional attributes for targeting

        Returns:
            True if flag is enabled
        """
        flag = self._flags.get(flag_key)

        if not flag:
            logger.warning(
                "feature_flag_not_found",
                flag_key=flag_key,
            )
            return False

        # Check user-specific override
        if user_id and flag_key in self._overrides and user_id in self._overrides[flag_key]:
            return self._overrides[flag_key][user_id]

        # Check if flag is globally enabled
        if not flag.enabled:
            return False

        # Check targeting rules
        if flag.targeting_rules and self._matches_targeting_rules(
            flag.targeting_rules,
            user_id=user_id,
            tenant_id=tenant_id,
            attributes=attributes,
        ):
            return True

        # Apply rollout strategy
        if flag.rollout_strategy == RolloutStrategy.ALL_OR_NOTHING:
            return flag.enabled

        if flag.rollout_strategy == RolloutStrategy.PERCENTAGE:
            if user_id:
                return self._check_percentage_rollout(
                    flag.percentage,
                    user_id,
                )
            return False

        if flag.rollout_strategy == RolloutStrategy.GRADUAL:
            # Gradual rollout based on user ID hash
            if user_id:
                return self._check_percentage_rollout(
                    flag.percentage,
                    user_id,
                )
            return False

        if flag.rollout_strategy == RolloutStrategy.CANARY:
            # Canary rollout - check if user is in canary group
            if user_id:
                hash_value = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
                return (hash_value % 100) < flag.percentage
            return False

        return flag.enabled

    def _matches_targeting_rules(
        self,
        rules: list[TargetingRule],
        user_id: str | None = None,
        tenant_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> bool:
        """
        Check if targeting rules match.

        Args:
            rules: Targeting rules
            user_id: User identifier
            tenant_id: Tenant identifier
            attributes: Additional attributes

        Returns:
            True if any rule matches
        """
        attributes = attributes or {}
        attributes["user_id"] = user_id
        attributes["tenant_id"] = tenant_id

        for rule in rules:
            value = attributes.get(rule.attribute)

            if value is None:
                continue

            if rule.operator == "eq":
                if str(value) in rule.values:
                    return True

            elif rule.operator == "ne":
                if str(value) not in rule.values:
                    return True

            elif rule.operator == "in":
                if str(value) in rule.values:
                    return True

            elif rule.operator == "contains":
                if any(v in str(value) for v in rule.values):
                    return True

        return False

    def _check_percentage_rollout(
        self,
        percentage: int,
        user_id: str,
    ) -> bool:
        """
        Check if user is in percentage rollout.

        Args:
            percentage: Rollout percentage (0-100)
            user_id: User identifier

        Returns:
            True if user is in rollout
        """
        hash_value = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
        return (hash_value % 100) < percentage

    def set_user_override(
        self,
        flag_key: str,
        user_id: str,
        enabled: bool,
    ) -> None:
        """
        Set a user-specific override for a flag.

        Args:
            flag_key: Flag identifier
            user_id: User identifier
            enabled: Override value
        """
        if flag_key not in self._overrides:
            self._overrides[flag_key] = {}

        self._overrides[flag_key][user_id] = enabled

        logger.info(
            "user_override_set",
            flag_key=flag_key,
            user_id=user_id,
            enabled=enabled,
        )

    def remove_user_override(
        self,
        flag_key: str,
        user_id: str,
    ) -> bool:
        """
        Remove a user-specific override.

        Args:
            flag_key: Flag identifier
            user_id: User identifier

        Returns:
            True if removed
        """
        if flag_key in self._overrides and user_id in self._overrides[flag_key]:
            del self._overrides[flag_key][user_id]
            logger.info(
                "user_override_removed",
                flag_key=flag_key,
                user_id=user_id,
            )
            return True
        return False

    def update_flag(
        self,
        flag_key: str,
        enabled: bool | None = None,
        percentage: int | None = None,
        rollout_strategy: RolloutStrategy | None = None,
    ) -> FeatureFlag | None:
        """
        Update a feature flag.

        Args:
            flag_key: Flag identifier
            enabled: New enabled state
            percentage: New percentage
            rollout_strategy: New rollout strategy

        Returns:
            Updated flag or None
        """
        flag = self._flags.get(flag_key)

        if not flag:
            logger.error(
                "feature_flag_not_found",
                flag_key=flag_key,
            )
            return None

        updated_flag = FeatureFlag(
            flag_key=flag.flag_key,
            flag_type=flag.flag_type,
            enabled=enabled if enabled is not None else flag.enabled,
            rollout_strategy=rollout_strategy
            if rollout_strategy is not None
            else flag.rollout_strategy,
            percentage=percentage if percentage is not None else flag.percentage,
            targeting_rules=flag.targeting_rules,
            created_at=flag.created_at,
            updated_at=datetime.now(UTC),
            description=flag.description,
        )

        self._flags[flag_key] = updated_flag

        logger.info(
            "feature_flag_updated",
            flag_key=flag_key,
        )

        return updated_flag

    def get_flag(self, flag_key: str) -> FeatureFlag | None:
        """
        Get a feature flag by key.

        Args:
            flag_key: Flag identifier

        Returns:
            Feature flag or None
        """
        return self._flags.get(flag_key)

    def list_flags(
        self,
        enabled: bool | None = None,
    ) -> list[FeatureFlag]:
        """
        List feature flags with optional filter.

        Args:
            enabled: Filter by enabled state

        Returns:
            List of feature flags
        """
        flags = list(self._flags.values())

        if enabled is not None:
            flags = [f for f in flags if f.enabled == enabled]

        return sorted(flags, key=lambda f: f.created_at, reverse=True)

    def get_flag_stats(self) -> dict[str, Any]:
        """
        Get feature flag statistics.

        Returns:
            Feature flag statistics
        """
        total_flags = len(self._flags)
        enabled_flags = sum(1 for f in self._flags.values() if f.enabled)

        type_counts: dict[str, int] = {}
        for flag in self._flags.values():
            type_counts[flag.flag_type] = type_counts.get(flag.flag_type, 0) + 1

        strategy_counts: dict[str, int] = {}
        for flag in self._flags.values():
            strategy_counts[flag.rollout_strategy] = (
                strategy_counts.get(flag.rollout_strategy, 0) + 1
            )

        total_overrides = sum(len(overrides) for overrides in self._overrides.values())

        return {
            "total_flags": total_flags,
            "enabled_flags": enabled_flags,
            "disabled_flags": total_flags - enabled_flags,
            "type_breakdown": type_counts,
            "strategy_breakdown": strategy_counts,
            "total_user_overrides": total_overrides,
        }
