"""Retry middleware for LangChain agents.

Implements retry logic with circuit breaker integration.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain.middleware.base import (
    ButlerBaseMiddleware,
    ButlerMiddlewareContext,
    MiddlewareResult,
)

import structlog

logger = structlog.get_logger(__name__)


class RetryMiddleware(ButlerBaseMiddleware):
    """Middleware for tool execution retry with circuit breaker.

    This middleware:
    - Implements retry logic for tool execution failures
    - Integrates with Butler's CircuitBreakerRegistry
    - Configurable retry policy (max_retries, backoff)
    - Tracks retry attempts in state
    - Runs at PRE_TOOL and POST_TOOL hooks

    Production integration (Phase B.3):
    - Real circuit breaker integration
    - Exponential backoff for retries
    - Per-tool retry limits
    - Circuit breaker state tracking
    """

    def __init__(
        self,
        enabled: bool = True,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        backoff_max_ms: int = 5000,
        circuit_breaker_registry: Any = None,
    ):
        """Initialize retry middleware.

        Args:
            enabled: Whether middleware is enabled
            max_retries: Maximum number of retry attempts
            backoff_base: Base multiplier for exponential backoff
            backoff_max_ms: Maximum backoff delay in milliseconds
            circuit_breaker_registry: Butler's CircuitBreakerRegistry
        """
        super().__init__(enabled=enabled)
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_max_ms = backoff_max_ms
        self._circuit_breaker_registry = circuit_breaker_registry

    async def pre_tool(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Check circuit breaker state before tool execution.

        Args:
            context: ButlerMiddlewareContext with tool call info

        Returns:
            MiddlewareResult with potential blocking
        """
        if not self.enabled:
            return MiddlewareResult(success=True, should_continue=True)

        # Check circuit breaker if available
        if self._circuit_breaker_registry:
            tool_name = context.metadata.get("tool_name", "unknown")
            breaker = self._circuit_breaker_registry.get(f"tool:{tool_name}")

            if breaker and breaker.is_open():
                logger.warning(
                    "retry_middleware_circuit_open",
                    tool_name=tool_name,
                )
                return MiddlewareResult(
                    success=False,
                    should_continue=False,
                    error=f"Circuit breaker open for tool: {tool_name}",
                )

        return MiddlewareResult(success=True, should_continue=True)

    async def post_tool(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Handle tool execution failures with retry logic.

        Args:
            context: ButlerMiddlewareContext with tool result

        Returns:
            MiddlewareResult with retry decision
        """
        if not self.enabled:
            return MiddlewareResult(success=True, should_continue=True)

        # Check if tool execution failed
        tool_results = context.tool_results
        if not tool_results:
            return MiddlewareResult(success=True, should_continue=True)

        for result in tool_results:
            if not result.get("success", True):
                tool_name = result.get("name", "unknown")
                error = result.get("error", "Unknown error")

                # Check retry count from state
                retry_count = context.metadata.get("retry_count", 0)

                if retry_count < self._max_retries:
                    # Calculate backoff delay
                    delay_ms = self._calculate_backoff(retry_count)
                    logger.info(
                        "retry_middleware_retry_scheduled",
                        tool_name=tool_name,
                        retry_count=retry_count + 1,
                        delay_ms=delay_ms,
                        error=error,
                    )

                    # Update metadata for retry
                    context.metadata.update(
                        {
                            "retry_count": retry_count + 1,
                            "retry_delay_ms": delay_ms,
                            "should_retry": True,
                        }
                    )

                    return MiddlewareResult(
                        success=True,
                        should_continue=True,
                        metadata=context.metadata,
                    )
                logger.warning(
                    "retry_middleware_max_retries_exceeded",
                    tool_name=tool_name,
                    max_retries=self._max_retries,
                    error=error,
                )

                # Trip circuit breaker if available
                if self._circuit_breaker_registry:
                    breaker = self._circuit_breaker_registry.get(f"tool:{tool_name}")
                    if breaker:
                        breaker.record_failure()

                return MiddlewareResult(
                    success=False,
                    should_continue=False,
                    error=f"Max retries exceeded for tool: {tool_name}",
                )

        # Reset retry count on success
        context.metadata["retry_count"] = 0
        return MiddlewareResult(success=True, should_continue=True)

    def _calculate_backoff(self, retry_count: int) -> int:
        """Calculate exponential backoff delay.

        Args:
            retry_count: Current retry attempt number

        Returns:
            Backoff delay in milliseconds
        """
        delay_ms = int((self._backoff_base**retry_count) * 100)
        return min(delay_ms, self._backoff_max_ms)

    async def execute_with_retry(
        self,
        tool_name: str,
        tool_func: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute a tool function with retry logic.

        Args:
            tool_name: Name of the tool being executed
            tool_func: Tool function to execute
            *args: Positional arguments for tool function
            **kwargs: Keyword arguments for tool function

        Returns:
            Tool function result

        Raises:
            Exception: If max retries exceeded
        """
        last_error = None

        for attempt in range(self._max_retries + 1):
            try:
                return await tool_func(*args, **kwargs)
            except Exception as e:
                last_error = e

                if attempt < self._max_retries:
                    delay_ms = self._calculate_backoff(attempt)
                    logger.info(
                        "retry_middleware_executing_retry",
                        tool_name=tool_name,
                        attempt=attempt + 1,
                        delay_ms=delay_ms,
                    )
                    await asyncio.sleep(delay_ms / 1000.0)
                else:
                    logger.error(
                        "retry_middleware_all_retries_failed",
                        tool_name=tool_name,
                        max_retries=self._max_retries,
                    )
                    # Trip circuit breaker if available
                    if self._circuit_breaker_registry:
                        breaker = self._circuit_breaker_registry.get(f"tool:{tool_name}")
                        if breaker:
                            breaker.record_failure()
                    raise

        raise last_error  # Should never reach here
