"""
LangChain/LangGraph Streaming Adapter - Maps LC events to Butler events.

This adapter translates LangChain/LangGraph streaming events into Butler's
canonical event schemas (StreamTokenEvent, StreamFinalEvent, etc.) for SSE
and pubsub clients.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import structlog

from domain.events.schemas import (
    StreamApprovalRequiredEvent,
    StreamErrorEvent,
    StreamFinalEvent,
    StreamStartEvent,
    StreamStatusEvent,
    StreamToolCallEvent,
    StreamToolResultEvent,
    StreamTokenEvent,
)

logger = structlog.get_logger(__name__)


class LangChainEventAdapter:
    """Adapter for converting LangChain/LangGraph events to Butler events.

    This adapter:
    - Maps LangChain token chunks to StreamTokenEvent
    - Maps LangGraph tool calls to StreamToolCallEvent
    - Maps LangGraph tool results to StreamToolResultEvent
    - Maps LangGraph interrupts to StreamApprovalRequiredEvent
    - Maps completion to StreamFinalEvent
    - Maps errors to StreamErrorEvent
    """

    def __init__(
        self,
        account_id: str,
        session_id: str,
        trace_id: str,
        task_id: str | None = None,
    ):
        """Initialize the event adapter.

        Args:
            account_id: Account UUID
            session_id: Session UUID
            trace_id: Trace UUID
            task_id: Optional task UUID
        """
        self.account_id = account_id
        self.session_id = session_id
        self.trace_id = trace_id
        self.task_id = task_id

    def create_start_event(self) -> StreamStartEvent:
        """Create a stream start event."""
        return StreamStartEvent(
            account_id=self.account_id,
            session_id=self.session_id,
            trace_id=self.trace_id,
            task_id=self.task_id,
        )

    def create_token_event(self, token: str, index: int = 0) -> StreamTokenEvent:
        """Create a token event from LangChain chunk.

        Args:
            token: Token or chunk of text
            index: Token index for ordering

        Returns:
            StreamTokenEvent instance
        """
        return StreamTokenEvent(
            account_id=self.account_id,
            session_id=self.session_id,
            trace_id=self.trace_id,
            task_id=self.task_id,
            payload={"token": token, "index": index},
        )

    def create_tool_call_event(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        execution_id: str,
        risk_tier: str = "L1",
    ) -> StreamToolCallEvent:
        """Create a tool call event.

        Args:
            tool_name: Name of the tool being called
            tool_args: Tool arguments (may be redacted based on risk tier)
            execution_id: Unique execution ID
            risk_tier: Risk tier of the tool

        Returns:
            StreamToolCallEvent instance
        """
        # Redact params for L1+ tools per Butler governance
        visible_params = tool_args if risk_tier == "L0" else None

        return StreamToolCallEvent(
            account_id=self.account_id,
            session_id=self.session_id,
            trace_id=self.trace_id,
            task_id=self.task_id,
            payload={
                "tool_name": tool_name,
                "visible_params": visible_params,
                "execution_id": execution_id,
            },
        )

    def create_tool_result_event(
        self,
        tool_name: str,
        result: Any,
        execution_id: str,
        duration_ms: int,
        risk_tier: str = "L1",
    ) -> StreamToolResultEvent:
        """Create a tool result event.

        Args:
            tool_name: Name of the tool
            result: Tool result (may be redacted based on risk tier)
            execution_id: Unique execution ID
            duration_ms: Execution duration in milliseconds
            risk_tier: Risk tier of the tool

        Returns:
            StreamToolResultEvent instance
        """
        # Redact result for L1+ tools per Butler governance
        visible_result = result if risk_tier == "L0" else None

        return StreamToolResultEvent(
            account_id=self.account_id,
            session_id=self.session_id,
            trace_id=self.trace_id,
            task_id=self.task_id,
            payload={
                "tool_name": tool_name,
                "success": True,
                "visible_result": visible_result,
                "duration_ms": duration_ms,
            },
        )

    def create_approval_required_event(
        self,
        approval_id: str,
        approval_type: str,
        description: str,
        risk_tier: str,
        expires_at: str,
    ) -> StreamApprovalRequiredEvent:
        """Create an approval required event from LangGraph interrupt.

        Args:
            approval_id: Approval request ID
            approval_type: Type of approval (tool_execution, send_message, etc)
            description: Human-readable description
            risk_tier: Risk tier requiring approval
            expires_at: ISO timestamp when approval expires

        Returns:
            StreamApprovalRequiredEvent instance
        """
        return StreamApprovalRequiredEvent(
            account_id=self.account_id,
            session_id=self.session_id,
            trace_id=self.trace_id,
            task_id=self.task_id,
            payload={
                "approval_id": approval_id,
                "approval_type": approval_type,
                "description": description,
                "expires_at": expires_at,
                "risk_tier": risk_tier,
            },
        )

    def create_status_event(
        self,
        phase: str,
        step_index: int = 0,
        total_steps: int = 0,
        message: str = "",
    ) -> StreamStatusEvent:
        """Create a status event.

        Args:
            phase: Current phase (planning, executing, paused, compensating)
            step_index: Current step index
            total_steps: Total number of steps
            message: Status message

        Returns:
            StreamStatusEvent instance
        """
        return StreamStatusEvent(
            account_id=self.account_id,
            session_id=self.session_id,
            trace_id=self.trace_id,
            task_id=self.task_id,
            payload={
                "phase": phase,
                "step_index": step_index,
                "total_steps": total_steps,
                "message": message,
            },
        )

    def create_final_event(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        estimated_cost_usd: float = 0.0,
        duration_ms: int = 0,
    ) -> StreamFinalEvent:
        """Create a final event.

        Args:
            input_tokens: Input token count
            output_tokens: Output token count
            cache_read_tokens: Cache read token count
            estimated_cost_usd: Estimated cost in USD
            duration_ms: Total duration in milliseconds

        Returns:
            StreamFinalEvent instance
        """
        return StreamFinalEvent(
            account_id=self.account_id,
            session_id=self.session_id,
            trace_id=self.trace_id,
            task_id=self.task_id,
            payload={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_tokens": cache_read_tokens,
                "estimated_cost_usd": estimated_cost_usd,
                "duration_ms": duration_ms,
            },
        )

    def create_error_event(
        self,
        error_type: str,
        title: str,
        detail: str,
        status: int = 500,
        retryable: bool = False,
    ) -> StreamErrorEvent:
        """Create an error event.

        Args:
            error_type: RFC 9457 problem type URI
            title: Error title
            detail: Error detail
            status: HTTP status code
            retryable: Whether the error is retryable

        Returns:
            StreamErrorEvent instance
        """
        return StreamErrorEvent(
            account_id=self.account_id,
            session_id=self.session_id,
            trace_id=self.trace_id,
            task_id=self.task_id,
            payload={
                "type": error_type,
                "title": title,
                "status": status,
                "detail": detail,
                "retryable": retryable,
            },
        )


async def stream_langchain_to_butler(
    langchain_stream: AsyncGenerator[Any, None],
    adapter: LangChainEventAdapter,
) -> AsyncGenerator[Any, None]:
    """Convert LangChain/LangGraph stream to Butler event stream.

    Args:
        langchain_stream: LangChain/LangGraph async generator
        adapter: LangChainEventAdapter instance

    Yields:
        Butler canonical events (StreamTokenEvent, StreamFinalEvent, etc)
    """
    # Yield start event
    yield adapter.create_start_event()

    try:
        async for event in langchain_stream:
            # Map LangChain events to Butler events
            if hasattr(event, "content") and isinstance(event.content, str):
                # Token chunk
                yield adapter.create_token_event(event.content)
            elif hasattr(event, "tool_calls"):
                # Tool call
                for tool_call in event.tool_calls:
                    yield adapter.create_tool_call_event(
                        tool_name=tool_call.get("name", "unknown"),
                        tool_args=tool_call.get("args", {}),
                        execution_id=tool_call.get("id", ""),
                    )
            elif hasattr(event, "event") and event.event == "on_tool_start":
                # Tool start (LangGraph)
                if hasattr(event, "data"):
                    data = event.data
                    yield adapter.create_tool_call_event(
                        tool_name=data.get("input", {}).get("name", "unknown"),
                        tool_args=data.get("input", {}).get("arguments", {}),
                        execution_id=data.get("execution_id", ""),
                    )
            elif hasattr(event, "event") and event.event == "on_tool_end":
                # Tool end (LangGraph)
                if hasattr(event, "data"):
                    data = event.data
                    yield adapter.create_tool_result_event(
                        tool_name=data.get("input", {}).get("name", "unknown"),
                        result=data.get("output"),
                        execution_id=data.get("execution_id", ""),
                        duration_ms=data.get("duration_ms", 0),
                    )
            elif hasattr(event, "event") and "interrupt" in str(event.event).lower():
                # Approval interrupt (LangGraph)
                if hasattr(event, "data"):
                    data = event.data
                    yield adapter.create_approval_required_event(
                        approval_id=data.get("approval_id", ""),
                        approval_type=data.get("type", "tool_execution"),
                        description=data.get("description", ""),
                        risk_tier=data.get("risk_tier", "L2"),
                        expires_at=data.get("expires_at", ""),
                    )

        # Yield final event on completion
        yield adapter.create_final_event()

    except Exception as exc:
        logger.error(
            "langchain_stream_conversion_failed",
            account_id=adapter.account_id,
            session_id=adapter.session_id,
            error=str(exc),
        )
        yield adapter.create_error_event(
            error_type="https://butler.ai/errors/streaming-failed",
            title="Streaming conversion failed",
            detail=str(exc),
            status=500,
            retryable=False,
        )
