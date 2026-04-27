"""Butler Tool Retry Middleware.

Implements tool retry with exponential backoff for transient failures.
"""

import asyncio
import logging

from langchain.middleware.base import (
    ButlerBaseMiddleware,
    ButlerMiddlewareContext,
    MiddlewareResult,
)

import structlog

logger = structlog.get_logger(__name__)


class ButlerToolRetryMiddleware(ButlerBaseMiddleware):
    """Middleware for tool retry with backoff.

    Runs on POST_TOOL hook to retry failed tools.
    """

    def __init__(
        self,
        enabled: bool = True,
        max_retries: int = 3,
        base_delay_ms: float = 100,
        max_delay_ms: float = 5000,
        retryable_errors: list[str] | None = None,
    ):
        super().__init__(enabled=enabled)
        self._max_retries = max_retries
        self._base_delay_ms = base_delay_ms
        self._max_delay_ms = max_delay_ms
        self._retryable_errors = retryable_errors or [
            "timeout",
            "rate_limit",
            "connection",
            "temporary",
            "transient",
        ]

    def _is_retryable(self, error: str | None) -> bool:
        """Check if an error is retryable."""
        if not error:
            return False
        error_lower = error.lower()
        return any(keyword in error_lower for keyword in self._retryable_errors)

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay."""
        delay = min(
            self._base_delay_ms * (2 ** (attempt - 1)),
            self._max_delay_ms,
        )
        return delay / 1000.0  # Convert to seconds

    async def pre_tool(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Initialize retry context."""
        context.metadata["_butler_tool_retry_attempt"] = 0
        return MiddlewareResult(success=True, should_continue=True)

    async def post_tool(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Retry failed tools if retryable."""
        retry_attempt = context.metadata.get("_butler_tool_retry_attempt", 0)
        failed_tools = [
            result
            for result in context.tool_results
            if result.get("error") and self._is_retryable(result.get("error"))
        ]

        if not failed_tools or retry_attempt >= self._max_retries:
            return MiddlewareResult(success=True, should_continue=True)

        delay = self._calculate_delay(retry_attempt + 1)
        await asyncio.sleep(delay)

        retry_attempt += 1
        context.metadata["_butler_tool_retry_attempt"] = retry_attempt

        logger.info(
            "tool_retry_attempt",
            attempt=retry_attempt,
            max_retries=self._max_retries,
            failed_tool_count=len(failed_tools),
            delay_ms=delay * 1000,
        )

        # Signal that tools should be retried
        return MiddlewareResult(
            success=True,
            should_continue=True,
            metadata={"retry_tools": True, "retry_attempt": retry_attempt},
        )
