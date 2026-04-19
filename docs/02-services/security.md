# Security Service - Technical Specification

> **For:** Engineering  
> **Status:** Active (v3.1) — PII Redaction and Content Safety fully implemented
> **Version:** 3.1  
> **Reference:** Butler trust and enforcement platform — policy, risk, data protection, and abuse detection  
> **Last Updated:** 2026-04-19

---

## 0. Implementation Status

| Phase | Component | Status | Description |
|-------|-----------|--------|-------------|
| 1 | **Trust Classification** | ✅ IMPLEMENTED | Channel separation and trust levels |
| 2 | **Policy Engine** | ✅ IMPLEMENTED | OPA-based authorization |
| 3 | **Tool Gating** | ✅ IMPLEMENTED | Scoped capability validation |
| 4 | **Secrets Mediation** | ✅ IMPLEMENTED | Brokered access to credentials |
| 5 | **PII Redaction** | ✅ IMPLEMENTED | Regex-based masking with reversible restore map (v3.1) |
| 6 | **Content Safety** | ✅ IMPLEMENTED | Heuristic blocklist + OpenAI Moderation API (v3.1) |

---

## 0.1 v3.1 Implementation Notes

> **Completed in v3.1 (2026-04-19)**

### RedactionService (`services/security/redaction.py`)
Production-grade PII masking integrated into the Orchestrator pipeline:
- **Patterns covered**: Email, US/INT phone, credit cards (Luhn-prefixed formats), API keys (`sk-*`, `Bearer *`, `AKIA*`), IPv4 addresses
- **Reversible**: `redact()` returns `(masked_text, redaction_map)`; `restore()` recovers originals — exact values are reinstated in the long-term memory write-back after inference
- **Disabled mode**: `RedactionService(enabled=False)` for unit tests / debugging without side effects
- **Sovereign rule**: Redaction happens BEFORE any LLM call. Restoration happens AFTER, before memory write.

### ContentGuard (`services/security/safety.py`)
Two-pass toxicity and harm gate:
1. **Heuristic blocklist** (sub-ms, no I/O): Pattern-matched keywords for violence, CSAM, bioweapons, self-harm
2. **OpenAI Moderation API** (optional, gated by `OPENAI_API_KEY`): `harassment`, `hate`, `violence`, `sexual`, `self-harm` categories
3. **Fail-safe**: If the API is unreachable, the response is `{"safe": true, "reason": "api_unavailable"}` in dev; stricter in prod

### Orchestrator Integration
- Every request: `input_safety_check → redact → classify → blend → infer → output_safety_check → restore → persist`
- Both input AND output are screened

### Key Files
| File | Role |
|------|------|
| `services/security/redaction.py` | PII masking service **[NEW v3.1]** |
| `services/security/safety.py` | Content safety guard **[NEW v3.1]** |
| `services/security/policy.py` | OPA-compatible `PolicyDecisionPoint`, `ToolCapabilityGate`, `MemoryIsolation` |
| `services/security/trust.py` | Channel trust classification (api/web/mobile/iot/cli) |
| `services/security/defense.py` | Prompt injection and injection detection heuristics |
| `services/security/crypto.py` | Secrets brokering — credential delegation helpers |
| `services/orchestrator/service.py` | Guardrail integration point |

> **Note on OPA**: `PolicyDecisionPoint` is Python-native (not an OPA server call). It enforces the same logical rules and can be swapped with the OPA HTTP adapter in Phase 3 without interface changes.

---

## 1. Service Overview

### 1.1 Purpose
The Security service is Butler's **model-safety and agent-control layer**. It governs:
- Untrusted content handling
- Prompt and tool injection resistance
- Model-to-tool boundaries
- Retrieval and memory isolation
- Output validation
- Agent risk scoring
- Runtime abuse prevention
- **PII Redaction** [UNIMPLEMENTED]
- **Content Safety / Harmful Content Detection** [UNIMPLEMENTED]

This is NOT "filter some weird text and hope." It's a policy-driven platform with:
- Trust classification on ingress
- Channel separation (instructions vs data)
- Structured model outputs (typed proposals, not raw authority)
- Policy-based tool decisions
- Memory class isolation
- Immutable audit

### 1.2 Architecture Layers

| Layer | Responsibilities |
|-------|-----------------|
| **Trust Classification** | Classify every input by trust level, separate channels |
| **Policy Decision Point** | OPA-based allow/deny, approval gating |
| **Tool & Capability Gates** | Scoped capabilities, credential modes, approval classes |
| **Memory Isolation** | Purpose binding, memory classes, redaction |
| **Threat & Abuse** | Detection classes, response actions |
| **Secrets & Keys** | Brokered access, envelope encryption, rotation |
| **Audit & Forensics** | Immutable audit, security metrics |

### 1.3 Clear Separation: Auth vs Security

| Aspect | Auth Service | Security Service |
|--------|-------------|----------------|
| **What it owns** | Who you are | What you can do |
| **Permissions** | Role claims | Policy evaluation |
| **Sessions** | Creates, rotates | Risk signals, detects anomalies |
| **Credentials** | Credential lifecycle | Secret access mediation |
| **Data** | User identity | Data protection |

---

## 2. Trust Classification & Channel Separation

### 2.1 Trust Levels

```python
from enum import Enum

class TrustLevel(str, Enum):
    TRUSTED = "trusted"           # System policy, instructions
    INTERNAL = "internal"         # Butler services, workload identity
    USER_INPUT = "user_input"      # Direct user requests
    RETRIEVED = "retrieved"      # Memory, knowledge base
    EXTERNAL = "external"        # Web, OCR, documents, email
    UNTRUSTED = "untrusted"      # User uploads, unknown sources
```

### 2.2 Input Source Classification

```python
@dataclass
class ContentSource:
    source_type: str          # web, ocr, email, memory, upload, user_input
    trust_level: TrustLevel
    content_class: str        # text, image, document, audio
    classification_reason: str
    provenance: dict          # URL, document ID, etc.
    
# Classification rules
SOURCE_TRUST_MAP = {
    "system_policy": TrustLevel.TRUSTED,
    "workload_internal": TrustLevel.INTERNAL,
    "user_direct_input": TrustLevel.USER_INPUT,
    "memory_episodic": TrustLevel.RETRIEVED,
    "memory_entity": TrustLevel.RETRIEVED,
    "web_content": TrustLevel.EXTERNAL,
    "ocr_output": TrustLevel.EXTERNAL,
    "document_upload": TrustLevel.EXTERNAL,
    "email_body": TrustLevel.EXTERNAL,
    "screenshot_vision": TrustLevel.EXTERNAL,
    "camera_scene_text": TrustLevel.EXTERNAL,
}
```

### 2.3 Channel Separation

**CRITICAL RULE:** Never merge untrusted content into instruction authority channel.

```python
class ChannelSeparator:
    """
    Models emit typed proposals. Policy layer decides. Tool layer executes.
    """
    
    CHANNELS = {
        "instructions": {
            "trust": TrustLevel.TRUSTED,
            "sources": ["system_policy", "builtin_instructions"]
        },
        "data_context": {
            "trust": TrustLevel.EXTERNAL,
            "sources": ["web_content", "ocr_output", "document_upload"]
        },
        "memory_context": {
            "trust": TrustLevel.RETRIEVED,
            "sources": ["memory_episodic", "memory_entity", "memory_facts"]
        },
        "tool_specs": {
            "trust": TrustLevel.INTERNAL,
            "sources": ["tool_registry"]
        },
        "policy_constraints": {
            "trust": TrustLevel.TRUSTED,
            "sources": ["security_policy"]
        }
    }
    
    def route_to_channel(self, source: ContentSource) -> str:
        """Route content to appropriate channel"""
        for channel, config in self.CHANNELS.items():
            if source.source_type in config["sources"]:
                return channel
        return "data_context"  # Default to lowest trust
```

---

## 3. Prompt & Content Injection Defense

### 3.1 Detection Signals (NOT regex as religion)

```python
class InjectionDetector:
    """
    Pattern detection is ONE weak signal. Not the whole religion.
    """
    
    DETECTION_SIGNALS = {
        # Instruction override attempts
        "ignore_instructions": ["ignore previous", "disregard", "forget instructions"],
        "role_confusion": ["you are now", "pretend to be", "roleplay as"],
        
        # External content trying to control model
        "context_injection": ["in the text above", "as mentioned before", "remember that"],
        
        # Attempts to access internal channels
        "channel_escalation": ["system prompt", "hidden instructions"],
        
        # Tool/command injection
        "tool_injection": ["execute", "run command", "shell", "bash"],
        
        # Encoding attempts
        "obfuscation": ["base64", "hex", "url encoding", "unicode"],
    }
    
    # Response levels
    RESPONSE_ACTIONS = {
        "tag_suspicious": "Content marked untrusted",
        "lower_trust": "Trust score reduced",
        "exclude_high_authority": "Blocked from instruction channel",
        "require_approval": "Human approval required",
        "quarantine": "Security event logged, content isolated",
        "block": "High-confidence attack blocked"
    }
```

### 3.2 Defense Layers

```python
@dataclass
class DefenseDecision:
    trust_score: float           # 0.0 - 1.0
    channel_assignment: str       # Where content can go
    response_action: str         # What to do
    suspicious_signals: list[str]
    block: bool = False

class ContentDefense:
    async def evaluate(self, content: str, source: ContentSource) -> DefenseDecision:
        # 1. Check trust level from source
        trust = self.get_base_trust(source)
        
        # 2. Run pattern detection (weak signal)
        signals = self.detect_injection_patterns(content)
        
        # 3. Adjust trust based on signals
        if signals:
            trust *= 0.5  # Reduce trust if patterns found
        
        # 4. Decide channel assignment
        if trust < 0.3:
            channel = "quarantine"
            block = True
        elif trust < 0.6:
            channel = "data_context"  # Not allowed in planning
        else:
            channel = self.route_to_channel(source)
        
        return DefenseDecision(
            trust_score=trust,
            channel_assignment=channel,
            response_action=self.decide_response(trust, signals),
            suspicious_signals=signals,
            block=block
        )
```

---

## 4. Tool & Capability Gating

### 4.1 Scoped Capability Model

```python
class CapabilityScope(str, Enum):
    # Format: domain:resource:action
    SEARCH_WEB_READ = "search:web:read"
    MEMORY_EPISODIC_APPEND = "memory:episodic:append"
    COMMUNICATION_SMS_SEND = "communication:sms:send"
    DEVICE_CAMERA_VIEW = "device:camera:view"
    DEVICE_LOCK_CONTROL = "device:lock:control"
    IDENTITY_SESSION_REVOKE = "identity:session:revoke"
    CREDENTIAL_USE = "credential:delegation:use"

class CredentialMode(str, Enum):
    SERVICE_CREDENTIAL = "service"     # Backend service key
    USER_DELEGATED = "user_delegated" # User-granted OAuth scope
    SESSION_BOUND = "session"        # Short-lived session token
    APPROVAL_BOUND = "approval"       # Requires human approval

class ApprovalClass(str, Enum):
    NONE = "none"           # No approval needed
    IMPLICIT = "implicit"   # Auto-approved by policy
    EXPLICIT = "explicit"  # Human must approve
    STEP_UP = "step_up"     # Requires authentication boost
    FORBIDDEN = "forbidden" # Never allowed

@dataclass
class ToolCapability:
    scope: CapabilityScope
    credential_mode: CredentialMode
    approval_class: ApprovalClass
    idempotency_required: bool
    side_effect_class: str  # read, write, external, destructive
    resource_ownership_check: bool
```

### 4.2 Tool Request Validation

```python
@dataclass
class ToolRequest:
    tool_name: str
    scope: CapabilityScope
    normalized_params: dict
    risk_score: float
    justification: str
    approval_token: str | None
    idempotency_key: str | None

class ToolGate:
    async def validate(
        self, 
        request: ToolRequest,
        actor_context: ActorContext
    ) -> ToolGateDecision:
        
        # 1. Check capability scope
        capability = await self.get_capability(request.scope)
        if not capability:
            return ToolGateDecision(allowed=False, reason="Unknown scope")
        
        # 2. Check credential mode
        if not self.check_credential_mode(actor_context, capability.credential_mode):
            return ToolGateDecision(allowed=False, reason="Invalid credential mode")
        
        # 3. Check approval requirement
        if capability.approval_class == ApprovalClass.EXPLICIT:
            if not request.approval_token:
                return ToolGateDecision(
                    allowed=False, 
                    reason="Requires approval",
                    requires_approval=True
                )
            # Validate token
            approved = await self.validate_approval_token(
                request.approval_token, 
                request.tool_name
            )
            if not approved:
                return ToolGateDecision(allowed=False, reason="Approval denied")
        
        # 4. Check resource ownership
        if capability.resource_ownership_check:
            if not await self.verify_ownership(actor_context, request.normalized_params):
                return ToolGateDecision(allowed=False, reason="Not resource owner")
        
        # 5. Check idempotency for side effects
        if capability.side_effect_class != "read" and capability.idempotency_required:
            if not request.idempotency_key:
                return ToolGateDecision(allowed=False, reason="Idempotency key required")
        
        return ToolGateDecision(allowed=True)
```

---

## 5. Retrieval & Memory Safety

### 5.1 Memory Classes

```python
class MemoryClass(str, Enum):
    PUBLIC_PROFILE = "public_profile"      # Publicly visible
    PREFERENCES = "preferences"           # User settings
    ROUTINES = "routines"                 # User patterns
    COMMUNICATION = "communication"         # Messages, contacts
    AUTH_SECURITY = "auth_security"       # Tokens, secrets
    FINANCIAL = "financial"               # Payment info
    HEALTH = "health"                     # Health data
    PRIVATE_NOTES = "private_notes"       # User's private content
    RESTRICTED = "restricted"            # Highly sensitive

@dataclass
class MemoryAccessPolicy:
    memory_class: MemoryClass
    allowed_task_families: list[str]
    min_assurance: str                    # aal1, aal2, aal3
    summarization_allowed: bool
    raw_access_allowed: bool
    output_redaction_required: bool
```

### 5.2 Purpose Binding

```python
class MemoryPurposeBinding:
    """Retrieval must be purpose-bound"""
    
    async def check_retrieval(
        self,
        requester_id: str,
        memory_class: MemoryClass,
        task_family: str
    ) -> RetrievalDecision:
        
        policy = self.get_policy(memory_class)
        
        # Check task family allowed
        if task_family not in policy.allowed_task_families:
            return RetrievalDecision(
                allowed=False,
                reason=f"Task {task_family} not allowed for {memory_class}"
            )
        
        # Check assurance level
        if requester_context.assurance < policy.min_assurance:
            return RetrievalDecision(
                allowed=False,
                reason="Assurance level too low"
            )
        
        # Determine access mode
        if policy.summarization_allowed and not policy.raw_access_allowed:
            access_mode = "summarized"
        elif policy.raw_access_allowed:
            access_mode = "raw"
        else:
            return RetrievalDecision(allowed=False, reason="Access denied")
        
        return RetrievalDecision(
            allowed=True,
            access_mode=access_mode,
            redaction_required=policy.output_redaction_required
        )
```

---

## 6. Policy Decision Point (OPA)

### 6.1 Policy Input Model

```python
class PolicyInput(BaseModel):
    # Actor
    actor_id: str
    actor_type: str  # user, agent, service, tool
    
    # Account context
    account_id: str
    session_id: str
    device_id: str | None
    assurance_level: str  # aal1, aal2, aal3
    
    # Action context
    action: str  # tools:send_message, memory:write, etc.
    resource_type: str
    resource_id: str | None
    resource_owner_id: str | None
    
    # Environment
    channel: str  # mobile, web, watch, voice, internal
    ip_address: str | None
    geolocation: str | None
    
    # Risk context
    risk_score: float
    approval_state: str | None  # approved, pending, denied
    
    # Trust context
    content_trust_level: str  # From content defense
    memory_access_mode: str  # raw, summarized, denied
    
    # Agent context
    agent_workflow_id: str | None
    agent_parent_id: str | None
```

### 6.2 Policy Decision

```python
class PolicyDecision(BaseModel):
    allow: bool
    reason: str
    obligations: list[str] = []  # require_approval, require_step_up, redact_output
    ttl_seconds: int | None = None
    risk_adjustment: float | None = None
```

### 6.3 OPA Policy Example

```python
OPA_POLICY = """
package butler.authz

default allow = false

# Allow safe reads
allow {
    input.action == "memory:read"
    input.assurance_level == "aal1"
    input.content_trust_level != "untrusted"
}

# External communication requires approval
allow {
    startswith(input.action, "communication:")
    input.approval_state == "approved"
}

# Financial actions require step-up
allow {
    startswith(input.action, "financial:")
    input.assurance_level == "aal2"
}

# Physical control requires explicit approval
allow {
    startswith(input.action, "device:")
    input.action != "device:view"
    input.approval_state == "approved"
}

# Deny if untrusted content in planning
deny {
    input.content_trust_level == "untrusted"
    input.action == "plan:create"
}
"""
```

---

## 7. Multiparty/Agent Security

### 7.1 Inter-Agent Message Signing

```python
class InterAgentSecurity:
    """Signed envelopes between Butler services/agents"""
    
    async def sign_envelope(
        self, 
        payload: dict, 
        sender_id: str
    ) -> SignedEnvelope:
        message = json.dumps(payload, sort_keys=True)
        signature = self.ed25519_sign(message, self.current_workload_key)
        
        return SignedEnvelope(
            payload=payload,
            sender_id=sender_id,
            sender_workload=self.current_workload_id,
            signature=signature,
            timestamp=time.time(),
            nonce=secrets.token_hex(16)
        )
    
    async def verify_envelope(self, envelope: SignedEnvelope) -> bool:
        # Verify Ed25519 signature
        message = json.dumps(envelope.payload, sort_keys=True)
        return self.ed25519_verify(message, envelope.signature, envelope.sender_workload)
```

### 7.2 MCP Security

```python
class MCPSecurity:
    """MCP server security controls"""
    
    # Per-server scoped credentials
    SERVER_CREDENTIALS = {
        "memory-server": {
            "scopes": ["memory:read", "memory:write"],
            "token_ttl": 300,
            "bound_services": ["orchestrator", "memory"]
        },
        "tools-server": {
            "scopes": ["tools:execute"],
            "token_ttl": 600,
            "bound_services": ["orchestrator"]
        }
    }
    
    async def validate_mcp_request(
        self,
        server: str,
        requested_scope: str,
        caller_workload: str
    ) -> bool:
        config = self.SERVER_CREDENTIALS.get(server)
        if not config:
            return False
        
        if caller_workload not in config["bound_services"]:
            return False
        
        return requested_scope in config["scopes"]
```

---

## 8. Cryptography Standards

### 8.1 Approved Algorithms

| Use Case | Preferred | Compatibility |
|----------|-----------|----------------|
| Symmetric encryption | AES-256-GCM | - |
| Key derivation (secrets) | HKDF-SHA-256 | - |
| Password hashing | Argon2id | - |
| Key exchange | X25519 | P-256 ECDH |
| Signatures | Ed25519 | ECDSA P-256 |
| Key wrapping | AES-KW / AES-KWP | RSA-OAEP 3072 |
| MAC | HMAC-SHA-256 | - |

### 8.2 AES-GCM Implementation

```python
class AESCipher:
    """AES-256-GCM with versioning and AAD"""
    
    VERSION = b"\x01"
    
    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("AES-256 key must be 32 bytes")
        self.aesgcm = AESGCM(key)
    
    def encrypt(self, plaintext: bytes, aad: bytes = b"") -> bytes:
        nonce = os.urandom(12)  # 96-bit nonce
        ciphertext = self.aesgcm.encrypt(nonce, plaintext, self.VERSION + aad)
        return self.VERSION + nonce + ciphertext
    
    def decrypt(self, blob: bytes, aad: bytes = b"") -> bytes:
        version = blob[:1]
        if version != self.VERSION:
            raise ValueError("Unsupported ciphertext version")
        nonce = blob[1:13]
        ciphertext = blob[13:]
        return self.aesgcm.decrypt(nonce, ciphertext, version + aad)
```

### 8.3 Key Hierarchy

```python
class KeyHierarchy:
    # Level 0: KMS/HSM-backed root
    ROOT_KEY_PROVIDER = "aws_kms"  # or hashicorp_vault
    
    # Level 1: Domain KEKs (rotated periodically)
    DOMAIN_KEKS = {
        "credentials": "kek_cred_v1",
        "user_secrets": "kek_user_v1",
        "memory_pii": "kek_pii_v1",
        "audit": "kek_audit_v1",
    }
    
    # Level 2: Data Encryption Keys (per-object)
    # Wrapped by domain KEK
```

---

## 9. Data Classification

### 9.1 Classification Levels

```python
class DataLevel(str, Enum):
    PUBLIC = "public"           # Safe for public disclosure
    INTERNAL = "internal"      # Business operational
    CONFIDENTIAL = "confidential"  # User/business data
    RESTRICTED = "restricted"  # Secrets, high-impact

class LogPolicy(str, Enum):
    ALLOWED = "allowed"
    REDACTED = "redacted"
    METADATA_ONLY = "metadata_only"
    FORBIDDEN = "forbidden"

@dataclass
class DataClassification:
    level: DataLevel
    pii: bool = False
    financial: bool = False
    auth_secret: bool = False
    encryption_required: bool = True
    log_policy: LogPolicy = LogPolicy.REDACTED
    retention_days: int | None = None
```

### 9.2 Classification Mapping

| Data Type | Level | Encryption | Logging | Retention |
|-----------|-------|------------|---------|------------|
| user.email | CONFIDENTIAL | Yes | REDACTED | Account lifetime |
| message.content | CONFIDENTIAL | Yes | METADATA_ONLY | User policy |
| session.refresh_token | RESTRICTED | Yes | FORBIDDEN | Rotation window |
| password_hash | RESTRICTED | Yes | FORBIDDEN | While active |
| API keys | RESTRICTED | Yes | FORBIDDEN | Per key lifecycle |
| payment info | RESTRICTED | Tokenized | FORBIDDEN | Legal minimum |
| preferences | CONFIDENTIAL | Yes | REDACTED | User lifecycle |
| analytics (agg) | INTERNAL | If user-linked | ALLOWED | Policy-based |

---

## 10. Observability & Metrics

### 10.1 Security Metrics

| Metric | Type | Alert |
|--------|------|-------|
| ai_security.prompt_injection_suspected_total | counter | rate > 5/min |
| ai_security.tool_request_blocked_total | counter | any |
| ai_security.approval_required_total | counter | - |
| ai_security.approval_denied_total | counter | any |
| ai_security.restricted_memory_filtered_total | counter | - |
| ai_security.untrusted_content_quarantined_total | counter | - |
| ai_security.schema_parse_fail_total | counter | any |
| ai_security.output_policy_violation_total | counter | any |
| ai_security.secret_exposure_prevented_total | counter | - |
| ai_security.max_tool_calls_exceeded_total | counter | - |
| policy.denied.total | counter | rate > 10/min |
| policy.denied.unauthorized | counter | any |

### 10.2 Audit Fields

Every security event logs:
- actor_id, account_id, session_id, device_id
- workload_identity
- action, resource_type, resource_id
- policy_decision, reason
- trust_level, approval_state
- trace_id, task_id, workflow_id
- **NEVER logs:** tokens, passwords, API keys, raw secrets

---

## 11. API Contracts

### 11.1 Authorization

```yaml
POST /security/authorize
  Request:
    {
      "actor_id": "usr_123",
      "actor_type": "user",
      "account_id": "acc_123",
      "session_id": "session_xyz",
      "assurance_level": "aal2",
      "action": "tools:send_message",
      "content_trust_level": "user_input",
      "risk_score": 0.3,
      "approval_state": "approved"
    }
  Response:
    {
      "allow": true,
      "reason": "policy allows",
      "obligations": []
    }
```

### 11.2 Content Defense

```yaml
POST /security/content/evaluate
  Request:
    {
      "content": "...",
      "source": { "type": "web_content", "url": "https://..." }
    }
  Response:
    {
      "trust_score": 0.7,
      "channel_assignment": "data_context",
      "response_action": "lower_trust",
      "suspicious_signals": [],
      "block": false,
      "pii_redacted": false,
      "content_safety_passed": true
    }
```

### 11.3 Tool Gate

```yaml
POST /security/tool/validate
  Request:
    {
      "tool_name": "send_message",
      "scope": "communication:sms:send",
      "normalized_params": {...},
      "risk_score": 0.5,
      "approval_token": "..."
    }
  Response:
    {
      "allowed": true,
      "reason": "approved"
    }
```

---

## 12. Runbook

### 12.1 Suspicious Content Detected

```bash
# Check recent injection attempts
curl http://security:8015/security/content/events

# Check trust scores
curl http://security:8015/metrics | grep trust_level

# Update blocking rules
kubectl apply -f security-policy.yaml
```

### 12.2 Unauthorized Tool Access

```bash
# Check blocked requests
curl http://security:8015/security/tool/denials

# Verify OPA policy
kubectl exec -it security-0 -- opa eval -d /policy "data.butler.authz.allow"
```

---

*Document owner: Security Team*  
*Version: 2.1 (Implementation-ready)*  
*Last updated: 2026-04-18*
