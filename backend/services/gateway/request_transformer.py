"""
Request Transformer - Request/Response Transformation Middleware

Implements request and response transformation for API gateway.
Supports header manipulation, body transformation, and protocol adaptation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class TransformationType(StrEnum):
    """Transformation type."""

    HEADER_ADD = "header_add"
    HEADER_REMOVE = "header_remove"
    HEADER_MODIFY = "header_modify"
    BODY_TRANSFORM = "body_transform"
    PROTOCOL_ADAPT = "protocol_adapt"


@dataclass(frozen=True, slots=True)
class TransformationRule:
    """Transformation rule."""

    rule_id: str
    transformation_type: TransformationType
    target: str  # header name, body path, etc.
    value: str | None
    transformer: Callable[[Any], Any] | None
    condition: Callable[[dict[str, Any]], bool] | None


@dataclass(slots=True)
class TransformationContext:
    """Transformation context."""

    request_id: str
    tenant_id: str
    user_id: str | None
    path: str
    method: str
    headers: dict[str, str]
    body: dict[str, Any]


class RequestTransformer:
    """
    Request transformer for gateway middleware.

    Features:
    - Header manipulation
    - Body transformation
    - Protocol adaptation
    - Conditional transformation
    """

    def __init__(self) -> None:
        """Initialize request transformer."""
        self._request_rules: list[TransformationRule] = []
        self._response_rules: list[TransformationRule] = []

    def add_request_rule(
        self,
        rule: TransformationRule,
    ) -> None:
        """
        Add a request transformation rule.

        Args:
            rule: Transformation rule
        """
        self._request_rules.append(rule)

        logger.info(
            "request_transformation_rule_added",
            rule_id=rule.rule_id,
            transformation_type=rule.transformation_type,
        )

    def add_response_rule(
        self,
        rule: TransformationRule,
    ) -> None:
        """
        Add a response transformation rule.

        Args:
            rule: Transformation rule
        """
        self._response_rules.append(rule)

        logger.info(
            "response_transformation_rule_added",
            rule_id=rule.rule_id,
            transformation_type=rule.transformation_type,
        )

    async def transform_request(
        self,
        context: TransformationContext,
    ) -> TransformationContext:
        """
        Transform request based on rules.

        Args:
            context: Transformation context

        Returns:
            Transformed context
        """
        context_dict = {
            "request_id": context.request_id,
            "tenant_id": context.tenant_id,
            "user_id": context.user_id,
            "path": context.path,
            "method": context.method,
            "headers": context.headers.copy(),
            "body": context.body.copy(),
        }

        for rule in self._request_rules:
            # Check condition
            if rule.condition and not rule.condition(context_dict):
                continue

            # Apply transformation
            if rule.transformation_type == TransformationType.HEADER_ADD:
                if rule.target and rule.value:
                    context.headers[rule.target] = rule.value

            elif rule.transformation_type == TransformationType.HEADER_REMOVE:
                if rule.target in context.headers:
                    del context.headers[rule.target]

            elif rule.transformation_type == TransformationType.HEADER_MODIFY:
                if rule.target and rule.value:
                    context.headers[rule.target] = rule.value

            elif rule.transformation_type == TransformationType.BODY_TRANSFORM:
                if rule.transformer:
                    context.body = rule.transformer(context.body)

        logger.debug(
            "request_transformed",
            request_id=context.request_id,
            rules_applied=len(self._request_rules),
        )

        return context

    async def transform_response(
        self,
        context: TransformationContext,
    ) -> dict[str, Any]:
        """
        Transform response based on rules.

        Args:
            context: Transformation context

        Returns:
            Transformed response body
        """
        response_body = context.body.copy()
        context_dict = {
            "request_id": context.request_id,
            "tenant_id": context.tenant_id,
            "user_id": context.user_id,
            "path": context.path,
            "method": context.method,
            "headers": context.headers.copy(),
            "body": response_body,
        }

        for rule in self._response_rules:
            # Check condition
            if rule.condition and not rule.condition(context_dict):
                continue

            # Apply transformation
            if (
                rule.transformation_type == TransformationType.BODY_TRANSFORM
                or rule.transformation_type == TransformationType.PROTOCOL_ADAPT
            ) and rule.transformer:
                response_body = rule.transformer(response_body)

        logger.debug(
            "response_transformed",
            request_id=context.request_id,
            rules_applied=len(self._response_rules),
        )

        return response_body

    def remove_request_rule(self, rule_id: str) -> bool:
        """
        Remove a request transformation rule.

        Args:
            rule_id: Rule identifier

        Returns:
            True if removed
        """
        for i, rule in enumerate(self._request_rules):
            if rule.rule_id == rule_id:
                self._request_rules.pop(i)
                logger.info(
                    "request_transformation_rule_removed",
                    rule_id=rule_id,
                )
                return True
        return False

    def remove_response_rule(self, rule_id: str) -> bool:
        """
        Remove a response transformation rule.

        Args:
            rule_id: Rule identifier

        Returns:
            True if removed
        """
        for i, rule in enumerate(self._response_rules):
            if rule.rule_id == rule_id:
                self._response_rules.pop(i)
                logger.info(
                    "response_transformation_rule_removed",
                    rule_id=rule_id,
                )
                return True
        return False

    def get_transformation_stats(self) -> dict[str, Any]:
        """
        Get transformation statistics.

        Returns:
            Transformation statistics
        """
        request_type_counts: dict[str, int] = {}
        for rule in self._request_rules:
            request_type_counts[rule.transformation_type] = (
                request_type_counts.get(rule.transformation_type, 0) + 1
            )

        response_type_counts: dict[str, int] = {}
        for rule in self._response_rules:
            response_type_counts[rule.transformation_type] = (
                response_type_counts.get(rule.transformation_type, 0) + 1
            )

        return {
            "total_request_rules": len(self._request_rules),
            "total_response_rules": len(self._response_rules),
            "request_type_breakdown": request_type_counts,
            "response_type_breakdown": response_type_counts,
        }
