"""StreamBuffer — v3.1 Real-time Audio Ingestion.

Handles the buffering and pre-processing of partial audio chunks
received via WebSockets or streaming APIs.
"""

import asyncio
import io
import time

import structlog
from opentelemetry import trace

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class StreamBuffer:
    """Stateful buffer for join-and-process audio streaming."""

    def __init__(self, sample_rate: int = 16000, chunk_size_ms: int = 500):
        self.sample_rate = sample_rate
        self.chunk_size_samples = int(sample_rate * (chunk_size_ms / 1000))
        self._buffer = io.BytesIO()
        self._last_flush_ts = time.monotonic()
        self._lock = asyncio.Lock()

    async def push(self, chunk: bytes):
        """Add a new audio chunk to the buffer."""
        async with self._lock:
            self._buffer.write(chunk)

    async def consume(self, min_bytes: int = 3200) -> bytes | None:
        """
        Return the buffered data if it exceeds min_bytes (approx 100ms at 16k).
        Returns None if buffer is too small.
        """
        async with self._lock:
            data = self._buffer.getvalue()
            if len(data) < min_bytes:
                return None

            # Reset buffer
            self._buffer = io.BytesIO()
            self._last_flush_ts = time.monotonic()
            return data

    def get_stats(self) -> dict:
        return {
            "buffer_size_bytes": len(self._buffer.getvalue()),
            "last_flush_age_s": round(time.monotonic() - self._last_flush_ts, 2),
        }

    async def clear(self):
        async with self._lock:
            self._buffer = io.BytesIO()
