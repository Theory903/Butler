"""
Async Optimizer - Batching and Streaming Patterns

Implements async optimization patterns for high-performance operations.
Includes batching, streaming, and concurrent execution utilities.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")
R = TypeVar("R")


class BatchingStrategy(StrEnum):
    """Batching strategies."""

    SIZE_BASED = "size_based"
    TIME_BASED = "time_based"
    HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class BatchConfig:
    """Batch configuration."""

    max_size: int = 100
    max_wait_ms: int = 100
    strategy: BatchingStrategy = BatchingStrategy.HYBRID


class AsyncBatcher[T, R]:
    """
    Async batch processor for high-throughput operations.

    Features:
    - Size-based batching
    - Time-based batching
    - Hybrid batching
    - Async batch processing
    """

    def __init__(
        self,
        processor: Callable[[list[T]], Awaitable[list[R]]],
        config: BatchConfig | None = None,
    ) -> None:
        """Initialize async batcher."""
        self._processor = processor
        self._config = config or BatchConfig()
        self._batch: list[T] = []
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(1)

    async def add(self, item: T) -> list[R] | None:
        """
        Add item to batch and process if batch is full.

        Args:
            item: Item to add

        Returns:
            Processed results if batch was processed, None otherwise
        """
        async with self._lock:
            self._batch.append(item)

            if len(self._batch) >= self._config.max_size:
                return await self._process_batch()

            return None

    async def add_many(self, items: list[T]) -> list[R] | None:
        """
        Add multiple items to batch.

        Args:
            items: Items to add

        Returns:
            Processed results if batch was processed, None otherwise
        """
        async with self._lock:
            self._batch.extend(items)

            if len(self._batch) >= self._config.max_size:
                return await self._process_batch()

            return None

    async def flush(self) -> list[R] | None:
        """
        Flush current batch.

        Returns:
            Processed results
        """
        async with self._lock:
            if self._batch:
                return await self._process_batch()
            return None

    async def _process_batch(self) -> list[R]:
        """Process current batch."""
        if not self._batch:
            return []

        batch = self._batch.copy()
        self._batch.clear()

        logger.debug(
            "batch_processing",
            batch_size=len(batch),
        )

        try:
            return await self._processor(batch)
        except Exception as e:
            logger.exception(
                "batch_processing_failed",
                batch_size=len(batch),
                error=str(e),
            )
            raise


class AsyncStreamer[T]:
    """
    Async stream processor for streaming data.

    Features:
    - Async iteration
    - Backpressure handling
    - Buffer management
    """

    def __init__(
        self,
        buffer_size: int = 1000,
    ) -> None:
        """Initialize async streamer."""
        self._queue: asyncio.Queue[T | None] = asyncio.Queue(maxsize=buffer_size)
        self._closed = False

    async def produce(self, item: T) -> bool:
        """
        Produce item to stream.

        Args:
            item: Item to produce

        Returns:
            True if item was added, False if stream is closed
        """
        if self._closed:
            return False

        try:
            await self._queue.put(item)
            return True
        except asyncio.CancelledError:
            return False

    async def consume(self) -> AsyncGenerator[T]:
        """
        Consume items from stream.

        Yields:
            Items from stream
        """
        while not self._closed:
            item = await self._queue.get()

            if item is None:
                break

            yield item

    async def close(self) -> None:
        """Close stream."""
        self._closed = True
        await self._queue.put(None)

    def is_closed(self) -> bool:
        """Check if stream is closed."""
        return self._closed

    def size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()


class ConcurrentExecutor:
    """
    Concurrent executor for parallel async operations.

    Features:
    - Concurrency limiting
    - Error handling
    - Timeout management
    """

    def __init__(self, max_concurrency: int = 10) -> None:
        """Initialize concurrent executor."""
        self._max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def execute(
        self,
        tasks: list[Awaitable[R]],
        timeout: float | None = None,
    ) -> list[R]:
        """
        Execute tasks concurrently with limit.

        Args:
            tasks: List of async tasks
            timeout: Optional timeout in seconds

        Returns:
            List of results
        """

        async def _execute_with_limit(task: Awaitable[R]) -> R:
            async with self._semaphore:
                if timeout:
                    return await asyncio.wait_for(task, timeout=timeout)
                return await task

        results = await asyncio.gather(
            *[_execute_with_limit(task) for task in tasks],
            return_exceptions=True,
        )

        # Filter out exceptions
        valid_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(
                    "concurrent_execution_failed",
                    error=str(result),
                )
            else:
                valid_results.append(result)

        return valid_results

    async def execute_map(
        self,
        func: Callable[[T], Awaitable[R]],
        items: list[T],
        timeout: float | None = None,
    ) -> list[R]:
        """
        Execute function on items concurrently.

        Args:
            func: Async function to execute
            items: List of items
            timeout: Optional timeout in seconds

        Returns:
            List of results
        """
        tasks = [func(item) for item in items]
        return await self.execute(tasks, timeout)


class RateLimitedExecutor:
    """
    Rate-limited executor for controlled async operations.

    Features:
    - Rate limiting
    - Token bucket algorithm
    - Burst handling
    """

    def __init__(
        self,
        rate: float,  # requests per second
        burst: int = 10,
    ) -> None:
        """Initialize rate-limited executor."""
        self._rate = rate
        self._burst = burst
        self._tokens = burst
        self._last_update = datetime.now(UTC)
        self._lock = asyncio.Lock()

    async def execute(
        self,
        task: Awaitable[R],
    ) -> R:
        """
        Execute task with rate limiting.

        Args:
            task: Async task to execute

        Returns:
            Task result
        """
        await self._acquire_token()
        return await task

    async def _acquire_token(self) -> None:
        """Acquire token from bucket."""
        async with self._lock:
            now = datetime.now(UTC)
            elapsed = (now - self._last_update).total_seconds()

            # Refill tokens
            self._tokens = min(
                self._burst,
                self._tokens + elapsed * self._rate,
            )
            self._last_update = now

            # Wait if no tokens available
            if self._tokens < 1:
                wait_time = (1 - self._tokens) / self._rate
                await asyncio.sleep(wait_time)
                self._tokens = 0
            else:
                self._tokens -= 1

    async def execute_many(
        self,
        tasks: list[Awaitable[R]],
    ) -> list[R]:
        """
        Execute multiple tasks with rate limiting.

        Args:
            tasks: List of async tasks

        Returns:
            List of results
        """
        results = []
        for task in tasks:
            result = await self.execute(task)
            results.append(result)
        return results
