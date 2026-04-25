"""Butler Content Guard Middleware.

Wraps ContentGuard for safety checks on inputs and outputs.
"""

import logging
from typing import Any

from langchain.middleware.base import (
    ButlerBaseMiddleware,
    ButlerMiddlewareContext,
    MiddlewareOrder,
    MiddlewareResult,
)
from services.security.safety import ContentGuard

logger = logging.getLogger(__name__)


class ButlerContentGuardMiddleware(ButlerBaseMiddleware):
    """Middleware for content safety checks.

    Runs on PRE_MODEL and POST_MODEL hooks to check safety.
    """

    def __init__(
        self,
        content_guard: ContentGuard | None = None,
        enabled: bool = True,
        block_unsafe: bool = True,
    ):
        super().__init__(enabled=enabled)
        self._content_guard = content_guard
        self._block_unsafe = block_unsafe

    async def _check_messages(
        self, messages: list[dict[str, Any]], context: ButlerMiddlewareContext
    ) -> MiddlewareResult:
        """Check safety of messages."""
        if not self._content_guard:
            return MiddlewareResult(success=True, should_continue=True)

        for msg in messages:
            content = msg.get("content", "")
            if not content:
                continue

            try:
                safety_result = await self._content_guard.check(content)
                if not safety_result.get("safe", True):
                    if self._block_unsafe:
                        logger.warning(
                            "unsafe_content_blocked",
                            account_id=context.account_id,
                            session_id=context.session_id,
                            reason=safety_result.get("reason"),
                            categories=safety_result.get("categories"),
                        )
                        return MiddlewareResult(
                            success=False,
                            should_continue=False,
                            error=f"Content blocked: {safety_result.get('reason')}",
                            metadata={"safety_result": safety_result},
                        )
                    else:
                        logger.warning(
                            "unsafe_content_logged",
                            account_id=context.account_id,
                            session_id=context.session_id,
                            reason=safety_result.get("reason"),
                            categories=safety_result.get("categories"),
                        )
            except Exception as exc:
                logger.warning("content_guard_check_failed", error=str(exc))

        return MiddlewareResult(success=True, should_continue=True)

    async def pre_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Check input safety before model inference."""
        if not context.messages:
            return MiddlewareResult(success=True, should_continue=True)

        return await self._check_messages(context.messages, context)

    async def post_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Check output safety after model inference."""
        if not context.messages:
            return MiddlewareResult(success=True, should_continue=True)

        return await self._check_messages(context.messages, context)
