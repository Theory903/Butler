"""
Dynamic Configuration Service - Hot-Reload Configuration

Implements dynamic configuration with hot-reload capabilities.
Supports runtime configuration changes without service restart.
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


class ConfigScope(StrEnum):
    """Configuration scope."""

    GLOBAL = "global"
    TENANT = "tenant"
    USER = "user"
    ENVIRONMENT = "environment"


@dataclass(frozen=True, slots=True)
class ConfigValue:
    """Configuration value with metadata."""

    key: str
    value: Any
    scope: ConfigScope
    scope_id: str | None  # tenant_id, user_id, etc.
    updated_at: datetime
    updated_by: str


class DynamicConfigService:
    """
    Dynamic configuration service for hot-reload.

    Features:
    - Runtime configuration
    - Hot-reload
    - Scope-based isolation
    - Change notifications
    """

    def __init__(self) -> None:
        """Initialize dynamic configuration service."""
        self._configs: dict[str, dict[str, ConfigValue]] = {}  # scope -> key -> value
        self._subscribers: dict[str, list[Callable[[ConfigValue], Awaitable[None]]]] = {}
        self._reload_task: asyncio.Task | None = None

    def set_config(
        self,
        key: str,
        value: Any,
        scope: ConfigScope = ConfigScope.GLOBAL,
        scope_id: str | None = None,
        updated_by: str = "system",
    ) -> ConfigValue:
        """
        Set a configuration value.

        Args:
            key: Configuration key
            value: Configuration value
            scope: Configuration scope
            scope_id: Scope identifier
            updated_by: Who made the change

        Returns:
            Configuration value
        """
        scope_key = f"{scope.value}:{scope_id or 'default'}"

        if scope_key not in self._configs:
            self._configs[scope_key] = {}

        config = ConfigValue(
            key=key,
            value=value,
            scope=scope,
            scope_id=scope_id,
            updated_at=datetime.now(UTC),
            updated_by=updated_by,
        )

        self._configs[scope_key][key] = config

        logger.info(
            "config_set",
            key=key,
            scope=scope,
            scope_id=scope_id,
            value=value,
        )

        # Notify subscribers
        asyncio.create_task(self._notify_subscribers(config))

        return config

    def get_config(
        self,
        key: str,
        scope: ConfigScope = ConfigScope.GLOBAL,
        scope_id: str | None = None,
        default: Any = None,
    ) -> Any:
        """
        Get a configuration value.

        Args:
            key: Configuration key
            scope: Configuration scope
            scope_id: Scope identifier
            default: Default value if not found

        Returns:
            Configuration value or default
        """
        scope_key = f"{scope.value}:{scope_id or 'default'}"

        if scope_key not in self._configs:
            return default

        config = self._configs[scope_key].get(key)

        if config:
            return config.value

        # Fall back to global scope
        global_key = f"{ConfigScope.GLOBAL.value}:default"
        if global_key in self._configs and key in self._configs[global_key]:
            return self._configs[global_key][key].value

        return default

    def delete_config(
        self,
        key: str,
        scope: ConfigScope = ConfigScope.GLOBAL,
        scope_id: str | None = None,
    ) -> bool:
        """
        Delete a configuration value.

        Args:
            key: Configuration key
            scope: Configuration scope
            scope_id: Scope identifier

        Returns:
            True if deleted
        """
        scope_key = f"{scope.value}:{scope_id or 'default'}"

        if scope_key in self._configs and key in self._configs[scope_key]:
            del self._configs[scope_key][key]

            logger.info(
                "config_deleted",
                key=key,
                scope=scope,
                scope_id=scope_id,
            )

            return True

        return False

    def subscribe_to_changes(
        self,
        key: str | None = None,
        handler: Callable[[ConfigValue], Awaitable[None]] | None = None,
    ) -> str:
        """
        Subscribe to configuration changes.

        Args:
            key: Configuration key to filter (None for all)
            handler: Change handler

        Returns:
            Subscription ID
        """
        subscription_id = f"sub-{datetime.now(UTC).timestamp()}"

        subscription_key = key or "*"

        if subscription_key not in self._subscribers:
            self._subscribers[subscription_key] = []

        if handler:
            self._subscribers[subscription_key].append(handler)

        logger.info(
            "config_subscription_created",
            subscription_id=subscription_id,
            key=key or "*",
        )

        return subscription_id

    async def _notify_subscribers(self, config: ConfigValue) -> None:
        """Notify subscribers of configuration change."""
        # Notify wildcard subscribers
        for handler in self._subscribers.get("*", []):
            try:
                await handler(config)
            except Exception as e:
                logger.error(
                    "config_subscriber_handler_failed",
                    key=config.key,
                    error=str(e),
                )

        # Notify key-specific subscribers
        for handler in self._subscribers.get(config.key, []):
            try:
                await handler(config)
            except Exception as e:
                logger.error(
                    "config_subscriber_handler_failed",
                    key=config.key,
                    error=str(e),
                )

    def list_configs(
        self,
        scope: ConfigScope | None = None,
        scope_id: str | None = None,
    ) -> list[ConfigValue]:
        """
        List configuration values.

        Args:
            scope: Filter by scope
            scope_id: Filter by scope ID

        Returns:
            List of configuration values
        """
        configs = []

        for _scope_key, values in self._configs.items():
            for config in values.values():
                if scope and config.scope != scope:
                    continue

                if scope_id and config.scope_id != scope_id:
                    continue

                configs.append(config)

        return sorted(configs, key=lambda c: c.updated_at, reverse=True)

    def reload_from_source(self, source: str = "env") -> int:
        """
        Reload configuration from source.

        Args:
            source: Source to reload from (env, file, etc.)

        Returns:
            Number of configs reloaded
        """
        # In production, this would load from external config source
        logger.info(
            "config_reload_started",
            source=source,
        )

        # Placeholder implementation
        count = 0

        logger.info(
            "config_reload_completed",
            source=source,
            count=count,
        )

        return count

    def start_auto_reload(
        self,
        interval_seconds: int = 60,
    ) -> None:
        """
        Start automatic configuration reload.

        Args:
            interval_seconds: Reload interval
        """

        async def _reload_loop():
            while True:
                await asyncio.sleep(interval_seconds)
                self.reload_from_source("auto")

        if self._reload_task is None or self._reload_task.done():
            self._reload_task = asyncio.create_task(_reload_loop())

            logger.info(
                "auto_reload_started",
                interval_seconds=interval_seconds,
            )

    def stop_auto_reload(self) -> None:
        """Stop automatic configuration reload."""
        if self._reload_task and not self._reload_task.done():
            self._reload_task.cancel()

            logger.info("auto_reload_stopped")

    def get_config_stats(self) -> dict[str, Any]:
        """
        Get configuration statistics.

        Returns:
            Configuration statistics
        """
        total_configs = sum(len(values) for values in self._configs.values())

        scope_counts: dict[str, int] = {}
        for values in self._configs.values():
            for config in values.values():
                scope_counts[config.scope.value] = scope_counts.get(config.scope.value, 0) + 1

        return {
            "total_configs": total_configs,
            "scope_breakdown": scope_counts,
            "total_subscriptions": len(self._subscribers),
            "auto_reload_active": self._reload_task is not None and not self._reload_task.done(),
        }
