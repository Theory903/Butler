from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# --- Enums ---


class DeliveryPhase(StrEnum):
    """Normalized delivery phase across all providers"""

    ACCEPTED = "accepted"  # Provider accepted
    OUTBOUND = "outbound"  # In transit to carrier/network
    DELIVERED = "delivered"  # Handset/app confirmed
    READ = "read"  # User opened (where supported)
    FAILED = "failed"  # Permanent failure
    SUPPRESSED = "suppressed"  # Bounced/complaint/opt-out
    COMPLAINT = "complaint"  # Email complaint


class DeliveryStatus(StrEnum):
    """Butler internal status"""

    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    BOUNCED = "bounced"
    COMPLAINT = "complaint"
    SUPPRESSED = "suppressed"


class QueueClass(StrEnum):
    CRITICAL = "critical"  # Security alerts, approvals
    INTERACTIVE = "interactive"  # Chat responses
    BACKGROUND = "background"  # Scheduled notifications
    BULK = "bulk"  # Marketing/newsletter


# --- Requests ---


class SendRequest(BaseModel):
    channel: str = Field(..., description="sms|whatsapp|email|push")
    recipient: str = Field(..., description="Recipient identity (phone or email)")
    content: dict[str, Any] = Field(..., description="Normalized content")
    sender_profile_id: str = Field(..., description="ID of the verified sender profile to use")

    priority_class: QueueClass = Field(default=QueueClass.INTERACTIVE)
    idempotency_key: str | None = Field(None, description="Client-provided idempotency override")

    risk_class: str = Field(default="normal", description="normal|high")
    approval_token: str | None = Field(None, description="Required if risk_class is high")

    metadata: dict[str, Any] = Field(default_factory=dict)


# --- Responses / States ---


class DeliveryState(BaseModel):
    message_id: str
    channel: str
    provider: str

    phase: DeliveryPhase
    status: DeliveryStatus
    terminal: bool
    retryable: bool

    provider_status_raw: str | None = None
    provider_event_type: str | None = None

    provider_message_id: str | None = None
    first_provider_acceptance: datetime | None = None
    final_delivery: datetime | None = None
    retry_count: int = 0


class PolicyResultResponse(BaseModel):
    allowed: bool
    reason: str | None = None
    suppressed: bool = False


# --- Inbound ---


class AuthenticityResult(BaseModel):
    verified: bool
    method: str
    details: dict[str, Any]


class CanonicalInbound(BaseModel):
    channel: str
    provider: str
    provider_message_id: str

    external_sender: str
    recipient_identity: str

    received_at: datetime

    content: dict[str, Any]
    attachments: list[dict[str, Any]]

    authenticity: AuthenticityResult

    conversation_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
