"""
Migration Guide - API Migration Guidance and Compatibility Layer

Provides migration guidance and compatibility layer for API version transitions.
Supports automatic response transformation and client migration assistance.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class MigrationType(StrEnum):
    """Migration type."""

    FIELD_RENAME = "field_rename"
    FIELD_REMOVE = "field_remove"
    FIELD_ADD = "field_add"
    TYPE_CHANGE = "type_change"
    STRUCTURE_CHANGE = "structure_change"


@dataclass(frozen=True, slots=True)
class MigrationRule:
    """Migration rule for transforming data between versions."""

    rule_id: str
    from_version: str
    to_version: str
    migration_type: MigrationType
    field_path: str
    transform: Callable[[Any], Any] | None
    description: str


@dataclass(frozen=True, slots=True)
class CompatibilityLayer:
    """Compatibility layer for version transitions."""

    from_version: str
    to_version: str
    request_transformer: Callable[[dict[str, Any]], dict[str, Any]] | None
    response_transformer: Callable[[dict[str, Any]], dict[str, Any]] | None
    enabled: bool


class MigrationGuideService:
    """
    Migration guide service for API version transitions.

    Features:
    - Migration rule management
    - Compatibility layer
    - Automatic transformation
    - Migration documentation
    """

    def __init__(self) -> None:
        """Initialize migration guide service."""
        self._migration_rules: dict[str, list[MigrationRule]] = {}
        self._compatibility_layers: dict[str, CompatibilityLayer] = {}

    def add_migration_rule(
        self,
        from_version: str,
        to_version: str,
        migration_type: MigrationType,
        field_path: str,
        transform: Callable[[Any], Any] | None = None,
        description: str = "",
    ) -> MigrationRule:
        """
        Add a migration rule.

        Args:
            from_version: Source version
            to_version: Target version
            migration_type: Type of migration
            field_path: Field path affected
            transform: Optional transform function
            description: Rule description

        Returns:
            Migration rule
        """
        rule_id = f"{from_version}-{to_version}-{field_path}"

        rule = MigrationRule(
            rule_id=rule_id,
            from_version=from_version,
            to_version=to_version,
            migration_type=migration_type,
            field_path=field_path,
            transform=transform,
            description=description,
        )

        key = f"{from_version}->{to_version}"
        if key not in self._migration_rules:
            self._migration_rules[key] = []

        self._migration_rules[key].append(rule)

        logger.info(
            "migration_rule_added",
            rule_id=rule_id,
            from_version=from_version,
            to_version=to_version,
        )

        return rule

    def add_compatibility_layer(
        self,
        from_version: str,
        to_version: str,
        request_transformer: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        response_transformer: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        enabled: bool = True,
    ) -> CompatibilityLayer:
        """
        Add a compatibility layer for version transition.

        Args:
            from_version: Source version
            to_version: Target version
            request_transformer: Optional request transformer
            response_transformer: Optional response transformer
            enabled: Whether layer is enabled

        Returns:
            Compatibility layer
        """
        layer = CompatibilityLayer(
            from_version=from_version,
            to_version=to_version,
            request_transformer=request_transformer,
            response_transformer=response_transformer,
            enabled=enabled,
        )

        key = f"{from_version}->{to_version}"
        self._compatibility_layers[key] = layer

        logger.info(
            "compatibility_layer_added",
            from_version=from_version,
            to_version=to_version,
            enabled=enabled,
        )

        return layer

    def get_migration_rules(
        self,
        from_version: str,
        to_version: str,
    ) -> list[MigrationRule]:
        """
        Get migration rules for version transition.

        Args:
            from_version: Source version
            to_version: Target version

        Returns:
            List of migration rules
        """
        key = f"{from_version}->{to_version}"
        return self._migration_rules.get(key, [])

    def get_compatibility_layer(
        self,
        from_version: str,
        to_version: str,
    ) -> CompatibilityLayer | None:
        """
        Get compatibility layer for version transition.

        Args:
            from_version: Source version
            to_version: Target version

        Returns:
            Compatibility layer or None
        """
        key = f"{from_version}->{to_version}"
        return self._compatibility_layers.get(key)

    async def transform_request(
        self,
        request_data: dict[str, Any],
        from_version: str,
        to_version: str,
    ) -> dict[str, Any]:
        """
        Transform request data from one version to another.

        Args:
            request_data: Request data
            from_version: Source version
            to_version: Target version

        Returns:
            Transformed request data
        """
        layer = self.get_compatibility_layer(from_version, to_version)

        if layer and layer.enabled and layer.request_transformer:
            try:
                transformed = layer.request_transformer(request_data)
                logger.debug(
                    "request_transformed",
                    from_version=from_version,
                    to_version=to_version,
                )
                return transformed
            except Exception as e:
                logger.error(
                    "request_transform_failed",
                    from_version=from_version,
                    to_version=to_version,
                    error=str(e),
                )
                return request_data

        return request_data

    async def transform_response(
        self,
        response_data: dict[str, Any],
        from_version: str,
        to_version: str,
    ) -> dict[str, Any]:
        """
        Transform response data from one version to another.

        Args:
            response_data: Response data
            from_version: Source version
            to_version: Target version

        Returns:
            Transformed response data
        """
        layer = self.get_compatibility_layer(from_version, to_version)

        if layer and layer.enabled and layer.response_transformer:
            try:
                transformed = layer.response_transformer(response_data)
                logger.debug(
                    "response_transformed",
                    from_version=from_version,
                    to_version=to_version,
                )
                return transformed
            except Exception as e:
                logger.error(
                    "response_transform_failed",
                    from_version=from_version,
                    to_version=to_version,
                    error=str(e),
                )
                return response_data

        return response_data

    def generate_migration_guide(
        self,
        from_version: str,
        to_version: str,
    ) -> dict[str, Any]:
        """
        Generate migration guide for version transition.

        Args:
            from_version: Source version
            to_version: Target version

        Returns:
            Migration guide
        """
        rules = self.get_migration_rules(from_version, to_version)
        layer = self.get_compatibility_layer(from_version, to_version)

        return {
            "from_version": from_version,
            "to_version": to_version,
            "generated_at": datetime.now(UTC).isoformat(),
            "migration_rules": [
                {
                    "rule_id": rule.rule_id,
                    "type": rule.migration_type,
                    "field_path": rule.field_path,
                    "description": rule.description,
                }
                for rule in rules
            ],
            "compatibility_layer": {
                "available": layer is not None,
                "enabled": layer.enabled if layer else False,
                "has_request_transformer": layer.request_transformer is not None
                if layer
                else False,
                "has_response_transformer": layer.response_transformer is not None
                if layer
                else False,
            }
            if layer
            else None,
        }

    def list_migration_paths(self) -> list[str]:
        """List all available migration paths."""
        return list(self._migration_rules.keys())

    def list_compatibility_layers(self) -> list[str]:
        """List all compatibility layers."""
        return list(self._compatibility_layers.keys())

    def get_migration_stats(self) -> dict[str, Any]:
        """
        Get migration statistics.

        Returns:
            Migration statistics
        """
        total_rules = sum(len(rules) for rules in self._migration_rules.values())
        total_layers = len(self._compatibility_layers)
        enabled_layers = sum(1 for layer in self._compatibility_layers.values() if layer.enabled)

        return {
            "total_migration_rules": total_rules,
            "total_compatibility_layers": total_layers,
            "enabled_compatibility_layers": enabled_layers,
            "available_migration_paths": len(self._migration_rules),
        }
