"""LangChain/LangGraph Streaming Adapter — maps LC events to Butler events.

Translates LangChain/LangGraph streaming events into Butler's canonical event
schemas (StreamTokenEvent, StreamFinalEvent, etc.) for SSE and pubsub clients.
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
    StreamTokenEvent,
    StreamToolCallEvent,
    StreamToolResultEvent,
)

logger = structlog.get_logger(__name__)


class LangChainEventAdapter:
    """Convert LangChain/LangGraph events to Butler canonical events.

    Mapping:
    - Token chunks          → StreamTokenEvent  (``payload.content``)
    - Tool calls            → StreamToolCallEvent
    - Tool results          → StreamToolResultEvent
    - LangGraph interrupts  → StreamApprovalRequiredEvent
    - Completion            → StreamFinalEvent
    - Errors                → StreamErrorEvent
    """

    def __init__(
        self,
        account_id: str,
        session_id: str,
        trace_id: str,
        task_id: str | None = None,
    ) -> None:
        self.account_id = account_id
        self.session_id = session_id
        self.trace_id = trace_id
        self.task_id = task_id

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    def create_start_event(self) -> StreamStartEvent:
        return StreamStartEvent(
            account_id=self.account_id,
            session_id=self.session_id,
            trace_id=self.trace_id,
            task_id=self.task_id,
        )

    def create_token_event(self, token: str, index: int = 0) -> StreamTokenEvent:
        """Create a token event from a LangChain chunk.

        Args:
            token: Text token or chunk.
            index: Token index for ordering.

        Note:
            Payload key is ``"content"`` (not ``"token"``) to match the
            canonical ``StreamTokenEvent`` shape consumed by the runtime kernel
            and SSE bridge.
        """
        return StreamTokenEvent(
            account_id=self.account_id,
            session_id=self.session_id,
            trace_id=self.trace_id,
            task_id=self.task_id,
            payload={"content": token, "index": index},
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
            tool_name:    Name of the tool.
            tool_args:    Tool arguments (redacted for L1+ tools per governance).
            execution_id: Unique execution identifier.
            risk_tier:    Risk tier string (``"L0"`` – ``"L3"``).
        """
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

        Result is redacted for L1+ tools per Butler governance policy.
        """
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
        content: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        estimated_cost_usd: float = 0.0,
        duration_ms: int = 0,
    ) -> StreamFinalEvent:
        return StreamFinalEvent(
            account_id=self.account_id,
            session_id=self.session_id,
            trace_id=self.trace_id,
            task_id=self.task_id,
            payload={
                "content": content,
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


# ---------------------------------------------------------------------------
# Streaming adapter function
# ---------------------------------------------------------------------------


async def stream_langchain_to_butler(
    langchain_stream: AsyncGenerator[Any],
    adapter: LangChainEventAdapter,
) -> AsyncGenerator[Any]:
    """Convert a LangChain/LangGraph async stream to Butler canonical events.

    Mapping rules applied in order per event:
      1. ``event.content`` (str) → StreamTokenEvent
      2. ``event.tool_calls``    → StreamToolCallEvent per call
      3. ``event.event == "on_tool_start"`` → StreamToolCallEvent
      4. ``event.event == "on_tool_end"``   → StreamToolResultEvent
      5. ``"interrupt"`` in ``event.event`` → StreamApprovalRequiredEvent

    Any unhandled event type is silently skipped — the adapter never raises
    inside the loop so a single unexpected event cannot abort the stream.

    Yields:
        Butler canonical events.  Always starts with StreamStartEvent and
        ends with StreamFinalEvent (or StreamErrorEvent on exception).
    """
    yield adapter.create_start_event()

    try:
        async for event in langchain_stream:
            # 1. Plain token chunk (AIMessageChunk, etc.)
            content = getattr(event, "content", None)
            if isinstance(content, str) and content:
                yield adapter.create_token_event(content)
                continue

            # 2. Tool call embedded in a message
            tool_calls = getattr(event, "tool_calls", None)
            if tool_calls:
                for tc in tool_calls:
                    name = tc.get("name", "unknown") if isinstance(tc, dict) else getattr(tc, "name", "unknown")
                    args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                    exec_id = tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")
                    yield adapter.create_tool_call_event(
                        tool_name=name,
                        tool_args=args if isinstance(args, dict) else {},
                        execution_id=str(exec_id),
                    )
                continue

            # 3–5. LangGraph lifecycle events
            event_name = getattr(event, "event", None)
            data = getattr(event, "data", {}) or {}

            if event_name == "on_tool_start":
                inp = data.get("input", {}) if isinstance(data, dict) else {}
                yield adapter.create_tool_call_event(
                    tool_name=inp.get("name", "unknown"),
                    tool_args=inp.get("arguments", {}),
                    execution_id=str(data.get("execution_id", "")) if isinstance(data, dict) else "",
                )

            elif event_name == "on_tool_end":
                inp = data.get("input", {}) if isinstance(data, dict) else {}
                yield adapter.create_tool_result_event(
                    tool_name=inp.get("name", "unknown"),
                    result=data.get("output") if isinstance(data, dict) else None,
                    execution_id=str(data.get("execution_id", "")) if isinstance(data, dict) else "",
                    duration_ms=int(data.get("duration_ms", 0)) if isinstance(data, dict) else 0,
                )

            elif event_name and "interrupt" in str(event_name).lower():
                if isinstance(data, dict):
                    yield adapter.create_approval_required_event(
                        approval_id=str(data.get("approval_id", "")),
                        approval_type=str(data.get("type", "tool_execution")),
                        description=str(data.get("description", "")),
                        risk_tier=str(data.get("risk_tier", "L2")),
                        expires_at=str(data.get("expires_at", "")),
                    )

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