"""Butler Event Normalizer.

Translates raw Hermes runtime events into typed Butler canonical events.
This is the immune system boundary between Hermes and Butler.

Rules (per transplant-constitution.md §7.1):
  - Hermes 'delta'          → StreamTokenEvent
  - Hermes 'tool_use'       → TaskStepStartedEvent + ToolExecutingEvent
  - Hermes 'tool_result'    → ToolExecutedEvent or ToolFailedEvent
  - Hermes 'end_turn'       → StreamFinalEvent
  - Hermes 'thinking'       → SUPPRESSED (never forwarded)
  - Hermes 'error'          → TaskFailedEvent + StreamErrorEvent
  - Hermes session reset    → SessionEndedEvent

No Hermes event type ever reaches a Butler consumer directly.
"""

from __future__ import annotations

import structlog
from typing import Any, Iterator

from domain.events.schemas import (
    ButlerEvent,
    StreamTokenEvent,
    StreamToolCallEvent,
    StreamToolResultEvent,
    StreamApprovalRequiredEvent,
    StreamFinalEvent,
    StreamErrorEvent,
    TaskStartedEvent,
    TaskStepStartedEvent,
    TaskStepCompletedEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
    ToolExecutingEvent,
    ToolExecutedEvent,
    ToolFailedEvent,
    SessionEndedEvent,
)

logger = structlog.get_logger(__name__)

# Tools that expose their params in StreamToolCallEvent (L0 only)
_SAFE_AUTO_TOOLS = frozenset({
    "web_search",
    "memory_recall",
    "session_search",
    "list_files",
    "read_file",
    "clarify",
    "get_time",
    "get_weather",
})

# RFC 9457 problem type URIs for classified Hermes errors
_ERROR_TYPE_MAP: dict[str, str] = {
    "overloaded_error":     "https://butler.lasmoid.ai/problems/provider-overloaded",
    "rate_limit_error":     "https://butler.lasmoid.ai/problems/rate-limited",
    "context_window_error": "https://butler.lasmoid.ai/problems/context-too-large",
    "auth_error":           "https://butler.lasmoid.ai/problems/provider-auth-failed",
    "timeout":              "https://butler.lasmoid.ai/problems/tool-timeout",
    "tool_not_found":       "https://butler.lasmoid.ai/problems/tool-not-found",
    "default":              "https://butler.lasmoid.ai/problems/internal-error",
}

_RETRYABLE_ERRORS = frozenset({
    "overloaded_error",
    "rate_limit_error",
    "timeout",
})


class EventNormalizer:
    """Translates Hermes runtime events to typed Butler canonical events.

    Usage:
        normalizer = EventNormalizer(
            account_id="acct_...",
            session_id="ses_...",
            task_id="tsk_...",
            trace_id="trc_...",
        )
        for butler_event in normalizer.normalize(hermes_event_dict):
            await publish(butler_event)
    """

    def __init__(
        self,
        account_id: str,
        session_id: str,
        task_id: str,
        trace_id: str,
    ):
        self._account_id = account_id
        self._session_id = session_id
        self._task_id = task_id
        self._trace_id = trace_id
        self._token_index: int = 0
        self._input_tokens: int = 0
        self._output_tokens: int = 0
        self._cache_read_tokens: int = 0
        self._duration_ms: int = 0

    def _base_kwargs(self) -> dict:
        return {
            "account_id": self._account_id,
            "session_id": self._session_id,
            "task_id": self._task_id,
            "trace_id": self._trace_id,
        }

    def normalize(self, raw: dict[str, Any]) -> Iterator[ButlerEvent]:
        """Yield zero or more Butler events from a single Hermes event dict.

        A Hermes event dict is the raw streaming chunk or callback payload.
        Fields observed in practice:
          - type: "content_block_delta" | "content_block_start" | "message_delta"
                  | "message_stop" | "error"
          - delta.type: "text_delta" | "input_json_delta" | "thinking_delta"
          - index: content block index
          - usage: {input_tokens, output_tokens, cache_read_input_tokens}
        """
        event_type = raw.get("type", "")

        # ── Text token ──────────────────────────────────────────────────────
        if event_type == "content_block_delta":
            delta = raw.get("delta", {})
            delta_type = delta.get("type", "")

            if delta_type == "text_delta":
                text = delta.get("text", "")
                if text:
                    yield StreamTokenEvent(
                        **self._base_kwargs(),
                        payload={
                            "content": text,
                            "index": self._token_index,
                        },
                    )
                    self._token_index += 1

            elif delta_type == "thinking_delta":
                # SUPPRESSED — thinking block never forwarded to consumers
                logger.debug(
                    "hermes_thinking_suppressed",
                    trace_id=self._trace_id,
                    length=len(delta.get("thinking", "")),
                )
                return  # yield nothing

            elif delta_type == "input_json_delta":
                # Tool input fragment — part of a tool_use block
                # Accumulated upstream; suppress fragment events
                return

        # ── Tool use start (content_block_start with type=tool_use) ─────────
        elif event_type == "content_block_start":
            block = raw.get("content_block", {})
            if block.get("type") == "tool_use":
                tool_name = block.get("name", "")
                tool_id = block.get("id", "")
                visible_params = None  # redacted by default

                yield ToolExecutingEvent(
                    **self._base_kwargs(),
                    payload={
                        "tool_name": tool_name,
                        "risk_tier": "L?",  # resolved by ToolExecutor, not here
                        "execution_id": tool_id,
                    },
                )
                yield StreamToolCallEvent(
                    **self._base_kwargs(),
                    payload={
                        "tool_name": tool_name,
                        "visible_params": visible_params,
                        "execution_id": tool_id,
                    },
                )

        # ── Tool result ──────────────────────────────────────────────────────
        elif event_type == "tool_result":
            # Hermes passes a dict with tool_use_id, content, is_error
            tool_name = raw.get("tool_name", "")
            hermes_error = raw.get("is_error", False)
            duration_ms = raw.get("duration_ms", 0)
            execution_id = raw.get("tool_use_id", "")
            visible = tool_name in _SAFE_AUTO_TOOLS

            if hermes_error:
                yield ToolFailedEvent(
                    **self._base_kwargs(),
                    payload={
                        "tool_name": tool_name,
                        "error_type": raw.get("error_type", "unknown"),
                        "retryable": raw.get("error_type", "") in _RETRYABLE_ERRORS,
                    },
                )
                yield StreamToolResultEvent(
                    **self._base_kwargs(),
                    payload={
                        "tool_name": tool_name,
                        "success": False,
                        "visible_result": None,
                        "duration_ms": duration_ms,
                    },
                )
            else:
                yield ToolExecutedEvent(
                    **self._base_kwargs(),
                    payload={
                        "tool_name": tool_name,
                        "duration_ms": duration_ms,
                        "verification_passed": raw.get("verification_passed", True),
                    },
                )
                yield StreamToolResultEvent(
                    **self._base_kwargs(),
                    payload={
                        "tool_name": tool_name,
                        "success": True,
                        "visible_result": raw.get("content") if visible else None,
                        "duration_ms": duration_ms,
                    },
                )
                yield TaskStepCompletedEvent(
                    **self._base_kwargs(),
                    payload={"execution_id": execution_id},
                )

        # ── Approval required ────────────────────────────────────────────────
        elif event_type == "approval_required":
            yield StreamApprovalRequiredEvent(
                **self._base_kwargs(),
                payload={
                    "approval_id": raw.get("approval_id", ""),
                    "approval_type": raw.get("approval_type", "tool_execution"),
                    "description": raw.get("description", ""),
                    "expires_at": raw.get("expires_at", ""),
                    "risk_tier": raw.get("risk_tier", ""),
                },
            )

        # ── Usage/token accounting (message_delta with stop_reason) ──────────
        elif event_type == "message_delta":
            usage = raw.get("usage", {})
            self._output_tokens += usage.get("output_tokens", 0)

        # ── Message stop → StreamFinal ───────────────────────────────────────
        elif event_type == "message_stop":
            # Final accumulated usage from the Hermes message object
            usage = raw.get("_butler_usage", {})  # injected by HermesAgentBackend
            self._input_tokens = usage.get("input_tokens", self._input_tokens)
            self._output_tokens = usage.get("output_tokens", self._output_tokens)
            self._cache_read_tokens = usage.get("cache_read_input_tokens", 0)
            self._duration_ms = raw.get("_butler_duration_ms", 0)

            cost = _estimate_cost(
                self._input_tokens,
                self._output_tokens,
                self._cache_read_tokens,
            )
            yield StreamFinalEvent(
                **self._base_kwargs(),
                payload={
                    "input_tokens": self._input_tokens,
                    "output_tokens": self._output_tokens,
                    "cache_read_tokens": self._cache_read_tokens,
                    "estimated_cost_usd": cost,
                    "duration_ms": self._duration_ms,
                },
            )
            yield TaskCompletedEvent(
                **self._base_kwargs(),
                payload={
                    "duration_ms": self._duration_ms,
                },
            )

        # ── Hermes error ──────────────────────────────────────────────────────
        elif event_type == "error":
            error_type = raw.get("error", {}).get("type", "default")
            error_msg = raw.get("error", {}).get("message", "Unknown error")
            retryable = error_type in _RETRYABLE_ERRORS

            yield TaskFailedEvent(
                **self._base_kwargs(),
                payload={
                    "error_type": error_type,
                    "retryable": retryable,
                    "compensation_triggered": False,
                },
            )
            yield StreamErrorEvent(
                **self._base_kwargs(),
                payload={
                    "type": _ERROR_TYPE_MAP.get(error_type, _ERROR_TYPE_MAP["default"]),
                    "title": error_type.replace("_", " ").title(),
                    "status": 503 if error_type in ("overloaded_error", "rate_limit_error") else 500,
                    "detail": error_msg,
                    "retryable": retryable,
                },
            )

        # ── Session reset ──────────────────────────────────────────────────
        elif event_type == "session_reset":
            yield SessionEndedEvent(
                **self._base_kwargs(),
                payload={
                    "reason": raw.get("reason", "reset"),
                    "turns": raw.get("turns", 0),
                    "duration_s": raw.get("duration_s", 0),
                },
            )

        else:
            # Unknown Hermes event type — log and suppress
            logger.debug(
                "hermes_event_suppressed",
                hermes_type=event_type,
                trace_id=self._trace_id,
            )


def _estimate_cost(
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    model: str = "claude-sonnet",
) -> float:
    """Rough cost estimate in USD. Exact pricing from ButlerUsageTracker (Phase 5)."""
    # Sonnet-class pricing as default
    input_price_per_mtok = 3.00
    output_price_per_mtok = 15.00
    cache_read_price_per_mtok = 0.30

    return round(
        (input_tokens / 1_000_000 * input_price_per_mtok)
        + (output_tokens / 1_000_000 * output_price_per_mtok)
        + (cache_read_tokens / 1_000_000 * cache_read_price_per_mtok),
        8,
    )
