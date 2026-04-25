from enum import StrEnum

from pydantic import BaseModel


class TrustLevel(StrEnum):
    TRUSTED = "trusted"  # System policy, instructions
    INTERNAL = "internal"  # Butler services, workload identity
    USER_INPUT = "user_input"  # Direct user requests
    RETRIEVED = "retrieved"  # Memory, knowledge base
    EXTERNAL = "external"  # Web, OCR, documents, email
    UNTRUSTED = "untrusted"  # User uploads, unknown sources


class ContentSource(BaseModel):
    source_type: str
    trust_level: TrustLevel
    content_class: str
    classification_reason: str


class DefenseDecision(BaseModel):
    trust_score: float
    channel_assignment: str
    response_action: str
    suspicious_signals: list[str]
    block: bool


class PolicyInput(BaseModel):
    action: str
    content_trust_level: str
    assurance_level: str
    approval_state: str


class PolicyDecision(BaseModel):
    allow: bool
    reason: str
    obligations: list[str] = []


class ActorContext(BaseModel):
    account_id: str
    roles: list[str] = []


class ToolGateRequest(BaseModel):
    scope: str
    approval_token: str | None = None
    idempotency_key: str | None = None


class ToolGateDecision(BaseModel):
    allowed: bool
    reason: str | None = None
    requires_approval: bool = False


class RetrievalDecision(BaseModel):
    allowed: bool
    access_mode: str = "summarized"
    redaction_required: bool = True
    reason: str | None = None
