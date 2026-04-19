from enum import Enum
from typing import List, Optional
from pydantic import BaseModel

class TrustLevel(str, Enum):
    TRUSTED = "trusted"         # System policy, instructions
    INTERNAL = "internal"       # Butler services, workload identity
    USER_INPUT = "user_input"   # Direct user requests
    RETRIEVED = "retrieved"     # Memory, knowledge base
    EXTERNAL = "external"       # Web, OCR, documents, email
    UNTRUSTED = "untrusted"     # User uploads, unknown sources

class ContentSource(BaseModel):
    source_type: str
    trust_level: TrustLevel
    content_class: str
    classification_reason: str

class DefenseDecision(BaseModel):
    trust_score: float
    channel_assignment: str
    response_action: str
    suspicious_signals: List[str]
    block: bool

class PolicyInput(BaseModel):
    action: str
    content_trust_level: str
    assurance_level: str
    approval_state: str

class PolicyDecision(BaseModel):
    allow: bool
    reason: str
    obligations: List[str] = []

class ActorContext(BaseModel):
    account_id: str
    roles: List[str] = []

class ToolGateRequest(BaseModel):
    scope: str
    approval_token: Optional[str] = None
    idempotency_key: Optional[str] = None

class ToolGateDecision(BaseModel):
    allowed: bool
    reason: Optional[str] = None
    requires_approval: bool = False

class RetrievalDecision(BaseModel):
    allowed: bool
    access_mode: str = "summarized"
    redaction_required: bool = True
    reason: Optional[str] = None
