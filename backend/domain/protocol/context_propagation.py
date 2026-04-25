"""Protocol RuntimeContext propagation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ProtocolMessage:
    """Protocol message with RuntimeContext propagation.

    Rule: All protocol messages must carry RuntimeContext.
    """

    message_type: str
    payload: dict[str, Any]
    runtime_context: dict[str, str | None]

    @classmethod
    def create(
        cls,
        message_type: str,
        payload: dict[str, Any],
        runtime_context: dict[str, str | None],
    ) -> ProtocolMessage:
        """Factory method to create a ProtocolMessage."""
        return cls(
            message_type=message_type,
            payload=payload,
            runtime_context=runtime_context,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "message_type": self.message_type,
            "payload": self.payload,
            "runtime_context": self.runtime_context,
        }


@dataclass(frozen=True, slots=True)
class ContextPropagationHeader:
    """Context propagation header for protocol messages."""

    tenant_id: str
    account_id: str
    session_id: str | None
    request_id: str
    trace_id: str
    workflow_id: str | None
    task_id: str | None
    agent_id: str | None

    @classmethod
    def from_runtime_context(cls, ctx: dict[str, str | None]) -> ContextPropagationHeader:
        """Create from RuntimeContext dictionary."""
        return cls(
            tenant_id=ctx.get("tenant_id") or "",
            account_id=ctx.get("account_id") or "",
            session_id=ctx.get("session_id"),
            request_id=ctx.get("request_id") or "",
            trace_id=ctx.get("trace_id") or "",
            workflow_id=ctx.get("workflow_id"),
            task_id=ctx.get("task_id"),
            agent_id=ctx.get("agent_id"),
        )

    def to_dict(self) -> dict[str, str | None]:
        """Convert to dictionary."""
        return {
            "tenant_id": self.tenant_id,
            "account_id": self.account_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "workflow_id": self.workflow_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
        }
