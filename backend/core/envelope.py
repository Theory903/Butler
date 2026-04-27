"""Canonical Butler request envelope.

Every inbound request is normalized into this envelope by the Gateway
before dispatching to the Orchestrator. This ensures multi-device
continuity, trace propagation, policy-aware routing, and deterministic
contracts across all execution layers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from typing import Any
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


def _now_utc() -> datetime:
    return datetime.now(UTC)


class ButlerChannel(StrEnum):
    API = "api"
    WEB = "web"
    MOBILE = "mobile"
    WATCH = "watch"
    VOICE = "voice"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    SLACK = "slack"
    TELEGRAM = "telegram"
    DISCORD = "discord"


class ButlerMode(StrEnum):
    AUTO = "auto"
    CHAT = "chat"
    AGENT = "agent"
    AGENTIC = "agentic"
    SEARCH = "search"
    TOOL = "tool"
    WORKFLOW = "workflow"


class AssuranceLevel(StrEnum):
    AAL1 = "aal1"
    AAL2 = "aal2"
    AAL3 = "aal3"


class RiskTier(IntEnum):
    """Canonical request/tool risk tier used across orchestration boundaries."""

    TIER_0_BUILTIN = 0
    TIER_1_READ = 1
    TIER_2_WRITE = 2
    TIER_3_DEVICE = 3
    TIER_4_APPROVAL = 4


class EventType(StrEnum):
    """Stable event names emitted by the orchestrator graph."""

    REQUEST_RECEIVED = "request_received"
    SAFETY_CHECKED = "safety_checked"
    CONTEXT_RETRIEVED = "context_retrieved"
    PLAN_CREATED = "plan_created"
    TOOL_CALLED = "tool_called"
    APPROVAL_REQUESTED = "approval_requested"
    MEMORY_WRITTEN = "memory_written"
    RESPONSE_RENDERED = "response_rendered"
    ERROR = "error"


class AttachmentKind(StrEnum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    FILE = "file"
    URL = "url"
    JSON = "json"


class EnvelopeSource(StrEnum):
    CLIENT = "client"
    GATEWAY = "gateway"
    INTERNAL = "internal"


class ButlerAttachment(BaseModel):
    """Normalized attachment metadata passed downstream.

    The gateway should normalize raw upload/provider payloads into this model.
    Downstream services should not have to guess what kind of thing they got.
    """

    model_config = ConfigDict(extra="forbid")

    attachment_id: str | None = None
    kind: AttachmentKind
    name: str | None = None
    mime_type: str | None = None
    url: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    sha256: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("attachment_id", "name", "mime_type", "url", "sha256", mode="before")
    @classmethod
    def _normalize_optional_strings(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        cleaned = value.strip()
        return cleaned or None


class LocationHint(BaseModel):
    """Client-supplied coarse location hint.

    This is intentionally flexible, but normalized enough for downstream use.
    """

    model_config = ConfigDict(extra="forbid")

    latitude: float | None = None
    longitude: float | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    timezone: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("city", "region", "country", "timezone", mode="before")
    @classmethod
    def _normalize_optional_strings(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        cleaned = value.strip()
        return cleaned or None


class TraceContext(BaseModel):
    """W3C / internal trace propagation fields."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str | None = None
    span_id: str | None = None
    traceparent: str | None = None
    tracestate: str | None = None

    @field_validator("trace_id", "span_id", "traceparent", "tracestate", mode="before")
    @classmethod
    def _normalize_optional_strings(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        cleaned = value.strip()
        return cleaned or None


class ClientContext(BaseModel):
    """Client-controlled context hints.

    These are useful, but not trusted as authoritative policy inputs unless
    explicitly revalidated by the gateway or downstream services.
    """

    model_config = ConfigDict(extra="forbid")

    client_version: str | None = None
    locale: str | None = None
    timezone: str | None = None
    user_agent: str | None = None
    app_build: str | None = None
    platform: str | None = None
    location: LocationHint | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "client_version",
        "locale",
        "timezone",
        "user_agent",
        "app_build",
        "platform",
        mode="before",
    )
    @classmethod
    def _normalize_optional_strings(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        cleaned = value.strip()
        return cleaned or None


class GatewayContext(BaseModel):
    """Gateway-set, non-client-controlled operational fields."""

    model_config = ConfigDict(extra="forbid")

    source: EnvelopeSource = EnvelopeSource.GATEWAY
    assurance_level: AssuranceLevel = AssuranceLevel.AAL1
    idempotency_key: str | None = None
    rate_limit_remaining: int | None = None
    authenticated_user_id: str | None = None
    tenant_id: str | None = None
    ip_address: str | None = None
    request_received_at: datetime = Field(default_factory=_now_utc)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "idempotency_key", "authenticated_user_id", "tenant_id", "ip_address", mode="before"
    )
    @classmethod
    def _normalize_optional_strings(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        cleaned = value.strip()
        return cleaned or None

    @field_validator("request_received_at", mode="before")
    @classmethod
    def _normalize_datetime(cls, value: Any) -> datetime:
        if value is None:
            return _now_utc()
        if isinstance(value, datetime):
            return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        raise TypeError("request_received_at must be a datetime or ISO-8601 string")


class SessionIdentity(BaseModel):
    """Canonical multi-tenant session identity.

    Immutable tenant context set by Gateway only.
    Client cannot override tenant identity.

    `account_id` is Butler's current durable owner for existing data paths.
    `tenant_id` is the active tenant/account context for SaaS isolation (UUID).
    `tenant_slug` is display-only string for UI (e.g., "acme-corp").
    """

    model_config = ConfigDict(extra="forbid")

    account_id: str  # UUID
    tenant_id: str  # UUID
    tenant_slug: str | None = None  # display only
    session_id: str
    user_id: str | None = None  # UUID
    device_id: str | None = None
    channel: ButlerChannel = ButlerChannel.API
    assurance_level: AssuranceLevel = AssuranceLevel.AAL1
    authenticated: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("account_id", "tenant_id", "session_id", "user_id", "device_id", mode="before")
    @classmethod
    def _normalize_optional_strings(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @model_validator(mode="after")
    def _validate_identity(self) -> SessionIdentity:
        if not self.account_id:
            raise ValueError("account_id must not be empty")
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty")
        if not self.session_id:
            raise ValueError("session_id must not be empty")
        return self


class Message(BaseModel):
    """Canonical message shape returned by graph execution."""

    model_config = ConfigDict(extra="forbid")

    role: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    """Canonical tool call record surfaced by orchestration."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk_tier: RiskTier = RiskTier.TIER_1_READ
    status: str = "pending"
    result: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryWrite(BaseModel):
    """Memory write emitted by orchestration for downstream persistence/audit."""

    model_config = ConfigDict(extra="forbid")

    tier: str = "hot"
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ButlerEvent(BaseModel):
    """Graph event compatible with tracing and workflow replay."""

    model_config = ConfigDict(extra="forbid")

    type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: str
    timestamp: datetime = Field(default_factory=_now_utc)

    @field_validator("timestamp", mode="before")
    @classmethod
    def _normalize_timestamp(cls, value: Any) -> datetime:
        if value is None:
            return _now_utc()
        if isinstance(value, datetime):
            return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        raise TypeError("timestamp must be a datetime or ISO-8601 string")


class ButlerEnvelope(BaseModel):
    """Canonical request envelope between Gateway and Orchestrator.

    Rules:
    - built by Gateway after auth / normalization
    - consumed by Orchestrator and downstream services
    - downstream services should not depend on raw HTTP request shape
    """

    model_config = ConfigDict(extra="forbid")

    # Identity and routing
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    account_id: str
    session_id: str
    identity: SessionIdentity | None = None
    device_id: str | None = None
    workflow_id: str | None = None

    # Channel and intent/routing mode
    channel: ButlerChannel = ButlerChannel.API
    mode: ButlerMode = ButlerMode.AUTO
    model: str | None = None

    # Message payload
    message: str = ""
    attachments: list[ButlerAttachment] = Field(default_factory=list)

    # Timing and tracing
    created_at: datetime = Field(default_factory=_now_utc)
    trace: TraceContext = Field(default_factory=TraceContext)

    # Client and gateway context
    client: ClientContext = Field(default_factory=ClientContext)
    gateway: GatewayContext = Field(default_factory=GatewayContext)

    # Orchestrator hints
    risk_tier: RiskTier = RiskTier.TIER_0_BUILTIN
    tool_hints: list[str] = Field(default_factory=list)
    capability_hints: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    # Freeform normalized metadata
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "request_id",
        "account_id",
        "session_id",
        "device_id",
        "workflow_id",
        "model",
        "message",
        mode="before",
    )
    @classmethod
    def _normalize_strings(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        cleaned = value.strip()
        return cleaned or None

    @field_validator("tool_hints", "capability_hints", "tags", mode="before")
    @classmethod
    def _normalize_string_lists(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError("expected a list")
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            if item is None:
                continue
            cleaned = str(item).strip()
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            result.append(cleaned)
        return result

    @field_validator("created_at", mode="before")
    @classmethod
    def _normalize_created_at(cls, value: Any) -> datetime:
        if value is None:
            return _now_utc()
        if isinstance(value, datetime):
            return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        raise TypeError("created_at must be a datetime or ISO-8601 string")

    @field_validator("metadata", mode="before")
    @classmethod
    def _normalize_metadata(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise TypeError("metadata must be a dictionary")
        return dict(value)

    @model_validator(mode="after")
    def _validate_envelope(self) -> ButlerEnvelope:
        if not self.account_id:
            raise ValueError("account_id must not be empty")
        if not self.session_id:
            raise ValueError("session_id must not be empty")

        if not self.message and not self.attachments:
            raise ValueError("at least one of message or attachments must be present")

        if self.identity is None:
            self.identity = SessionIdentity(
                account_id=self.account_id,
                tenant_id=self.gateway.tenant_id or self.account_id,
                session_id=self.session_id,
                user_id=self.gateway.authenticated_user_id or self.account_id,
                device_id=self.device_id,
                channel=self.channel,
                assurance_level=self.gateway.assurance_level,
            )
        elif (
            self.identity.account_id != self.account_id
            or self.identity.session_id != self.session_id
            or self.identity.channel != self.channel
        ):
            raise ValueError("identity must match envelope account, session, and channel")

        if (
            self.gateway.request_received_at is not None
            and self.gateway.request_received_at < self.created_at
        ):
            # Gateway receive time should generally be at or after created_at.
            # If the client clock is weird, created_at is still accepted, but this
            # catches bad normalization where internal timestamps got flipped.
            raise ValueError("gateway.request_received_at cannot be earlier than created_at")

        return self


class OrchestratorAction(BaseModel):
    """Structured action emitted by the Orchestrator."""

    model_config = ConfigDict(extra="forbid")

    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"

    @field_validator("type", "status", mode="before")
    @classmethod
    def _normalize_required_strings(cls, value: Any) -> str:
        if value is None:
            raise ValueError("field is required")
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("field must not be empty")
        return cleaned


class OrchestratorResult(BaseModel):
    """Result returned by the Orchestrator back to Gateway."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    content: str
    actions: list[OrchestratorAction] = Field(default_factory=list)

    envelope: ButlerEnvelope | None = None
    messages: list[Message] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    approvals_pending: list[dict[str, Any]] = Field(default_factory=list)
    workflow_state: dict[str, Any] = Field(default_factory=dict)
    memory_writes: list[MemoryWrite] = Field(default_factory=list)
    events: list[ButlerEvent] = Field(default_factory=list)
    final: bool = True

    requires_approval: bool = False
    approval_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    execution_mode: str | None = None
    planner_source: str | None = None
    risk_level: str | None = None

    session_id: str
    request_id: str

    model_used: str | None = None
    finish_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content", mode="before")
    @classmethod
    def _normalize_content(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator(
        "workflow_id",
        "approval_id",
        "session_id",
        "request_id",
        "model_used",
        "finish_reason",
        mode="before",
    )
    @classmethod
    def _normalize_optional_strings(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("metadata", mode="before")
    @classmethod
    def _normalize_metadata(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise TypeError("metadata must be a dictionary")
        return dict(value)

    @model_validator(mode="after")
    def _validate_result(self) -> OrchestratorResult:
        if self.requires_approval and not self.approval_id:
            raise ValueError("approval_id is required when requires_approval=True")
        if not self.workflow_id:
            raise ValueError("workflow_id must not be empty")
        if not self.session_id:
            raise ValueError("session_id must not be empty")
        if not self.request_id:
            raise ValueError("request_id must not be empty")
        return self
