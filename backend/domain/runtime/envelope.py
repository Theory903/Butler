"""Canonical runtime envelope for Butler production flow.

The ``ButlerRuntimeEnvelope`` is the single authoritative object that flows
through all pipeline stages.  Every downstream component receives either this
envelope or a typed contract derived from it.

Design rules:
- Frozen after creation; use ``copy_with()`` for derived envelopes.
- One ``request_id``, one ``session_id``, one ``account_id`` per envelope.
- No ambient ``dict[str, Any]`` escaping type boundaries.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Literal type aliases
# ---------------------------------------------------------------------------

ChannelType = Literal["api", "web", "mobile", "webhook", "cli"]
InputType = Literal["text", "audio", "image", "file", "mixed"]

# Default deadline: 30 seconds expressed in milliseconds.
_DEFAULT_DEADLINE_MS: Final[int] = 30_000


# ---------------------------------------------------------------------------
# Component models
# ---------------------------------------------------------------------------


class UserInput(BaseModel):
    """Normalised user input."""

    type: InputType
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}


class ClientContext(BaseModel):
    """Client-side context extracted from request metadata."""

    timezone: str | None = None
    locale: str | None = None
    device_id: str | None = None
    platform: str | None = None
    user_agent: str | None = None
    ip_address: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}


class AuthContext(BaseModel):
    """Authentication and authorisation context."""

    authenticated: bool = False
    user_id: str | None = None
    tenant_id: UUID | None = None
    account_id: UUID | None = None
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    session_id: str | None = None

    model_config = {"frozen": True}


class PolicyContext(BaseModel):
    """Policy and risk evaluation context."""

    risk_tier: str | None = None
    approval_required: bool = False
    sandbox_required: bool = False
    constraints: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


class ButlerRuntimeEnvelope(BaseModel):
    """Canonical runtime envelope for Butler production flow.

    Immutable after construction.  Use ``copy_with(**updates)`` to produce
    derived envelopes (e.g. after redaction or enrichment).

    Invariants:
    - ``request_id`` is unique per request.
    - ``session_id`` is stable across a conversation.
    - ``tenant_id`` is always present; ``account_id`` may be ``None`` for
      unauthenticated entry points.
    - ``deadline_ms`` represents the wall-clock budget in milliseconds
      allocated to the entire pipeline for this request.
    """

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: UUID
    account_id: UUID | None = None
    session_id: str
    channel: ChannelType = "api"
    input: UserInput
    client_context: ClientContext = Field(default_factory=ClientContext)
    auth_context: AuthContext = Field(default_factory=AuthContext)
    policy_context: PolicyContext = Field(default_factory=PolicyContext)
    # Wall-clock budget for the full pipeline (ms).  Callers should set this
    # explicitly; the default of 30 s is a conservative safety net.
    deadline_ms: int = _DEFAULT_DEADLINE_MS
    idempotency_key: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}

    def copy_with(self, **updates: Any) -> ButlerRuntimeEnvelope:
        """Return a new envelope with the given fields replaced.

        Uses Pydantic's ``model_copy`` to preserve validation and freezing.
        """
        return self.model_copy(update=updates)


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class RuntimeResponse(BaseModel):
    """Canonical runtime response produced by the orchestration pipeline."""

    request_id: str
    session_id: str
    response: str
    actions_taken: list[dict[str, Any]] = Field(default_factory=list)
    requires_approval: bool = False
    approval_id: str | None = None
    workflow_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"frozen": True}