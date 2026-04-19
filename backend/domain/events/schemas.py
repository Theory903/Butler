"""Butler canonical event schemas.

These are the ONLY event types that Butler services, API consumers, and Redis
Streams are permitted to receive. Hermes runtime events are never forwarded
raw — they are normalized by EventNormalizer into these types first.

Delivery classes:
  A — Guaranteed (exactly-once): task state, approvals → Redis Streams
  B — At-least-once: analytics, metrics → Redis Streams
  C — Fire-and-forget: presence, typing → Redis Pub/Sub

Versioning: {domain}.{entity}.{action}.v{version}
  Example: task.completed.v1

Governed by:
  docs/00-governance/event-contract.md §2
  docs/00-governance/transplant-constitution.md §7
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Any


# ── Delivery Class ────────────────────────────────────────────────────────────

class EventDeliveryClass(str, Enum):
    """Delivery semantics per event category."""
    A = "A"  # Guaranteed / exactly-once — Redis Streams + consumer group
    B = "B"  # At-least-once — Redis Streams
    C = "C"  # Fire-and-forget — Redis Pub/Sub


# ── Base Event ────────────────────────────────────────────────────────────────

@dataclass
class ButlerEvent:
    """Base for all Butler canonical events.

    Every event carries identity (account + session), traceability (trace_id),
    and delivery semantics. Downstream consumers should never receive a raw
    dict — always a typed ButlerEvent subclass.
    """
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    event_type: str = field(default="butler.event.v1")
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    account_id: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    trace_id: str = field(default_factory=lambda: f"trc_{uuid.uuid4().hex[:12]}")
    delivery_class: EventDeliveryClass = EventDeliveryClass.B
    durable: bool = False
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "account_id": self.account_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "delivery_class": self.delivery_class.value,
            "durable": self.durable,
            "payload": self.payload,
        }

    def to_sse(self) -> str:
        """SSE-formatted event string for streaming endpoints."""
        import json
        return f"data: {json.dumps(self.to_dict())}\n\n"


# ── Stream Events (Realtime API surface) ──────────────────────────────────────
# These are the ONLY events that reach API consumers via SSE/WebSocket.
# Hermes internal events (delta, tool_use, end_turn, thinking) never appear here.

@dataclass
class StreamStartEvent(ButlerEvent):
    """Stream opened. First event on any streaming response."""
    event_type: str = "realtime.start.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.C


@dataclass
class StreamTokenEvent(ButlerEvent):
    """Single LLM output token or token chunk.

    Hermes 'delta' events → normalized to this type.
    'thinking' blocks from Hermes are SUPPRESSED and never become this type.
    """
    event_type: str = "realtime.token.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.C

    def __post_init__(self):
        self.payload.setdefault("token", "")
        self.payload.setdefault("index", 0)


@dataclass
class StreamToolCallEvent(ButlerEvent):
    """Orchestrator is executing a tool.

    Hermes 'tool_use' content blocks → normalized to this type.
    Shows tool name + params only if tool risk tier is L0 (safe_auto).
    L1+ tools show name only; params are omitted for privacy/security.
    """
    event_type: str = "realtime.tool_call.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.C

    def __post_init__(self):
        self.payload.setdefault("tool_name", "")
        self.payload.setdefault("visible_params", None)  # None = redacted
        self.payload.setdefault("execution_id", "")


@dataclass
class StreamToolResultEvent(ButlerEvent):
    """Tool completed.

    Hermes 'tool_result' content blocks → normalized to this type.
    Full result payload only for L0 tools. L1+ show status only.
    """
    event_type: str = "realtime.tool_result.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.C

    def __post_init__(self):
        self.payload.setdefault("tool_name", "")
        self.payload.setdefault("success", True)
        self.payload.setdefault("visible_result", None)
        self.payload.setdefault("duration_ms", 0)


@dataclass
class StreamApprovalRequiredEvent(ButlerEvent):
    """Execution paused — human decision required.

    Delivery class A: this event must be durable. It initiates an
    ApprovalRequest in PostgreSQL and must survive restarts.
    """
    event_type: str = "approval.requested.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.A
    durable: bool = True

    def __post_init__(self):
        self.payload.setdefault("approval_id", "")
        self.payload.setdefault("approval_type", "")  # tool_execution, send_message, etc
        self.payload.setdefault("description", "")
        self.payload.setdefault("expires_at", "")
        self.payload.setdefault("risk_tier", "")


@dataclass
class StreamStatusEvent(ButlerEvent):
    """Workflow phase change or progress update."""
    event_type: str = "realtime.status.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.B

    def __post_init__(self):
        self.payload.setdefault("phase", "")       # planning, executing, paused, compensating
        self.payload.setdefault("step_index", 0)
        self.payload.setdefault("total_steps", 0)
        self.payload.setdefault("message", "")


@dataclass
class StreamFinalEvent(ButlerEvent):
    """Complete response. Final event on any streaming response.

    Hermes 'end_turn' → normalized to this type.
    Includes token usage summary for billing.
    """
    event_type: str = "realtime.final.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.B

    def __post_init__(self):
        self.payload.setdefault("input_tokens", 0)
        self.payload.setdefault("output_tokens", 0)
        self.payload.setdefault("cache_read_tokens", 0)
        self.payload.setdefault("estimated_cost_usd", 0.0)
        self.payload.setdefault("duration_ms", 0)


@dataclass
class StreamErrorEvent(ButlerEvent):
    """Classified error. RFC 9457 Problem Details format in payload.

    Hermes internal errors → classified and normalized before forwarding.
    """
    event_type: str = "realtime.error.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.B

    def __post_init__(self):
        self.payload.setdefault("type", "")           # RFC 9457 problem type URI
        self.payload.setdefault("title", "")
        self.payload.setdefault("status", 500)
        self.payload.setdefault("detail", "")
        self.payload.setdefault("retryable", False)


# ── Domain Events (internal bus / Redis Streams) ──────────────────────────────

@dataclass
class TaskStartedEvent(ButlerEvent):
    event_type: str = "task.started.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.A
    durable: bool = True

    def __post_init__(self):
        self.payload.setdefault("intent", "")
        self.payload.setdefault("safety_class", "")
        self.payload.setdefault("mode", "")
        self.payload.setdefault("execution_strategy", "")  # hermes_agent|deterministic|workflow_dag


@dataclass
class TaskStepStartedEvent(ButlerEvent):
    event_type: str = "task.step.started.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.A
    durable: bool = True

    def __post_init__(self):
        self.payload.setdefault("step_id", "")
        self.payload.setdefault("step_type", "")
        self.payload.setdefault("tool_name", None)


@dataclass
class TaskStepCompletedEvent(ButlerEvent):
    event_type: str = "task.step.completed.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.A
    durable: bool = True


@dataclass
class TaskCompletedEvent(ButlerEvent):
    event_type: str = "task.completed.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.A
    durable: bool = True

    def __post_init__(self):
        self.payload.setdefault("steps_completed", 0)
        self.payload.setdefault("steps_total", 0)
        self.payload.setdefault("duration_ms", 0)


@dataclass
class TaskFailedEvent(ButlerEvent):
    event_type: str = "task.failed.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.A
    durable: bool = True

    def __post_init__(self):
        self.payload.setdefault("error_type", "")
        self.payload.setdefault("retryable", False)
        self.payload.setdefault("compensation_triggered", False)


@dataclass
class ToolExecutingEvent(ButlerEvent):
    event_type: str = "tool.executing.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.B

    def __post_init__(self):
        self.payload.setdefault("tool_name", "")
        self.payload.setdefault("risk_tier", "")
        self.payload.setdefault("execution_id", "")


@dataclass
class ToolExecutedEvent(ButlerEvent):
    event_type: str = "tool.executed.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.B

    def __post_init__(self):
        self.payload.setdefault("tool_name", "")
        self.payload.setdefault("duration_ms", 0)
        self.payload.setdefault("verification_passed", True)


@dataclass
class ToolFailedEvent(ButlerEvent):
    event_type: str = "tool.failed.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.B

    def __post_init__(self):
        self.payload.setdefault("tool_name", "")
        self.payload.setdefault("error_type", "")
        self.payload.setdefault("retryable", False)


@dataclass
class MemoryStoredEvent(ButlerEvent):
    event_type: str = "memory.stored.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.B

    def __post_init__(self):
        self.payload.setdefault("memory_id", "")
        self.payload.setdefault("memory_type", "")
        self.payload.setdefault("tiers", [])           # which storage tiers received the write
        self.payload.setdefault("importance", 0.5)


@dataclass
class MemoryRetrievedEvent(ButlerEvent):
    event_type: str = "memory.retrieved.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.B

    def __post_init__(self):
        self.payload.setdefault("query_type", "")
        self.payload.setdefault("result_count", 0)
        self.payload.setdefault("source_tiers", [])    # hot|warm|cold|graph


@dataclass
class ApprovalRequestedEvent(ButlerEvent):
    event_type: str = "approval.requested.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.A
    durable: bool = True


@dataclass
class ApprovalGrantedEvent(ButlerEvent):
    event_type: str = "approval.granted.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.A
    durable: bool = True


@dataclass
class ApprovalDeniedEvent(ButlerEvent):
    event_type: str = "approval.denied.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.A
    durable: bool = True


@dataclass
class ApprovalExpiredEvent(ButlerEvent):
    event_type: str = "approval.expired.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.A
    durable: bool = True


@dataclass
class SessionStartedEvent(ButlerEvent):
    event_type: str = "user.session.start.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.B

    def __post_init__(self):
        self.payload.setdefault("channel", "")
        self.payload.setdefault("device_id", "")
        self.payload.setdefault("assurance_level", "AAL1")


@dataclass
class SessionEndedEvent(ButlerEvent):
    event_type: str = "user.session.end.v1"
    delivery_class: EventDeliveryClass = EventDeliveryClass.B

    def __post_init__(self):
        self.payload.setdefault("reason", "normal")   # normal|timeout|reset|error
        self.payload.setdefault("turns", 0)
        self.payload.setdefault("duration_s", 0)
