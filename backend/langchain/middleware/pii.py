"""Butler PII Middleware.

RFC-compliant PII redaction on inputs and outputs.
"""

import logging
from typing import Any

from langchain.middleware.base import (
    ButlerBaseMiddleware,
    ButlerMiddlewareContext,
    MiddlewareResult,
)
from services.security.redaction import RedactionService

import structlog

logger = structlog.get_logger(__name__)


class ButlerPIIMiddleware(ButlerBaseMiddleware):
    """Middleware for RFC-compliant PII redaction.

    Runs on PRE_MODEL and POST_MODEL hooks to redact PII.
    """

    def __init__(
        self,
        redaction_service: RedactionService | None = None,
        enabled: bool = True,
    ):
        super().__init__(enabled=enabled)
        self._redaction_service = redaction_service or RedactionService()

    async def _redact_messages(
        self, messages: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
        """Redact PII from messages."""
        modified_messages = []
        redaction_map: dict[str, list[str]] = {}

        for msg in messages:
            content = msg.get("content", "")
            if not content:
                modified_messages.append(msg)
                continue

            redacted_text, msg_redaction_map = self._redaction_service.redact(content)
            if msg_redaction_map:
                for key, values in msg_redaction_map.items():
                    redaction_map.setdefault(key, []).extend(values)

            modified_messages.append({**msg, "content": redacted_text})

        return modified_messages, redaction_map

    async def pre_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Redact PII from input messages."""
        if not context.messages:
            return MiddlewareResult(success=True, should_continue=True)

        modified_messages, redaction_map = await self._redact_messages(context.messages)

        # Store redaction map in context for potential restoration
        context.metadata["_butler_pii_redaction_map"] = redaction_map

        if redaction_map:
            logger.info(
                "pii_redacted_input",
                categories=list(redaction_map.keys()),
                total_redacted=sum(len(v) for v in redaction_map.values()),
            )

        return MiddlewareResult(
            success=True,
            should_continue=True,
            modified_input={"messages": modified_messages},
            metadata={"pii_redaction_map": redaction_map},
        )

    async def post_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Redact PII from output messages (do not restore)."""
        if not context.messages:
            return MiddlewareResult(success=True, should_continue=True)

        modified_messages, redaction_map = await self._redact_messages(context.messages)

        if redaction_map:
            logger.info(
                "pii_redacted_output",
                categories=list(redaction_map.keys()),
                total_redacted=sum(len(v) for v in redaction_map.values()),
            )

        return MiddlewareResult(
            success=True,
            should_continue=True,
            modified_output={"messages": modified_messages},
            metadata={"pii_redaction_map": redaction_map},
        )
