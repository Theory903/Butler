"""Butler Guardrails Middleware.

Wraps ContentGuard and RedactionService to enforce safety and PII redaction
on agent inputs and outputs.
"""

import logging

from langchain.middleware.base import (
    ButlerBaseMiddleware,
    ButlerMiddlewareContext,
    MiddlewareResult,
)
from services.security.redaction import RedactionService
from services.security.safety import ContentGuard

import structlog

logger = structlog.get_logger(__name__)


class ButlerGuardrailsMiddleware(ButlerBaseMiddleware):
    """Middleware for safety checks and PII redaction.

    Runs on PRE_MODEL hook to check input safety and redact PII.
    Runs on POST_MODEL hook to check output safety and restore/redact as needed.
    """

    def __init__(
        self,
        content_guard: ContentGuard | None = None,
        redaction_service: RedactionService | None = None,
        enabled: bool = True,
        block_unsafe: bool = True,
    ):
        super().__init__(enabled=enabled)
        self._content_guard = content_guard
        self._redaction_service = redaction_service or RedactionService()
        self._block_unsafe = block_unsafe

    async def pre_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Check input safety and redact PII before model inference."""
        if not context.messages:
            return MiddlewareResult(success=True, should_continue=True)

        modified_messages = []
        redaction_map: dict[str, list[str]] = {}

        for msg in context.messages:
            content = msg.get("content", "")
            if not content:
                modified_messages.append(msg)
                continue

            # Redact PII
            redacted_text, msg_redaction_map = self._redaction_service.redact(content)
            if msg_redaction_map:
                for key, values in msg_redaction_map.items():
                    redaction_map.setdefault(key, []).extend(values)

            # Safety check
            if self._content_guard:
                try:
                    safety_result = await self._content_guard.check(redacted_text)
                    if not safety_result.get("safe", True):
                        if self._block_unsafe:
                            logger.warning(
                                "unsafe_input_blocked",
                                reason=safety_result.get("reason"),
                                categories=safety_result.get("categories"),
                            )
                            return MiddlewareResult(
                                success=False,
                                should_continue=False,
                                error=f"Content blocked: {safety_result.get('reason')}",
                                metadata={"safety_result": safety_result},
                            )
                        logger.warning(
                            "unsafe_input_logged",
                            reason=safety_result.get("reason"),
                            categories=safety_result.get("categories"),
                        )
                except Exception as exc:
                    logger.warning("safety_check_failed", error=str(exc))

            # Store redaction map in context for potential restoration
            modified_messages.append({**msg, "content": redacted_text})

        # Store redaction map in context metadata
        context.metadata["_butler_redaction_map"] = redaction_map

        return MiddlewareResult(
            success=True,
            should_continue=True,
            modified_input={"messages": modified_messages},
            metadata={"redaction_map": redaction_map},
        )

    async def post_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Check output safety and handle redaction restoration/redaction."""
        if not context.messages:
            return MiddlewareResult(success=True, should_continue=True)

        redaction_map = context.metadata.get("_butler_redaction_map", {})
        modified_messages = []

        for msg in context.messages:
            content = msg.get("content", "")
            if not content:
                modified_messages.append(msg)
                continue

            # Safety check on output
            if self._content_guard:
                try:
                    safety_result = await self._content_guard.check(content)
                    if not safety_result.get("safe", True):
                        if self._block_unsafe:
                            logger.warning(
                                "unsafe_output_blocked",
                                reason=safety_result.get("reason"),
                                categories=safety_result.get("categories"),
                            )
                            return MiddlewareResult(
                                success=False,
                                should_continue=False,
                                error=f"Output blocked: {safety_result.get('reason')}",
                                metadata={"safety_result": safety_result},
                            )
                        logger.warning(
                            "unsafe_output_logged",
                            reason=safety_result.get("reason"),
                            categories=safety_result.get("categories"),
                        )
                except Exception as exc:
                    logger.warning("output_safety_check_failed", error=str(exc))

            # Redact PII in output (don't restore - output should stay redacted)
            redacted_text, _ = self._redaction_service.redact(content)
            modified_messages.append({**msg, "content": redacted_text})

        return MiddlewareResult(
            success=True,
            should_continue=True,
            modified_output={"messages": modified_messages},
        )
