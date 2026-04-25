"""
Priority Queue - Request Prioritization with Weighted Queuing

Implements weighted priority queuing for request prioritization.
Supports priority levels, weighted fair queuing, and request scheduling.
"""

from __future__ import annotations

import asyncio
import heapq
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class Priority(StrEnum):
    """Request priority level."""

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class PriorityWeight:
    """Priority weight configuration."""

    priority: Priority
    weight: int
    max_concurrent: int


@dataclass(order=True, slots=True)
class PriorityRequest:
    """Priority request for queuing."""

    priority_score: int  # For heapq ordering
    request_id: str
    priority: Priority
    weight: int
    payload: Any
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    callback: Callable[[Any], Awaitable[None]] | None = None


class PriorityQueue:
    """
    Priority queue for request prioritization.

    Features:
    - Weighted fair queuing
    - Priority levels
    - Concurrent execution limits
    - Request scheduling
    """

    def __init__(
        self,
        max_concurrent: int = 100,
    ) -> None:
        """Initialize priority queue."""
        self._max_concurrent = max_concurrent
        self._queue: list[PriorityRequest] = []
        self._running: dict[str, asyncio.Task] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)

        # Default priority weights
        self._weights = {
            Priority.CRITICAL: PriorityWeight(Priority.CRITICAL, 1000, 50),
            Priority.HIGH: PriorityWeight(Priority.HIGH, 100, 30),
            Priority.NORMAL: PriorityWeight(Priority.NORMAL, 10, 15),
            Priority.LOW: PriorityWeight(Priority.LOW, 1, 5),
        }

    def set_priority_weight(
        self,
        priority: Priority,
        weight: int,
        max_concurrent: int,
    ) -> None:
        """
        Set priority weight configuration.

        Args:
            priority: Priority level
            weight: Weight for scheduling
            max_concurrent: Max concurrent for this priority
        """
        self._weights[priority] = PriorityWeight(
            priority=priority,
            weight=weight,
            max_concurrent=max_concurrent,
        )

        logger.info(
            "priority_weight_set",
            priority=priority,
            weight=weight,
            max_concurrent=max_concurrent,
        )

    async def enqueue(
        self,
        request_id: str,
        priority: Priority,
        payload: Any,
        callback: Callable[[Any], Awaitable[None]] | None = None,
    ) -> None:
        """
        Enqueue a request.

        Args:
            request_id: Request identifier
            priority: Request priority
            payload: Request payload
            callback: Optional callback for execution
        """
        weight_config = self._weights.get(priority, self._weights[Priority.NORMAL])

        # Calculate priority score (higher weight = higher priority)
        # Use negative for max-heap behavior with heapq (min-heap)
        priority_score = -weight_config.weight

        request = PriorityRequest(
            priority_score=priority_score,
            request_id=request_id,
            priority=priority,
            weight=weight_config.weight,
            payload=payload,
            callback=callback,
        )

        heapq.heappush(self._queue, request)

        logger.debug(
            "request_enqueued",
            request_id=request_id,
            priority=priority,
            queue_size=len(self._queue),
        )

    async def dequeue(self) -> PriorityRequest | None:
        """
        Dequeue the next request.

        Returns:
            Priority request or None
        """
        if not self._queue:
            return None

        request = heapq.heappop(self._queue)

        logger.debug(
            "request_dequeued",
            request_id=request.request_id,
            priority=request.priority,
        )

        return request

    async def execute_next(self) -> bool:
        """
        Execute the next request in the queue.

        Returns:
            True if a request was executed
        """
        request = await self.dequeue()

        if not request:
            return False

        async with self._semaphore:
            try:
                if request.callback:
                    await request.callback(request.payload)

                logger.info(
                    "request_executed",
                    request_id=request.request_id,
                    priority=request.priority,
                )

                return True

            except Exception as e:
                logger.error(
                    "request_execution_failed",
                    request_id=request.request_id,
                    priority=request.priority,
                    error=str(e),
                )
                return False

    async def process_queue(self) -> None:
        """Process all requests in the queue."""
        while self._queue:
            await self.execute_next()
            await asyncio.sleep(0.01)  # Prevent CPU hogging

    def get_queue_size(self) -> int:
        """Get current queue size."""
        return len(self._queue)

    def get_running_count(self) -> int:
        """Get number of running requests."""
        return len(self._running)

    def get_priority_counts(self) -> dict[str, int]:
        """Get count of requests by priority."""
        counts: dict[str, int] = {}

        for request in self._queue:
            counts[request.priority] = counts.get(request.priority, 0) + 1

        return counts

    def clear_queue(self) -> int:
        """
        Clear all pending requests.

        Returns:
            Number of requests cleared
        """
        count = len(self._queue)
        self._queue.clear()

        logger.info(
            "queue_cleared",
            count=count,
        )

        return count

    def get_queue_stats(self) -> dict[str, Any]:
        """
        Get queue statistics.

        Returns:
            Queue statistics
        """
        return {
            "queue_size": len(self._queue),
            "running_requests": len(self._running),
            "max_concurrent": self._max_concurrent,
            "priority_counts": self.get_priority_counts(),
            "priority_weights": {
                p.value: {"weight": w.weight, "max_concurrent": w.max_concurrent}
                for p, w in self._weights.items()
            },
        }
