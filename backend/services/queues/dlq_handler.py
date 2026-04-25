"""
Dead Letter Queue Handler - DLQ Management and Retry Policies

Handles failed message routing, retry policies, and DLQ monitoring.
Implements exponential backoff, max retry limits, and alerting.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import structlog
from redis.asyncio import Redis

from infrastructure.redpanda_client import RedpandaClient
from services.tenant.namespace import get_tenant_namespace

logger = structlog.get_logger(__name__)


class RetryPolicy(StrEnum):
    """Retry policies for failed messages."""

    IMMEDIATE = "immediate"  # Retry immediately
    EXPONENTIAL_BACKOFF = "exponential_backoff"  # Exponential backoff
    FIXED_DELAY = "fixed_delay"  # Fixed delay between retries
    NO_RETRY = "no_retry"  # Send directly to DLQ


class ErrorCategory(StrEnum):
    """Error categories for routing decisions."""

    TRANSIENT = "transient"  # Temporary errors (network, timeout)
    PERMANENT = "permanent"  # Permanent errors (validation, schema)
    RATE_LIMIT = "rate_limit"  # Rate limit errors
    SYSTEM = "system"  # System errors


@dataclass(frozen=True, slots=True)
class RetryConfig:
    """Retry configuration for a topic."""

    max_retries: int
    initial_delay_ms: int
    max_delay_ms: int
    backoff_multiplier: float
    policy: RetryPolicy


# Default retry configurations per topic
DEFAULT_RETRY_CONFIGS: dict[str, RetryConfig] = {
    "butler.workflow.events": RetryConfig(
        max_retries=5,
        initial_delay_ms=1000,
        max_delay_ms=60000,
        backoff_multiplier=2.0,
        policy=RetryPolicy.EXPONENTIAL_BACKOFF,
    ),
    "butler.tool.executions": RetryConfig(
        max_retries=3,
        initial_delay_ms=500,
        max_delay_ms=30000,
        backoff_multiplier=2.0,
        policy=RetryPolicy.EXPONENTIAL_BACKOFF,
    ),
    "butler.audit.events": RetryConfig(
        max_retries=1,
        initial_delay_ms=1000,
        max_delay_ms=10000,
        backoff_multiplier=1.5,
        policy=RetryPolicy.FIXED_DELAY,
    ),
    "butler.billing.events": RetryConfig(
        max_retries=10,
        initial_delay_ms=2000,
        max_delay_ms=300000,  # 5 minutes
        backoff_multiplier=2.0,
        policy=RetryPolicy.EXPONENTIAL_BACKOFF,
    ),
    "butler.memory.compaction": RetryConfig(
        max_retries=3,
        initial_delay_ms=1000,
        max_delay_ms=60000,
        backoff_multiplier=2.0,
        policy=RetryPolicy.EXPONENTIAL_BACKOFF,
    ),
    "butler.realtime.delivery": RetryConfig(
        max_retries=1,
        initial_delay_ms=100,
        max_delay_ms=500,
        backoff_multiplier=1.0,
        policy=RetryPolicy.IMMEDIATE,
    ),
}


@dataclass(frozen=True, slots=True)
class FailedMessage:
    """Failed message metadata."""

    original_topic: str
    original_message: dict[str, Any]
    error: str
    error_category: ErrorCategory
    retry_count: int
    first_failed_at: datetime
    last_failed_at: datetime
    next_retry_at: datetime | None
    metadata: dict[str, Any]


class DLQHandler:
    """
    Handle dead letter queue operations.

    Routes failed messages to DLQ, manages retry policies,
    and monitors DLQ health.
    """

    def __init__(
        self,
        redpanda_client: RedpandaClient,
        redis: Redis,
        tenant_id: str | None = None,
    ) -> None:
        """Initialize DLQ handler."""
        self._redpanda = redpanda_client
        self._redis = redis
        self._tenant_id = tenant_id
        self._retry_configs = DEFAULT_RETRY_CONFIGS.copy()

    def _retry_key(self, message_id: str) -> str:
        """Generate Redis key for retry tracking using TenantNamespace."""
        if self._tenant_id:
            namespace = get_tenant_namespace(self._tenant_id)
            return f"{namespace.prefix}:dlq:retry:{message_id}"
        # Fallback to legacy format for non-tenant contexts
        return f"dlq:retry:{message_id}"

    def _dlq_stats_key(self, topic: str) -> str:
        """Generate Redis key for DLQ statistics using TenantNamespace."""
        if self._tenant_id:
            namespace = get_tenant_namespace(self._tenant_id)
            return f"{namespace.prefix}:dlq:stats:{topic}"
        # Fallback to legacy format for non-tenant contexts
        return f"dlq:stats:{topic}"

    def _categorize_error(self, error: str) -> ErrorCategory:
        """
        Categorize error based on error message.

        Args:
            error: Error message

        Returns:
            Error category
        """
        error_lower = error.lower()

        # Rate limit errors
        if "rate limit" in error_lower or "429" in error_lower:
            return ErrorCategory.RATE_LIMIT

        # Network/timeout errors (transient)
        if any(
            keyword in error_lower
            for keyword in [
                "timeout",
                "connection",
                "network",
                "temporary",
                "econnrefused",
                "etimedout",
                "503",
                "504",
            ]
        ):
            return ErrorCategory.TRANSIENT

        # Validation/schema errors (permanent)
        if any(
            keyword in error_lower
            for keyword in [
                "validation",
                "schema",
                "invalid",
                "malformed",
                "400",
                "422",
                "404",
            ]
        ):
            return ErrorCategory.PERMANENT

        # Default to system error
        return ErrorCategory.SYSTEM

    def get_retry_config(self, topic: str) -> RetryConfig:
        """
        Get retry configuration for a topic.

        Args:
            topic: Topic name

        Returns:
            Retry configuration
        """
        return self._retry_configs.get(topic, DEFAULT_RETRY_CONFIGS["butler.workflow.events"])

    def calculate_next_retry(
        self,
        retry_count: int,
        config: RetryConfig,
    ) -> datetime:
        """
        Calculate next retry time based on retry policy.

        Args:
            retry_count: Current retry count
            config: Retry configuration

        Returns:
            Next retry timestamp
        """
        if config.policy == RetryPolicy.NO_RETRY:
            return None

        if config.policy == RetryPolicy.IMMEDIATE:
            return datetime.now(UTC)

        if config.policy == RetryPolicy.FIXED_DELAY:
            delay_ms = config.initial_delay_ms
        elif config.policy == RetryPolicy.EXPONENTIAL_BACKOFF:
            delay_ms = min(
                config.initial_delay_ms * (config.backoff_multiplier**retry_count),
                config.max_delay_ms,
            )
        else:
            delay_ms = config.initial_delay_ms

        return datetime.now(UTC) + timedelta(milliseconds=delay_ms)

    async def handle_failed_message(
        self,
        original_topic: str,
        original_message: dict[str, Any],
        error: str,
        message_id: str,
        retry_count: int = 0,
        first_failed_at: datetime | None = None,
    ) -> bool:
        """
        Handle a failed message.

        Routes to DLQ or schedules retry based on policy.

        Args:
            original_topic: Original topic
            original_message: Original message payload
            error: Error message
            message_id: Unique message ID
            retry_count: Current retry count
            first_failed_at: First failure timestamp

        Returns:
            True if message was retried, False if sent to DLQ
        """
        error_category = self._categorize_error(error)
        retry_config = self.get_retry_config(original_topic)

        now = datetime.now(UTC)
        first_failed_at = first_failed_at or now

        # Check if we should retry
        should_retry = (
            error_category in [ErrorCategory.TRANSIENT, ErrorCategory.RATE_LIMIT]
            and retry_count < retry_config.max_retries
            and retry_config.policy != RetryPolicy.NO_RETRY
        )

        if should_retry:
            # Schedule retry
            next_retry_at = self.calculate_next_retry(retry_count, retry_config)

            # Store retry metadata in Redis
            if self._redis:
                retry_metadata = {
                    "original_topic": original_topic,
                    "original_message": json.dumps(original_message),
                    "error": error,
                    "error_category": error_category,
                    "retry_count": retry_count + 1,
                    "first_failed_at": first_failed_at.isoformat(),
                    "last_failed_at": now.isoformat(),
                    "next_retry_at": next_retry_at.isoformat() if next_retry_at else None,
                }

                await self._redis.hset(
                    self._retry_key(message_id),
                    mapping=retry_metadata,
                )
                await self._redis.expire(self._retry_key(message_id), 86400)  # 24 hours TTL

            logger.info(
                "message_scheduled_for_retry",
                message_id=message_id,
                topic=original_topic,
                retry_count=retry_count + 1,
                max_retries=retry_config.max_retries,
                next_retry_at=next_retry_at.isoformat() if next_retry_at else None,
                error_category=error_category,
            )

            return True
        # Send to DLQ
        await self.send_to_dlq(
            original_topic=original_topic,
            original_message=original_message,
            error=error,
            error_category=error_category,
            retry_count=retry_count,
            first_failed_at=first_failed_at,
            last_failed_at=now,
        )

        logger.warning(
            "message_sent_to_dlq",
            message_id=message_id,
            topic=original_topic,
            retry_count=retry_count,
            error_category=error_category,
            error=error,
        )

        return False

    async def send_to_dlq(
        self,
        original_topic: str,
        original_message: dict[str, Any],
        error: str,
        error_category: ErrorCategory,
        retry_count: int,
        first_failed_at: datetime,
        last_failed_at: datetime,
    ) -> None:
        """
        Send message to dead letter queue.

        Args:
            original_topic: Original topic
            original_message: Original message payload
            error: Error message
            error_category: Error category
            retry_count: Retry count
            first_failed_at: First failure timestamp
            last_failed_at: Last failure timestamp
        """
        dlq_topic = f"{original_topic}-dlq"

        dlq_message = {
            "original_topic": original_topic,
            "original_message": original_message,
            "error": error,
            "error_category": error_category,
            "retry_count": retry_count,
            "first_failed_at": first_failed_at.isoformat(),
            "last_failed_at": last_failed_at.isoformat(),
        }

        await self._redpanda.publish(
            topic=dlq_topic,
            value=dlq_message,
        )

        # Update DLQ statistics
        if self._redis:
            await self._redis.hincrby(self._dlq_stats_key(original_topic), "total_dlq", 1)
            await self._redis.hincrby(
                self._dlq_stats_key(original_topic), f"category:{error_category}", 1
            )
            await self._redis.expire(self._dlq_stats_key(original_topic), 86400 * 7)  # 7 days TTL

    async def get_dlq_statistics(self, topic: str) -> dict[str, Any]:
        """
        Get DLQ statistics for a topic.

        Args:
            topic: Topic name

        Returns:
            DLQ statistics
        """
        if self._redis:
            stats = await self._redis.hgetall(self._dlq_stats_key(topic))

            if stats:
                return {
                    "topic": topic,
                    "total_dlq": int(stats.get(b"total_dlq", b"0")),
                    "category_transient": int(stats.get(b"category:transient", b"0")),
                    "category_permanent": int(stats.get(b"category:permanent", b"0")),
                    "category_rate_limit": int(stats.get(b"category:rate_limit", b"0")),
                    "category_system": int(stats.get(b"category:system", b"0")),
                }

        return {
            "topic": topic,
            "total_dlq": 0,
            "category_transient": 0,
            "category_permanent": 0,
            "category_rate_limit": 0,
            "category_system": 0,
        }

    async def get_pending_retries(self) -> list[dict[str, Any]]:
        """
        Get all pending retries that are ready for retry.

        Returns:
            List of pending retry metadata
        """
        if not self._redis:
            return []

        # Get all retry keys
        pattern = "dlq:retry:*"
        keys = await self._redis.keys(pattern)

        pending_retries = []
        now = datetime.now(UTC)

        for key in keys:
            retry_data = await self._redis.hgetall(key)

            if retry_data:
                next_retry_at_str = retry_data.get(b"next_retry_at")
                if next_retry_at_str:
                    next_retry_at = datetime.fromisoformat(next_retry_at_str.decode())

                    if next_retry_at <= now:
                        pending_retries.append(
                            {
                                "message_id": key.decode().split(":")[-1],
                                "original_topic": retry_data.get(b"original_topic").decode(),
                                "retry_count": int(retry_data.get(b"retry_count").decode()),
                                "error": retry_data.get(b"error").decode(),
                            }
                        )

        return pending_retries

    async def retry_message(self, message_id: str) -> bool:
        """
        Retry a failed message.

        Args:
            message_id: Message ID to retry

        Returns:
            True if retry was successful, False otherwise
        """
        if not self._redis:
            return False

        retry_key = self._retry_key(message_id)
        retry_data = await self._redis.hgetall(retry_key)

        if not retry_data:
            logger.warning(
                "retry_metadata_not_found",
                message_id=message_id,
            )
            return False

        original_topic = retry_data.get(b"original_topic").decode()
        original_message = json.loads(retry_data.get(b"original_message").decode())
        retry_count = int(retry_data.get(b"retry_count").decode())
        retry_data.get(b"error").decode()

        # Publish back to original topic
        await self._redpanda.publish(
            topic=original_topic,
            value=original_message,
        )

        # Remove from retry tracking
        await self._redis.delete(retry_key)

        logger.info(
            "message_retried",
            message_id=message_id,
            topic=original_topic,
            retry_count=retry_count,
        )

        return True

    async def monitor_dlq_health(self, interval_seconds: int = 60) -> None:
        """
        Continuously monitor DLQ health.

        Args:
            interval_seconds: Monitoring interval
        """
        while True:
            try:
                # Get statistics for all topics
                for topic in DEFAULT_RETRY_CONFIGS:
                    stats = await self.get_dlq_statistics(topic)

                    # Alert on high DLQ rate
                    if stats["total_dlq"] > 100:
                        logger.warning(
                            "high_dlq_rate",
                            topic=topic,
                            total_dlq=stats["total_dlq"],
                        )

                # Check pending retries
                pending = await self.get_pending_retries()
                if pending:
                    logger.info(
                        "pending_retries",
                        count=len(pending),
                    )

                await asyncio.sleep(interval_seconds)

            except Exception as e:
                logger.exception(
                    "dlq_monitoring_error",
                    error=str(e),
                )
                await asyncio.sleep(interval_seconds)
