"""
Dead Letter Queue - Dead Letter Queue Strategies

Implements dead letter queue strategies for failed messages.
Supports retry policies, message inspection, and reprocessing.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class DLQAction(StrEnum):
    """DLQ action."""

    RETRY = "retry"
    DISCARD = "discard"
    REPROCESS = "reprocess"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class DeadLetterMessage:
    """Dead letter message."""

    message_id: str
    original_queue: str
    payload: Any
    error_message: str
    error_type: str
    retry_count: int
    failed_at: datetime
    action: DLQAction


@dataclass(frozen=True, slots=True)
class DLQConfig:
    """Dead letter queue configuration."""

    queue_name: str
    max_size: int
    retention_seconds: int
    default_action: DLQAction


class DeadLetterQueue:
    """
    Dead letter queue for failed messages.

    Features:
    - Failed message storage
    - Retry policies
    - Message inspection
    - Reprocessing support
    """

    def __init__(self) -> None:
        """Initialize dead letter queue."""
        self._config: DLQConfig | None = None
        self._messages: list[DeadLetterMessage] = []
        self._reprocess_callback: Callable[[DeadLetterMessage], Awaitable[bool]] | None = None

    def configure(
        self,
        config: DLQConfig,
    ) -> DLQConfig:
        """
        Configure dead letter queue.

        Args:
            config: DLQ configuration

        Returns:
            DLQ configuration
        """
        self._config = config

        logger.info(
            "dlq_configured",
            queue_name=config.queue_name,
            max_size=config.max_size,
        )

        return config

    def set_reprocess_callback(
        self,
        callback: Callable[[DeadLetterMessage], Awaitable[bool]],
    ) -> None:
        """
        Set reprocess callback.

        Args:
            callback: Async function to reprocess message
        """
        self._reprocess_callback = callback

    async def add_message(
        self,
        message_id: str,
        original_queue: str,
        payload: Any,
        error_message: str,
        error_type: str,
        retry_count: int,
    ) -> bool:
        """
        Add a failed message to DLQ.

        Args:
            message_id: Message identifier
            original_queue: Original queue name
            payload: Message payload
            error_message: Error message
            error_type: Error type
            retry_count: Retry count

        Returns:
            True if added
        """
        if not self._config:
            return False

        # Check queue size
        if len(self._messages) >= self._config.max_size:
            logger.warning(
                "dlq_full",
                queue_name=self._config.queue_name,
                current_size=len(self._messages),
                max_size=self._config.max_size,
            )
            return False

        dead_letter = DeadLetterMessage(
            message_id=message_id,
            original_queue=original_queue,
            payload=payload,
            error_message=error_message,
            error_type=error_type,
            retry_count=retry_count,
            failed_at=datetime.now(UTC),
            action=self._config.default_action,
        )

        self._messages.append(dead_letter)

        logger.warning(
            "message_added_to_dlq",
            message_id=message_id,
            original_queue=original_queue,
            error_type=error_type,
        )

        return True

    async def retry_message(
        self,
        message_id: str,
    ) -> bool:
        """
        Retry a message from DLQ.

        Args:
            message_id: Message identifier

        Returns:
            True if retry initiated
        """
        message = self._get_message(message_id)

        if not message:
            return False

        if not self._reprocess_callback:
            logger.warning(
                "reprocess_callback_not_set",
                message_id=message_id,
            )
            return False

        try:
            success = await self._reprocess_callback(message)

            if success:
                self._remove_message(message_id)

                logger.info(
                    "message_retried_successfully",
                    message_id=message_id,
                )

                return True
            logger.warning(
                "message_retry_failed",
                message_id=message_id,
            )

            return False

        except Exception as e:
            logger.error(
                "message_retry_error",
                message_id=message_id,
                error=str(e),
            )

            return False

    async def reprocess_message(
        self,
        message_id: str,
    ) -> bool:
        """
        Reprocess a message from DLQ.

        Args:
            message_id: Message identifier

        Returns:
            True if reprocessed
        """
        return await self.retry_message(message_id)

    async def retry_all(
        self,
        limit: int = 100,
    ) -> int:
        """
        Retry all messages in DLQ.

        Args:
            limit: Maximum number of messages to retry

        Returns:
            Number of messages retried
        """
        messages = self.get_messages(limit=limit)

        retried = 0
        for message in messages:
            if await self.retry_message(message.message_id):
                retried += 1

        return retried

    def get_messages(
        self,
        original_queue: str | None = None,
        error_type: str | None = None,
        limit: int = 100,
    ) -> list[DeadLetterMessage]:
        """
        Get dead letter messages.

        Args:
            original_queue: Filter by original queue
            error_type: Filter by error type
            limit: Maximum number of messages

        Returns:
            List of dead letter messages
        """
        messages = self._messages

        if original_queue:
            messages = [m for m in messages if m.original_queue == original_queue]

        if error_type:
            messages = [m for m in messages if m.error_type == error_type]

        return sorted(messages, key=lambda m: m.failed_at, reverse=True)[:limit]

    def get_message(self, message_id: str) -> DeadLetterMessage | None:
        """
        Get a specific dead letter message.

        Args:
            message_id: Message identifier

        Returns:
            Dead letter message or None
        """
        return self._get_message(message_id)

    def _get_message(self, message_id: str) -> DeadLetterMessage | None:
        """
        Get message by ID.

        Args:
            message_id: Message identifier

        Returns:
            Dead letter message or None
        """
        for message in self._messages:
            if message.message_id == message_id:
                return message
        return None

    def _remove_message(self, message_id: str) -> bool:
        """
        Remove message from DLQ.

        Args:
            message_id: Message identifier

        Returns:
            True if removed
        """
        initial_count = len(self._messages)
        self._messages = [m for m in self._messages if m.message_id != message_id]

        removed = len(self._messages) < initial_count

        if removed:
            logger.info(
                "message_removed_from_dlq",
                message_id=message_id,
            )

        return removed

    def discard_message(self, message_id: str) -> bool:
        """
        Discard a message from DLQ.

        Args:
            message_id: Message identifier

        Returns:
            True if discarded
        """
        return self._remove_message(message_id)

    def set_action(
        self,
        message_id: str,
        action: DLQAction,
    ) -> bool:
        """
        Set action for a message.

        Args:
            message_id: Message identifier
            action: Action to set

        Returns:
            True if action set
        """
        for i, message in enumerate(self._messages):
            if message.message_id == message_id:
                updated_message = DeadLetterMessage(
                    message_id=message.message_id,
                    original_queue=message.original_queue,
                    payload=message.payload,
                    error_message=message.error_message,
                    error_type=message.error_type,
                    retry_count=message.retry_count,
                    failed_at=message.failed_at,
                    action=action,
                )

                self._messages[i] = updated_message

                logger.info(
                    "message_action_set",
                    message_id=message_id,
                    action=action,
                )

                return True
        return False

    def cleanup_old_messages(self, retention_seconds: int | None = None) -> int:
        """
        Clean up old messages.

        Args:
            retention_seconds: Override retention period

        Returns:
            Number of messages cleaned up
        """
        if not self._config:
            return 0

        retention = retention_seconds or self._config.retention_seconds
        cutoff = datetime.now(UTC) - timedelta(seconds=retention)

        initial_count = len(self._messages)

        self._messages = [m for m in self._messages if m.failed_at > cutoff]

        cleaned = initial_count - len(self._messages)

        if cleaned > 0:
            logger.info(
                "dlq_messages_cleaned",
                count=cleaned,
            )

        return cleaned

    def get_dlq_stats(self) -> dict[str, Any]:
        """
        Get DLQ statistics.

        Returns:
            DLQ statistics
        """
        total_messages = len(self._messages)

        error_type_counts: dict[str, int] = {}
        for message in self._messages:
            error_type_counts[message.error_type] = error_type_counts.get(message.error_type, 0) + 1

        action_counts: dict[str, int] = {}
        for message in self._messages:
            action_counts[message.action] = action_counts.get(message.action, 0) + 1

        return {
            "queue_name": self._config.queue_name if self._config else None,
            "total_messages": total_messages,
            "max_size": self._config.max_size if self._config else 0,
            "error_type_breakdown": error_type_counts,
            "action_breakdown": action_counts,
        }
