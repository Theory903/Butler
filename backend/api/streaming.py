"""Streaming Support.

Phase J: Streaming support for real-time responses using Server-Sent Events (SSE).
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from sse_starlette.sse import EventSourceResponse

import structlog

logger = structlog.get_logger(__name__)


class ButlerStreaming:
    """Streaming support for Butler using SSE.

    This class:
    - Provides Server-Sent Events streaming
    - Supports real-time response streaming
    - Handles chunked message delivery
    - Manages stream lifecycle
    """

    def __init__(self):
        """Initialize streaming support."""
        self._active_streams: dict[str, asyncio.Queue] = {}

    async def stream_response(
        self,
        request_id: str,
        response_generator: AsyncGenerator[dict[str, Any]],
    ) -> EventSourceResponse:
        """Stream response using SSE.

        Args:
            request_id: Request identifier
            response_generator: Async generator yielding response chunks

        Returns:
            EventSourceResponse for streaming
        """

        async def event_generator():
            try:
                async for chunk in response_generator:
                    yield {
                        "event": "message",
                        "data": json.dumps(chunk),
                    }
                yield {
                    "event": "done",
                    "data": json.dumps({"request_id": request_id}),
                }
            except Exception as e:
                logger.exception("stream_error", request_id=request_id)
                yield {
                    "event": "error",
                    "data": json.dumps({"error": str(e)}),
                }

        return EventSourceResponse(event_generator())

    async def create_stream(self, stream_id: str) -> asyncio.Queue:
        """Create a new stream.

        Args:
            stream_id: Stream identifier

        Returns:
            Queue for the stream
        """
        queue = asyncio.Queue()
        self._active_streams[stream_id] = queue
        logger.info("stream_created", stream_id=stream_id)
        return queue

    async def send_to_stream(self, stream_id: str, data: dict[str, Any]) -> None:
        """Send data to a stream.

        Args:
            stream_id: Stream identifier
            data: Data to send
        """
        queue = self._active_streams.get(stream_id)
        if queue:
            await queue.put(data)

    async def close_stream(self, stream_id: str) -> None:
        """Close a stream.

        Args:
            stream_id: Stream identifier
        """
        if stream_id in self._active_streams:
            del self._active_streams[stream_id]
            logger.info("stream_closed", stream_id=stream_id)

    def get_active_streams(self) -> list[str]:
        """Get list of active stream IDs.

        Returns:
            List of stream IDs
        """
        return list(self._active_streams.keys())


async def generate_response_chunks(
    message: str,
    chunk_size: int = 10,
) -> AsyncGenerator[dict[str, Any]]:
    """Generate response chunks for streaming.

    Args:
        message: Message to chunk
        chunk_size: Chunk size

    Yields:
        Response chunks
    """
    for i in range(0, len(message), chunk_size):
        chunk = message[i : i + chunk_size]
        yield {
            "chunk": chunk,
            "index": i // chunk_size,
            "done": False,
        }
        await asyncio.sleep(0.01)  # Simulate streaming delay

    yield {
        "chunk": "",
        "index": len(message) // chunk_size,
        "done": True,
    }
