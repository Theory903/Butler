"""
Retry Policy - Intelligent Retry Policies with Backoff

Implements intelligent retry policies with exponential backoff.
Supports jitter, circuit breaker integration, and adaptive retry logic.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class BackoffStrategy(StrEnum):
    """Backoff strategy."""

    FIXED = "fixed"
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class RetryConfig:
    """Retry configuration."""

    policy_id: str
    max_attempts: int
    backoff_strategy: BackoffStrategy
    initial_delay_ms: int
    max_delay_ms: int
    jitter_enabled: bool
    jitter_factor: float
    retryable_errors: list[str]


@dataclass(frozen=True, slots=True)
class RetryAttempt:
    """Retry attempt record."""

    attempt_id: str
    policy_id: str
    attempt_number: int
    success: bool
    error: str | None
    delay_ms: float
    started_at: datetime
    completed_at: datetime


class RetryPolicy:
    """
    Intelligent retry policy with backoff.

    Features:
    - Multiple backoff strategies
    - Jitter support
    - Adaptive retry logic
    - Retry tracking
    """

    def __init__(self) -> None:
        """Initialize retry policy."""
        self._configs: dict[str, RetryConfig] = {}
        self._attempts: list[RetryAttempt] = []
        self._execute_callback: Callable[[int], Awaitable[Any]] | None = None

    def set_execute_callback(
        self,
        callback: Callable[[int], Awaitable[Any]],
    ) -> None:
        """
        Set callback for executing the operation.

        Args:
            callback: Async function to execute operation (receives attempt number)
        """
        self._execute_callback = callback

    def add_config(
        self,
        policy_id: str,
        max_attempts: int,
        backoff_strategy: BackoffStrategy,
        initial_delay_ms: int,
        max_delay_ms: int,
        jitter_enabled: bool = True,
        jitter_factor: float = 0.1,
        retryable_errors: list[str] | None = None,
    ) -> RetryConfig:
        """
        Add a retry configuration.

        Args:
            policy_id: Policy identifier
            max_attempts: Maximum retry attempts
            backoff_strategy: Backoff strategy
            initial_delay_ms: Initial delay in milliseconds
            max_delay_ms: Maximum delay in milliseconds
            jitter_enabled: Enable jitter
            jitter_factor: Jitter factor
            retryable_errors: List of retryable error types

        Returns:
            Retry configuration
        """
        config = RetryConfig(
            policy_id=policy_id,
            max_attempts=max_attempts,
            backoff_strategy=backoff_strategy,
            initial_delay_ms=initial_delay_ms,
            max_delay_ms=max_delay_ms,
            jitter_enabled=jitter_enabled,
            jitter_factor=jitter_factor,
            retryable_errors=retryable_errors or [],
        )

        self._configs[policy_id] = config

        logger.info(
            "retry_config_added",
            policy_id=policy_id,
            max_attempts=max_attempts,
            backoff_strategy=backoff_strategy,
        )

        return config

    async def execute_with_retry(
        self,
        policy_id: str,
    ) -> Any:
        """
        Execute operation with retry policy.

        Args:
            policy_id: Policy identifier

        Returns:
            Operation result
        """
        config = self._configs.get(policy_id)

        if not config:
            raise ValueError(f"Retry config not found: {policy_id}")

        if not self._execute_callback:
            raise ValueError("Execute callback not configured")

        last_error = None

        for attempt in range(1, config.max_attempts + 1):
            attempt_id = f"attempt-{datetime.now(UTC).timestamp()}-{attempt}"
            started_at = datetime.now(UTC)

            try:
                result = await self._execute_callback(attempt)

                # Success
                attempt_record = RetryAttempt(
                    attempt_id=attempt_id,
                    policy_id=policy_id,
                    attempt_number=attempt,
                    success=True,
                    error=None,
                    delay_ms=0,
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                )

                self._attempts.append(attempt_record)

                logger.info(
                    "operation_succeeded",
                    policy_id=policy_id,
                    attempt=attempt,
                )

                return result

            except Exception as e:
                last_error = e
                error_type = type(e).__name__

                # Check if error is retryable
                is_retryable = (
                    not config.retryable_errors
                    or error_type in config.retryable_errors
                    or any(pattern in str(e) for pattern in config.retryable_errors)
                )

                if not is_retryable or attempt == config.max_attempts:
                    # Not retryable or max attempts reached
                    attempt_record = RetryAttempt(
                        attempt_id=attempt_id,
                        policy_id=policy_id,
                        attempt_number=attempt,
                        success=False,
                        error=str(e),
                        delay_ms=0,
                        started_at=started_at,
                        completed_at=datetime.now(UTC),
                    )

                    self._attempts.append(attempt_record)

                    logger.error(
                        "operation_failed",
                        policy_id=policy_id,
                        attempt=attempt,
                        error=str(e),
                    )

                    raise

                # Calculate delay
                delay_ms = self._calculate_delay(config, attempt)

                # Apply jitter if enabled
                if config.jitter_enabled:
                    delay_ms = self._apply_jitter(delay_ms, config.jitter_factor)

                # Record failed attempt
                attempt_record = RetryAttempt(
                    attempt_id=attempt_id,
                    policy_id=policy_id,
                    attempt_number=attempt,
                    success=False,
                    error=str(e),
                    delay_ms=delay_ms,
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                )

                self._attempts.append(attempt_record)

                logger.warning(
                    "operation_failed_retrying",
                    policy_id=policy_id,
                    attempt=attempt,
                    next_attempt=attempt + 1,
                    delay_ms=delay_ms,
                    error=str(e),
                )

                # Wait before retry
                await asyncio.sleep(delay_ms / 1000)

        # Should not reach here
        if last_error:
            raise last_error
        return None

    def _calculate_delay(
        self,
        config: RetryConfig,
        attempt: int,
    ) -> float:
        """
        Calculate delay for retry attempt.

        Args:
            config: Retry configuration
            attempt: Attempt number

        Returns:
            Delay in milliseconds
        """
        if config.backoff_strategy == BackoffStrategy.FIXED:
            return float(config.initial_delay_ms)

        if config.backoff_strategy == BackoffStrategy.LINEAR:
            delay = config.initial_delay_ms * attempt
            return min(delay, config.max_delay_ms)

        if config.backoff_strategy == BackoffStrategy.EXPONENTIAL:
            delay = config.initial_delay_ms * (2 ** (attempt - 1))
            return min(delay, config.max_delay_ms)

        return float(config.initial_delay_ms)

    def _apply_jitter(
        self,
        delay_ms: float,
        jitter_factor: float,
    ) -> float:
        """
        Apply jitter to delay.

        Args:
            delay_ms: Base delay in milliseconds
            jitter_factor: Jitter factor

        Returns:
            Jittered delay in milliseconds
        """
        jitter = random.uniform(-jitter_factor, jitter_factor) * delay_ms
        return max(0, delay_ms + jitter)

    def get_attempts(
        self,
        policy_id: str | None = None,
        success: bool | None = None,
        limit: int = 100,
    ) -> list[RetryAttempt]:
        """
        Get retry attempts.

        Args:
            policy_id: Filter by policy
            success: Filter by success status
            limit: Maximum number of attempts

        Returns:
            List of retry attempts
        """
        attempts = self._attempts

        if policy_id:
            attempts = [a for a in attempts if a.policy_id == policy_id]

        if success is not None:
            attempts = [a for a in attempts if a.success == success]

        return sorted(attempts, key=lambda a: a.started_at, reverse=True)[:limit]

    def get_config(self, policy_id: str) -> RetryConfig | None:
        """
        Get retry configuration.

        Args:
            policy_id: Policy identifier

        Returns:
            Retry configuration or None
        """
        return self._configs.get(policy_id)

    def remove_config(self, policy_id: str) -> bool:
        """
        Remove retry configuration.

        Args:
            policy_id: Policy identifier

        Returns:
            True if removed
        """
        if policy_id in self._configs:
            del self._configs[policy_id]

            logger.info(
                "retry_config_removed",
                policy_id=policy_id,
            )

            return True
        return False

    def get_retry_stats(self) -> dict[str, Any]:
        """
        Get retry statistics.

        Returns:
            Retry statistics
        """
        total_attempts = len(self._attempts)
        successful_attempts = sum(1 for a in self._attempts if a.success)
        failed_attempts = total_attempts - successful_attempts

        policy_counts: dict[str, int] = {}
        for attempt in self._attempts:
            policy_counts[attempt.policy_id] = policy_counts.get(attempt.policy_id, 0) + 1

        avg_delay = 0
        if self._attempts:
            delays = [a.delay_ms for a in self._attempts if a.delay_ms > 0]
            if delays:
                avg_delay = sum(delays) / len(delays)

        return {
            "total_configs": len(self._configs),
            "total_attempts": total_attempts,
            "successful_attempts": successful_attempts,
            "failed_attempts": failed_attempts,
            "success_rate": successful_attempts / total_attempts if total_attempts > 0 else 0,
            "policy_breakdown": policy_counts,
            "average_delay_ms": avg_delay,
        }
