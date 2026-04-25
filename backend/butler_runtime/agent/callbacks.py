"""Event sink and callbacks for Butler Unified Agent Runtime.

Adapted from Hermes callback patterns with Butler-specific event streaming.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class ButlerEventSink:
    """Event sink for streaming Butler agent events.

    This class provides a unified interface for streaming events from the
    agent runtime to various consumers (WebSocket, API, logging, etc.).
    """

    def __init__(self) -> None:
        """Initialize event sink."""
        self._callbacks: dict[str, list[Callable[..., Awaitable[None]]]] = {}

    def register_callback(self, event_type: str, callback: Callable[..., Awaitable[None]]) -> None:
        """Register a callback for a specific event type.

        Args:
            event_type: Type of event to listen for
            callback: Async callback function
        """
        if event_type not in self._callbacks:
            self._callbacks[event_type] = []
        self._callbacks[event_type].append(callback)

    async def emit(self, event_type: str, **kwargs: Any) -> None:
        """Emit an event to all registered callbacks.

        Args:
            event_type: Type of event
            **kwargs: Event payload
        """
        if event_type not in self._callbacks:
            return

        for callback in self._callbacks[event_type]:
            try:
                await callback(**kwargs)
            except Exception as e:
                logger.exception(f"Error in callback for event {event_type}: {e}")

    async def emit_token(self, token: str, metadata: dict[str, Any] | None = None) -> None:
        """Emit a token event (streaming response).

        Args:
            token: Token content
            metadata: Optional metadata (model, timestamp, etc.)
        """
        await self.emit(
            "token",
            token=token,
            timestamp=datetime.now(UTC).isoformat(),
            metadata=metadata or {},
        )

    async def emit_tool_start(self, tool_name: str, tool_args: dict[str, Any]) -> None:
        """Emit a tool start event.

        Args:
            tool_name: Name of the tool being called
            tool_args: Arguments passed to the tool
        """
        await self.emit(
            "tool_start",
            tool_name=tool_name,
            tool_args=tool_args,
            timestamp=datetime.now(UTC).isoformat(),
        )

    async def emit_tool_complete(
        self,
        tool_name: str,
        result: Any,
        duration_ms: int,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Emit a tool completion event.

        Args:
            tool_name: Name of the tool
            result: Result from tool execution
            duration_ms: Execution duration in milliseconds
            metadata: Optional metadata (tokens, cost, etc.)
        """
        await self.emit(
            "tool_complete",
            tool_name=tool_name,
            result=str(result)[:1000] if result else "",  # Truncate large results
            duration_ms=duration_ms,
            timestamp=datetime.now(UTC).isoformat(),
            metadata=metadata or {},
        )

    async def emit_tool_error(self, tool_name: str, error: str, duration_ms: int) -> None:
        """Emit a tool error event.

        Args:
            tool_name: Name of the tool
            error: Error message
            duration_ms: Execution duration in milliseconds
        """
        await self.emit(
            "tool_error",
            tool_name=tool_name,
            error=error,
            duration_ms=duration_ms,
            timestamp=datetime.now(UTC).isoformat(),
        )

    async def emit_thinking(self, content: str) -> None:
        """Emit a thinking event (model reasoning).

        Args:
            content: Thinking/reasoning content
        """
        await self.emit(
            "thinking",
            content=content,
            timestamp=datetime.now(UTC).isoformat(),
        )

    async def emit_complete(
        self,
        final_response: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Emit a completion event.

        Args:
            final_response: Final response from the agent
            metadata: Optional metadata (tokens, cost, duration, etc.)
        """
        await self.emit(
            "complete",
            final_response=final_response,
            timestamp=datetime.now(UTC).isoformat(),
            metadata=metadata or {},
        )

    async def emit_error(self, error: str, metadata: dict[str, Any] | None = None) -> None:
        """Emit an error event.

        Args:
            error: Error message
            metadata: Optional metadata (error type, traceback, etc.)
        """
        await self.emit(
            "error",
            error=error,
            timestamp=datetime.now(UTC).isoformat(),
            metadata=metadata or {},
        )

    async def emit_approval_request(self, tool_name: str, tool_args: dict[str, Any]) -> None:
        """Emit an approval request event (for risky tools).

        Args:
            tool_name: Name of the tool requiring approval
            tool_args: Arguments passed to the tool
        """
        await self.emit(
            "approval_request",
            tool_name=tool_name,
            tool_args=tool_args,
            timestamp=datetime.now(UTC).isoformat(),
        )

    async def emit_memory_write(
        self, memory_type: str, content: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Emit a memory write event.

        Args:
            memory_type: Type of memory being written
            content: Content being written
            metadata: Optional metadata (account_id, session_id, etc.)
        """
        await self.emit(
            "memory_write",
            memory_type=memory_type,
            content=content[:1000] if content else "",  # Truncate large content
            timestamp=datetime.now(UTC).isoformat(),
            metadata=metadata or {},
        )
