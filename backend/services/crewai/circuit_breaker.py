"""Circuit breaker for CrewAI integration.

This module provides circuit breaker pattern implementation for CrewAI
calls to prevent cascading failures and improve system resilience.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Circuit breaker for CrewAI calls.

    Implements the circuit breaker pattern to prevent cascading failures
    when CrewAI service is experiencing issues.

    States:
    - CLOSED: Normal operation, calls are allowed
    - OPEN: Circuit is open, calls are blocked
    - HALF_OPEN: Circuit is testing if service has recovered
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type[Exception] = Exception,
    ) -> None:
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit.
            recovery_timeout: Seconds to wait before attempting recovery.
            expected_exception: Exception type to count as failure.
        """
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._expected_exception = expected_exception

        self._failure_count = 0
        self._last_failure_time = 0.0
        self._state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    async def call(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Execute function with circuit breaker protection.

        Args:
            func: Function to execute.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Function result.

        Raises:
            Exception: If circuit is open or function fails.
        """
        if self._state == "OPEN":
            if self._should_attempt_reset():
                self._state = "HALF_OPEN"
                logger.info("Circuit breaker attempting reset")
            else:
                raise Exception("Circuit breaker is OPEN - calls are blocked")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self._expected_exception as e:
            self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt circuit reset.

        Returns:
            True if reset should be attempted.
        """
        return time.time() - self._last_failure_time >= self._recovery_timeout

    def _on_success(self) -> None:
        """Handle successful function call."""
        self._failure_count = 0
        if self._state == "HALF_OPEN":
            self._state = "CLOSED"
            logger.info("Circuit breaker reset to CLOSED")

    def _on_failure(self) -> None:
        """Handle failed function call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._failure_count >= self._failure_threshold:
            if self._state != "OPEN":
                self._state = "OPEN"
                logger.warning(
                    f"Circuit breaker opened after {self._failure_count} failures"
                )

    def get_state(self) -> str:
        """Get current circuit breaker state.

        Returns:
            Current state (CLOSED, OPEN, HALF_OPEN).
        """
        return self._state

    def reset(self) -> None:
        """Reset circuit breaker to CLOSED state."""
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._state = "CLOSED"
        logger.info("Circuit breaker manually reset to CLOSED")
