"""
Message Transformer - Message Transformation and Enrichment

Implements message transformation and enrichment.
Supports schema validation, field mapping, and content enrichment.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class TransformationType(StrEnum):
    """Transformation type."""

    FIELD_MAPPING = "field_mapping"
    CONTENT_ENRICHMENT = "content_enrichment"
    SCHEMA_VALIDATION = "schema_validation"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class TransformationRule:
    """Transformation rule."""

    rule_id: str
    transformation_type: TransformationType
    source_pattern: str
    target_pattern: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class TransformationResult:
    """Transformation result."""

    transformation_id: str
    rule_id: str
    success: bool
    original_message: Any
    transformed_message: Any
    errors: list[str]
    transformed_at: datetime


class MessageTransformer:
    """
    Message transformation and enrichment service.

    Features:
    - Field mapping
    - Content enrichment
    - Schema validation
    - Custom transformations
    """

    def __init__(self) -> None:
        """Initialize message transformer."""
        self._rules: dict[str, TransformationRule] = {}
        self._results: dict[str, TransformationResult] = {}
        self._transform_callback: Callable[[TransformationRule, Any], Awaitable[Any]] | None = None
        self._enrichment_callback: Callable[[Any], Awaitable[dict[str, Any]]] | None = None

    def set_transform_callback(
        self,
        callback: Callable[[TransformationRule, Any], Awaitable[Any]],
    ) -> None:
        """
        Set transform callback.

        Args:
            callback: Async function to transform message
        """
        self._transform_callback = callback

    def set_enrichment_callback(
        self,
        callback: Callable[[Any], Awaitable[dict[str, Any]]],
    ) -> None:
        """
        Set enrichment callback.

        Args:
            callback: Async function to enrich message
        """
        self._enrichment_callback = callback

    def add_rule(
        self,
        rule_id: str,
        transformation_type: TransformationType,
        source_pattern: str,
        target_pattern: str,
        enabled: bool = True,
    ) -> TransformationRule:
        """
        Add a transformation rule.

        Args:
            rule_id: Rule identifier
            transformation_type: Transformation type
            source_pattern: Source pattern
            target_pattern: Target pattern
            enabled: Whether rule is enabled

        Returns:
            Transformation rule
        """
        rule = TransformationRule(
            rule_id=rule_id,
            transformation_type=transformation_type,
            source_pattern=source_pattern,
            target_pattern=target_pattern,
            enabled=enabled,
        )

        self._rules[rule_id] = rule

        logger.info(
            "transformation_rule_added",
            rule_id=rule_id,
            transformation_type=transformation_type,
        )

        return rule

    async def transform(
        self,
        rule_id: str,
        message: Any,
    ) -> TransformationResult:
        """
        Transform a message.

        Args:
            rule_id: Rule identifier
            message: Message to transform

        Returns:
            Transformation result
        """
        transformation_id = f"trans-{datetime.now(UTC).timestamp()}"

        rule = self._rules.get(rule_id)

        if not rule:
            return TransformationResult(
                transformation_id=transformation_id,
                rule_id=rule_id,
                success=False,
                original_message=message,
                transformed_message=None,
                errors=["Rule not found"],
                transformed_at=datetime.now(UTC),
            )

        if not rule.enabled:
            return TransformationResult(
                transformation_id=transformation_id,
                rule_id=rule_id,
                success=False,
                original_message=message,
                transformed_message=None,
                errors=["Rule not enabled"],
                transformed_at=datetime.now(UTC),
            )

        try:
            if rule.transformation_type == TransformationType.FIELD_MAPPING:
                transformed = await self._apply_field_mapping(rule, message)
            elif rule.transformation_type == TransformationType.CONTENT_ENRICHMENT:
                transformed = await self._apply_enrichment(message)
            elif rule.transformation_type == TransformationType.SCHEMA_VALIDATION:
                transformed = await self._validate_schema(rule, message)
            elif rule.transformation_type == TransformationType.CUSTOM:
                if self._transform_callback:
                    transformed = await self._transform_callback(rule, message)
                else:
                    transformed = message
            else:
                transformed = message

            result = TransformationResult(
                transformation_id=transformation_id,
                rule_id=rule_id,
                success=True,
                original_message=message,
                transformed_message=transformed,
                errors=[],
                transformed_at=datetime.now(UTC),
            )

            self._results[transformation_id] = result

            logger.info(
                "message_transformed",
                transformation_id=transformation_id,
                rule_id=rule_id,
            )

            return result

        except Exception as e:
            result = TransformationResult(
                transformation_id=transformation_id,
                rule_id=rule_id,
                success=False,
                original_message=message,
                transformed_message=None,
                errors=[str(e)],
                transformed_at=datetime.now(UTC),
            )

            self._results[transformation_id] = result

            logger.error(
                "transformation_failed",
                transformation_id=transformation_id,
                rule_id=rule_id,
                error=str(e),
            )

            return result

    async def _apply_field_mapping(
        self,
        rule: TransformationRule,
        message: Any,
    ) -> Any:
        """
        Apply field mapping transformation.

        Args:
            rule: Transformation rule
            message: Message to transform

        Returns:
            Transformed message
        """
        # Simplified field mapping
        # In production, this would parse source_pattern and target_pattern
        if isinstance(message, dict):
            return message
        return message

    async def _apply_enrichment(
        self,
        message: Any,
    ) -> Any:
        """
        Apply content enrichment.

        Args:
            message: Message to enrich

        Returns:
            Enriched message
        """
        if self._enrichment_callback:
            enrichment = await self._enrichment_callback(message)

            if isinstance(message, dict):
                return {**message, **enrichment}

        return message

    async def _validate_schema(
        self,
        rule: TransformationRule,
        message: Any,
    ) -> Any:
        """
        Validate message schema.

        Args:
            rule: Transformation rule
            message: Message to validate

        Returns:
            Validated message
        """
        # Simplified validation
        # In production, this would validate against schema
        return message

    async def transform_batch(
        self,
        rule_id: str,
        messages: list[Any],
    ) -> list[TransformationResult]:
        """
        Transform a batch of messages.

        Args:
            rule_id: Rule identifier
            messages: Messages to transform

        Returns:
            List of transformation results
        """
        results = []

        for message in messages:
            result = await self.transform(rule_id, message)
            results.append(result)

        return results

    def get_rule(self, rule_id: str) -> TransformationRule | None:
        """
        Get a transformation rule.

        Args:
            rule_id: Rule identifier

        Returns:
            Transformation rule or None
        """
        return self._rules.get(rule_id)

    def remove_rule(self, rule_id: str) -> bool:
        """
        Remove a transformation rule.

        Args:
            rule_id: Rule identifier

        Returns:
            True if removed
        """
        if rule_id in self._rules:
            del self._rules[rule_id]

            logger.info(
                "transformation_rule_removed",
                rule_id=rule_id,
            )

            return True
        return False

    def disable_rule(self, rule_id: str) -> bool:
        """
        Disable a transformation rule.

        Args:
            rule_id: Rule identifier

        Returns:
            True if disabled
        """
        if rule_id in self._rules:
            rule = self._rules[rule_id]
            disabled_rule = TransformationRule(
                rule_id=rule.rule_id,
                transformation_type=rule.transformation_type,
                source_pattern=rule.source_pattern,
                target_pattern=rule.target_pattern,
                enabled=False,
            )

            self._rules[rule_id] = disabled_rule

            logger.info(
                "transformation_rule_disabled",
                rule_id=rule_id,
            )

            return True
        return False

    def enable_rule(self, rule_id: str) -> bool:
        """
        Enable a transformation rule.

        Args:
            rule_id: Rule identifier

        Returns:
            True if enabled
        """
        if rule_id in self._rules:
            rule = self._rules[rule_id]
            enabled_rule = TransformationRule(
                rule_id=rule.rule_id,
                transformation_type=rule.transformation_type,
                source_pattern=rule.source_pattern,
                target_pattern=rule.target_pattern,
                enabled=True,
            )

            self._rules[rule_id] = enabled_rule

            logger.info(
                "transformation_rule_enabled",
                rule_id=rule_id,
            )

            return True
        return False

    def get_result(self, transformation_id: str) -> TransformationResult | None:
        """
        Get a transformation result.

        Args:
            transformation_id: Transformation identifier

        Returns:
            Transformation result or None
        """
        return self._results.get(transformation_id)

    def get_results(
        self,
        rule_id: str | None = None,
        success: bool | None = None,
        limit: int = 100,
    ) -> list[TransformationResult]:
        """
        Get transformation results.

        Args:
            rule_id: Filter by rule
            success: Filter by success status
            limit: Maximum number of results

        Returns:
            List of transformation results
        """
        results = list(self._results.values())

        if rule_id:
            results = [r for r in results if r.rule_id == rule_id]

        if success is not None:
            results = [r for r in results if r.success == success]

        return sorted(results, key=lambda r: r.transformed_at, reverse=True)[:limit]

    def get_transformer_stats(self) -> dict[str, Any]:
        """
        Get transformer statistics.

        Returns:
            Transformer statistics
        """
        total_rules = len(self._rules)
        enabled_rules = sum(1 for r in self._rules.values() if r.enabled)
        total_transformations = len(self._results)
        successful_transformations = sum(1 for r in self._results.values() if r.success)

        type_counts: dict[str, int] = {}
        for rule in self._rules.values():
            type_counts[rule.transformation_type] = type_counts.get(rule.transformation_type, 0) + 1

        return {
            "total_rules": total_rules,
            "enabled_rules": enabled_rules,
            "total_transformations": total_transformations,
            "successful_transformations": successful_transformations,
            "failed_transformations": total_transformations - successful_transformations,
            "type_breakdown": type_counts,
        }
