"""
Message Queue - Advanced Message Queue Management

Implements advanced message queue management.
Supports priority queues, batching, and message ordering guarantees.
"""

from __future__ import annotations

import asyncio
import heapq
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class MessagePriority(StrEnum):
    """Message priority."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class Message:
    """Message object."""

    message_id: str
    queue_name: str
    payload: Any
    priority: MessagePriority
    headers: dict[str, str]
    created_at: datetime
    retry_count: int
    max_retries: int


@dataclass(frozen=True, slots=True)
class QueueConfig:
    """Queue configuration."""

    queue_name: str
    max_size: int
    max_retries: int
    retention_seconds: int
    batch_size: int
    batch_timeout_ms: int


class MessageQueue:
    """
    Advanced message queue.

    Features:
    - Priority queues
    - Message batching
    - Retry logic
    - Ordering guarantees
    """

    def __init__(self) -> None:
        """Initialize message queue."""
        self._queues: dict[str, QueueConfig] = {}
        self._messages: dict[str, list[Message]] = {}  # queue_name -> messages
        self._priority_queues: dict[
            str, list[tuple[int, Message]]
        ] = {}  # queue_name -> (priority, message)
        self._consumer_callback: Callable[[Message], Awaitable[bool]] | None = None
        self._consumer_tasks: dict[str, asyncio.Task] = {}
        self._message_counter = 0

    def set_consumer_callback(
        self,
        callback: Callable[[Message], Awaitable[bool]],
    ) -> None:
        """
        Set consumer callback.

        Args:
            callback: Async function to consume message
        """
        self._consumer_callback = callback

    def create_queue(
        self,
        config: QueueConfig,
    ) -> QueueConfig:
        """
        Create a message queue.

        Args:
            config: Queue configuration

        Returns:
            Queue configuration
        """
        self._queues[config.queue_name] = config
        self._messages[config.queue_name] = []
        self._priority_queues[config.queue_name] = []

        logger.info(
            "queue_created",
            queue_name=config.queue_name,
            max_size=config.max_size,
        )

        return config

    async def publish(
        self,
        queue_name: str,
        payload: Any,
        priority: MessagePriority = MessagePriority.NORMAL,
        headers: dict[str, str] | None = None,
    ) -> str | None:
        """
        Publish a message to queue.

        Args:
            queue_name: Queue name
            payload: Message payload
            priority: Message priority
            headers: Optional headers

        Returns:
            Message ID or None
        """
        config = self._queues.get(queue_name)

        if not config:
            return None

        # Check queue size
        if len(self._messages[queue_name]) >= config.max_size:
            logger.warning(
                "queue_full",
                queue_name=queue_name,
                current_size=len(self._messages[queue_name]),
                max_size=config.max_size,
            )
            return None

        self._message_counter += 1
        message_id = f"msg-{queue_name}-{self._message_counter}"

        message = Message(
            message_id=message_id,
            queue_name=queue_name,
            payload=payload,
            priority=priority,
            headers=headers or {},
            created_at=datetime.now(UTC),
            retry_count=0,
            max_retries=config.max_retries,
        )

        # Add to priority queue
        priority_value = self._get_priority_value(priority)
        heapq.heappush(self._priority_queues[queue_name], (priority_value, message))
        self._messages[queue_name].append(message)

        logger.debug(
            "message_published",
            message_id=message_id,
            queue_name=queue_name,
            priority=priority,
        )

        return message_id

    def _get_priority_value(self, priority: MessagePriority) -> int:
        """
        Get numeric priority value.

        Args:
            priority: Message priority

        Returns:
            Numeric priority (lower = higher priority)
        """
        priority_map = {
            MessagePriority.CRITICAL: 0,
            MessagePriority.HIGH: 1,
            MessagePriority.NORMAL: 2,
            MessagePriority.LOW: 3,
        }
        return priority_map.get(priority, 2)

    async def consume(self, queue_name: str) -> Message | None:
        """
        Consume a message from queue.

        Args:
            queue_name: Queue name

        Returns:
            Message or None
        """
        config = self._queues.get(queue_name)

        if not config:
            return None

        if not self._priority_queues[queue_name]:
            return None

        # Get highest priority message
        _, message = heapq.heappop(self._priority_queues[queue_name])

        # Remove from messages list
        self._messages[queue_name] = [
            m for m in self._messages[queue_name] if m.message_id != message.message_id
        ]

        logger.debug(
            "message_consumed",
            message_id=message.message_id,
            queue_name=queue_name,
        )

        return message

    async def start_consumer(self, queue_name: str) -> None:
        """
        Start consumer for queue.

        Args:
            queue_name: Queue name
        """
        config = self._queues.get(queue_name)

        if not config:
            return

        if not self._consumer_callback:
            raise ValueError("Consumer callback not configured")

        if queue_name not in self._consumer_tasks or self._consumer_tasks[queue_name].done():
            self._consumer_tasks[queue_name] = asyncio.create_task(
                self._consumer_loop(queue_name, config)
            )

    async def _consumer_loop(
        self,
        queue_name: str,
        config: QueueConfig,
    ) -> None:
        """
        Consumer loop for queue.

        Args:
            queue_name: Queue name
            config: Queue configuration
        """
        while True:
            try:
                message = await self.consume(queue_name)

                if message:
                    success = await self._consumer_callback(message)

                    if not success:
                        # Retry logic
                        if message.retry_count < message.max_retries:
                            await self._retry_message(message)
                        else:
                            logger.warning(
                                "message_max_retries_exceeded",
                                message_id=message.message_id,
                                retry_count=message.retry_count,
                            )

                # Wait before next poll
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(
                    "consumer_loop_error",
                    queue_name=queue_name,
                    error=str(e),
                )
                await asyncio.sleep(1)

    async def _retry_message(self, message: Message) -> None:
        """
        Retry a message.

        Args:
            message: Message to retry
        """
        retried_message = Message(
            message_id=message.message_id,
            queue_name=message.queue_name,
            payload=message.payload,
            priority=message.priority,
            headers=message.headers,
            created_at=message.created_at,
            retry_count=message.retry_count + 1,
            max_retries=message.max_retries,
        )

        priority_value = self._get_priority_value(retried_message.priority)
        heapq.heappush(
            self._priority_queues[retried_message.queue_name], (priority_value, retried_message)
        )
        self._messages[retried_message.queue_name].append(retried_message)

        logger.debug(
            "message_retried",
            message_id=retried_message.message_id,
            retry_count=retried_message.retry_count,
        )

    async def consume_batch(
        self,
        queue_name: str,
    ) -> list[Message]:
        """
        Consume a batch of messages.

        Args:
            queue_name: Queue name

        Returns:
            List of messages
        """
        config = self._queues.get(queue_name)

        if not config:
            return []

        batch = []
        batch_size = min(config.batch_size, len(self._priority_queues[queue_name]))

        for _ in range(batch_size):
            message = await self.consume(queue_name)
            if message:
                batch.append(message)

        logger.debug(
            "batch_consumed",
            queue_name=queue_name,
            batch_size=len(batch),
        )

        return batch

    def stop_consumer(self, queue_name: str) -> bool:
        """
        Stop consumer for queue.

        Args:
            queue_name: Queue name

        Returns:
            True if stopped
        """
        if queue_name in self._consumer_tasks:
            task = self._consumer_tasks[queue_name]
            if not task.done():
                task.cancel()

            del self._consumer_tasks[queue_name]

            logger.info(
                "consumer_stopped",
                queue_name=queue_name,
            )

            return True
        return False

    def get_queue_size(self, queue_name: str) -> int:
        """
        Get queue size.

        Args:
            queue_name: Queue name

        Returns:
            Queue size
        """
        return len(self._messages.get(queue_name, []))

    def cleanup_old_messages(self, queue_name: str) -> int:
        """
        Clean up old messages.

        Args:
            queue_name: Queue name

        Returns:
            Number of messages cleaned up
        """
        config = self._queues.get(queue_name)

        if not config:
            return 0

        cutoff = datetime.now(UTC) - timedelta(seconds=config.retention_seconds)

        initial_count = len(self._messages[queue_name])

        # Filter old messages
        self._messages[queue_name] = [
            m for m in self._messages[queue_name] if m.created_at > cutoff
        ]

        # Rebuild priority queue
        self._priority_queues[queue_name] = [
            (self._get_priority_value(m.priority), m) for m in self._messages[queue_name]
        ]
        heapq.heapify(self._priority_queues[queue_name])

        cleaned = initial_count - len(self._messages[queue_name])

        if cleaned > 0:
            logger.info(
                "old_messages_cleaned",
                queue_name=queue_name,
                count=cleaned,
            )

        return cleaned

    def get_queue_stats(self, queue_name: str | None = None) -> dict[str, Any]:
        """
        Get queue statistics.

        Args:
            queue_name: Optional queue name

        Returns:
            Queue statistics
        """
        if queue_name:
            messages = self._messages.get(queue_name, [])
            return {
                "queue_name": queue_name,
                "size": len(messages),
                "priority_breakdown": {
                    p: sum(1 for m in messages if m.priority == p) for p in MessagePriority
                },
            }

        # All queues
        total_messages = sum(len(msgs) for msgs in self._messages.values())

        return {
            "total_queues": len(self._queues),
            "total_messages": total_messages,
            "active_consumers": sum(1 for t in self._consumer_tasks.values() if not t.done()),
        }
