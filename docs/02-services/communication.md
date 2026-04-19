# Communication Service - Technical Specification

> **For:** Engineering  
> **For:** Engineering  
> **Status:** Active (v3.1) [ACTIVE: SMS, Email, Push | GAPS: WhatsApp Business]
> **Version:** 3.1  
> **Reference:** Policy-governed multi-channel delivery and inbound communication runtime

---

## 0. Implementation Status

| Phase | Component | Status | Description |
|-------|-----------|--------|-------------|
| 1 | **Delivery Engine** | [IMPLEMENTED] | Multi-channel routing |
| 2 | **Policy Layer** | [IMPLEMENTED] | Consent and quiet hours |
| 3 | **Idempotency** | [IMPLEMENTED] | Deduplication logic |
| 4 | **SMS/Email** | [IMPLEMENTED] | Twilio and SES integration |
| 5 | **Push** | [PARTIAL] | FCM / APNS integration |
| 6 | **WhatsApp** | [STUB] | Meta Business API integration |

---

## 1. Service Overview

### 1.1 Purpose
The Communication service is Butler's **policy-governed multi-channel delivery and inbound communication runtime** across SMS, WhatsApp, email, and push.

This is NOT "send message to provider." It's a communications control plane that:
- Enforces channel policy before send
- Manages consent, quiet hours, sender identity
- Normalizes provider status to Butler contracts
- Handles inbound webhook normalization
- Manages suppressions, bounces, complaints

### 1.2 Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│           Butler Communications Control Plane                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  INPUT: Orchestrator / Services                                         │
│     │                                                                    │
│     ▼                                                                    │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ POLICY LAYER (Always First)                                      │   │
│  │  • consent / quiet hours check                                │   │
│  │  • sender identity verification                               │   │
│  │  • template/session eligibility                          │   │
│  │  • approval/token verification                           │   │
│  │  • risk class gating                                   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│     │                                                                    │
│     ▼                                                                    │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ CANONICAL MESSAGE ROUTER                                │   │
│  │  • sms / whatsapp / email / push                     │   │
│  │  • priority lane assignment                              │   │
│  │  • idempotency verification                          │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│     │                                                                    │
│     ▼                                                                    │
│  ┌────────────────────────────────────────��─────────────────────────┐   │
│  │ DELIVERY RUNTIME                                           │   │
│  │  • queue priority lanes (critical/interactive/bulk)         │   │
│  │  • per-channel retry policy                                │   │
│  │  • provider failover logic                             │   │
│  │  • DLQ handling                                      │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│     │                                                                    │
│     ▼                                                                    │
│  OUTPUT: Provider APIs                                              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Boundaries

| Service | Boundary |
|---------|----------|
| Communication | Never decides message content - only delivery governance |
| Orchestrator | Decides what to send, when |
| Data | Stores delivery metadata, NOT message content |
| Memory | Stores message content with retention policy |

### 1.4 Hermes Library Integration
Communication is **deferred**. Hermes channel adapters preserved for library inventory, not active Butler behavior.

---

## 2. Policy Layer

### 2.1 Pre-Send Policy Checks

```python
class CommunicationPolicy:
    """Policy governance before any provider call"""
    
    async def pre_send_check(self, send_request: SendRequest) -> PolicyResult:
        """Run all policy checks before enqueue"""
        
        # 1. Consent check
        consent = await self.check_consent(
            send_request.recipient, 
            send_request.channel
        )
        if not consent.allowed:
            return PolicyResult(allowed=False, reason=consent.reason)
        
        # 2. Quiet hours
        if not await self.quiet_hours_allows(send_request.recipient):
            return PolicyResult(allowed=False, reason="quiet_hours")
        
        # 3. Sender identity
        sender = await self.verify_sender(
            send_request.sender_profile_id,
            send_request.channel
        )
        if not sender.verified:
            return PolicyResult(allowed=False, reason="sender_not_verified")
        
        # 4. Template/session eligibility (WhatsApp)
        if send_request.channel == "whatsapp":
            wacom_check = await self.check_whatsapp_policy(send_request)
            if not wacom_check.allowed:
                return PolicyResult(allowed=False, reason=wacom_check.reason)
        
        # 5. Approval token for sensitive sends
        if send_request.risk_class == "high":
            approval = await self.verify_approval_token(
                send_request.approval_token,
                send_request.risk_class
            )
            if not approval.valid:
                return PolicyResult(allowed=False, reason="approval_required")
        
        return PolicyResult(allowed=True)

@dataclass
class PolicyResult:
    allowed: bool
    reason: str = None
    suppressed: bool = False  # Silent suppress vs error
```

### 2.2 Consent & Suppression

```python
@dataclass
class ConsentState:
    channel: str
    recipient: str
    status: str  # active, suppressed, pending
    reason: str = None  # user_opt_out, bounce, complaint
    updated_at: datetime

class SuppressionManager:
    """Handle bounces, complaints, opt-outs"""
    
    async def handle_bounce(self, recipient: str, channel: str, bounce_type: str):
        """Hard bounce → suppress immediately"""
        await self.suppressions.upsert(ConsentState(
            channel=channel,
            recipient=recipient,
            status="suppressed",
            reason="hard_bounce" if bounce_type == "hard" else "complaint"
        ))
    
    async def handle_complaint(self, recipient: str, channel: str):
        """Complaint → suppress"""
        await self.suppressions.upsert(ConsentState(
            channel=channel,
            recipient=recipient,
            status="suppressed",
            reason="complaint"
        ))
    
    async def check_suppressed(self, recipient: str, channel: str) -> bool:
        """Check before send"""
        state = await self.suppressions.get(recipient, channel)
        return state and state.status == "suppressed"
```

### 2.3 Sender Identity

```python
@dataclass
class SenderProfile:
    id: str
    type: str  # personal_email, business_email, whatsapp_business, sms_short_code
    verified: bool
    capabilities: list[str]  # transactional, marketing
    domain: str = None
    phone_number: str = None
    restrictions: dict = {}

class SenderManager:
    """Manage sender identities"""
    
    async def get_sender(self, profile_id: str, channel: str) -> SenderProfile:
        # Query sender profile with channel-specific verified state
        pass
    
    async def verify_capacity(self, profile_id: str, message_class: str) -> bool:
        """Transactional vs marketing separation"""
        sender = await self.get_sender(profile_id, channel)
        return message_class in sender.capabilities
```

---

## 3. Rich Delivery Status Model

### 3.1 Normalized Delivery Phase

```python
from enum import Enum

class DeliveryPhase(Enum):
    """Normalized across all providers"""
    ACCEPTED = "accepted"        # Provider accepted
    OUTBOUND = "outbound"       # In transit to carrier/network
    DELIVERED = "delivered"     # Handset/app confirmed
    READ = "read"             # User opened (where supported)
    FAILED = "failed"         # Permanent failure
    SUPPRESSED = "suppressed"  # Bounced/complaint/opt-out
    COMPLAINT = "complaint"    # Email complaint

class DeliveryStatus(Enum):
    """Butler internal status"""
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    BOUNCED = "bounced"
    COMPLAINT = "complaint"
    SUPPRESSED = "suppressed"
```

### 3.2 Provider-Native Status Mapping

```python
@dataclass
class DeliveryState:
    """Full delivery state"""
    message_id: str
    channel: str
    provider: str
    
    # Normalized
    phase: DeliveryPhase
    status: DeliveryStatus
    terminal: bool
    retryable: bool
    
    # Provider-native (raw)
    provider_status_raw: str = None
    provider_event_type: str = None
    
    # Metadata
    provider_message_id: str = None
    first_provider_acceptance: datetime = None
    final_delivery: datetime = None
    retry_count: int = 0

# Provider status mapping [STUB]
PROVIDER_STATUS_MAP = {
    "twilio": {  # [STUB]
        "accepted": ("OUTBOUND", False, False),
        "queued": ("OUTBOUND", False, False),
        "sending": ("OUTBOUND", False, False),
        "sent": ("DELIVERED", False, False),
        "delivered": ("DELIVERED", True, False),
        "failed": ("FAILED", True, False),
        "undelivered": ("FAILED", True, False),
    },
    "sendgrid": {  # [STUB]
        "processed": ("ACCEPTED", False, False),
        "deferred": ("OUTBOUND", False, True),
        "delivered": ("DELIVERED", True, False),
        "bounced": ("SUPPRESSED", True, False),
        "opened": ("READ", True, False),
        "clicked": ("READ", True, False),
        "spam_report": ("COMPLAINT", True, False),
        "unsubscribe": ("SUPPRESSED", True, False),
    },
    "whatsapp": {  # [STUB]
        "sent": ("OUTBOUND", False, False),
        "delivered": ("DELIVERED", True, False),
        "read": ("READ", True, False),
        "failed": ("FAILED", True, False),
    },
    "fcm": {  # [STUB]
        "sent": ("OUTBOUND", False, False),
        "delivered": ("DELIVERED", True, False),
    }
}
```

---

## 4. Idempotency

### 4.1 Strong Idempotency Key

```python
import hashlib
import json

class IdempotencyManager:
    """Real deduplication, not accidental suppression"""
    
    def compute_idem_key(
        self, 
        actor: str,
        channel: str,
        recipient: str,
        content: dict,
        template_id: str = None,
        media_ref: str = None
    ) -> str:
        """Compute deterministic hash"""
        
        # Normalize content for consistent hash
        canonical = {
            "actor": actor,
            "channel": channel,
            "recipient": recipient,
            "content_hash": hashlib.sha256(
                json.dumps(content, sort_keys=True).encode()
            ).hexdigest()[:16],
            "template_id": template_id,
            "media_ref": media_ref
        }
        
        # Hash to get key
        key_input = json.dumps(canonical, sort_keys=True)
        return f"idem:{hashlib.sha256(key_input.encode()).hexdigest()[:24]}"
    
    async def check_dedupe(self, idem_key: str) -> str | None:
        """Check if already processed, return message_id if exists"""
        existing = await self.redis.get(f"idem:{idem_key}")
        if existing:
            return json.loads(existing)["message_id"]
        return None
    
    async def mark_processed(
        self, 
        idem_key: str, 
        message_id: str, 
        provider_ref: str = None
    ):
        """Mark as processed"""
        await self.redis.setex(
            f"idem:{idem_key}", 
            86400,  # 24h window
            json.dumps({
                "message_id": message_id,
                "provider_ref": provider_ref
            })
        )
```

---

## 5. Retry Policy by Channel

### 5.1 Channel-Specific Retry

```python
from enum import Enum

class BackoffClass(Enum):
    LINEAR = "linear"      # SMS/WhatsApp
    EXPONENTIAL = "exp"    # Email
    NONE = "none"         # WhatsApp templates

@dataclass
class RetryPolicy:
    max_attempts: int
    backoff_class: BackoffClass
    retry_window_s: int     # Don't retry after this window
    duplicate_risk: str    # high, medium, low
    provider_safe: list[str]  # Codes safe to retry

RETRY_POLICIES = {
    "sms": RetryPolicy(
        max_attempts=3,
        backoff_class=BackoffClass.LINEAR,
        retry_window_s=300,  # 5 min
        duplicate_risk="high",
        provider_safe=["21601", "21611", "21614"]
    ),
    "whatsapp": RetryPolicy(
        max_attempts=2,
        backoff_class=BackoffClass.NONE,  # Templates can't retry same
        retry_window_s=0,
        duplicate_risk="high",
        provider_safe=["131031"]  # Template error
    ),
    "email": RetryPolicy(
        max_attempts=5,
        backoff_class=BackoffClass.EXPONENTIAL,
        retry_window_s=3600,  # 1 hour
        duplicate_risk="medium",
        provider_safe=["400", "401"]
    ),
    "push": RetryPolicy(
        max_attempts=3,
        backoff_class=BackoffClass.LINEAR,
        retry_window_s=600,
        duplicate_risk="medium",
        provider_safe=["INVALID_ARGUMENT"]
    )
}

# Token-level handling for push
class TokenManager:
    """Invalid token pruning"""
    
    async def handle_invalid_token(self, token: str, error: str):
        if "InvalidRegistration" in error or "NotRegistered" in error:
            await self.token_store.mark_invalid(token)
            await self.emit_alert("invalid_token", token)
```

---

## 6. Webhook Security

### 6.1 Signed Webhook Verification

```python
class WebhookValidator:
    """All webhook verification"""
    
    # Twilio
    async def verify_twilio(self, request: Request, params: dict) -> bool:
        signature = request.headers.get("X-Twilio-Signature")
        return self.verify_hmac(signature, params, self.twilio_auth_token)
    
    # WhatsApp
    async def verify_whatsapp(self, body: bytes, signature: str) -> bool:
        expected = hmac.new(self.whatsapp_secret, body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)
    
    # SendGrid (SIGNED)
    async def verify_sendgrid(self, body: bytes, signature: str) -> bool:
        """SendGrid signed webhook - verify with public key"""
        try:
            # Verify Ed25519 signature
            public_key = self.load_sendgrid_public_key()
            signature_bytes = bytes.fromhex(signature)
            return public_key.verify(body, signature_bytes)
        except Exception:
            return False
    
    # SES (via SNS)
    async def verify_ses_sns(self, message: dict) -> bool:
        """Verify SNS topic subscription"""
        # Check topic subscription URL
        if message.get("Type") == "SubscriptionConfirmation":
            await self.confirm_sns_subscription(message["SubscribeURL"])
        return True
```

---

## 7. Inbound Normalization

### 7.1 Canonical Inbound Envelope

```python
@dataclass
class CanonicalInbound:
    """Normalized inbound from all channels"""
    
    channel: str                              # sms, whatsapp, email, push
    provider: str                           # twilio, meta, sendgrid, ses, firebase
    provider_message_id: str
    
    external_sender: str                  # From phone/email
    recipient_identity: str               # Butler account
    
    received_at: datetime
    
    content: dict                          # Normalized content
    attachments: list[dict]
    
    authenticity: AuthenticityResult        # Verification results
    
    conversation_ref: str = None          # Thread ID
    metadata: dict = {}

@dataclass
class AuthenticityResult:
    verified: bool
    method: str                          # signature, spf, dkim, dmark
    details: dict

class InboundNormalizer:
    """Normalize all inbound to canonical envelope"""
    
    async def normalize(self, provider: str, payload: dict) -> CanonicalInbound:
        match provider:
            case "twilio":
                return self.normalize_sms(payload)
            case "meta":
                return self.normalize_whatsapp(payload)
            case "sendgrid":
                return self.normalize_email(payload)
            case "firebase":
                return self.normalize_push(payload)
    
    async def normalize_sms(self, payload: dict) -> CanonicalInbound:
        return CanonicalInbound(
            channel="sms",
            provider="twilio",
            provider_message_id=payload.get("MessageSid"),
            external_sender=payload.get("From"),
            recipient_identity=payload.get("To"),
            received_at=datetime.fromisoformat(payload.get("Timestamp")),
            content={"text": payload.get("Body")},
            authenticity=AuthenticityResult(
                verified=True,  # Twilio verifies source
                method="twilio_signature"
            ),
            conversation_ref=payload.get("ConversationSid")
        )
```

---

## 8. WhatsApp Policy

### 8.1 WhatsApp-Specific

```python
@dataclass
class WhatsAppPolicy:
    message_mode: str  # session, template, interactive
    template_name: str = None
    template_locale: str = "en_US"
    components: list[dict] = None
    
    async def validate(self) -> PolicyResult:
        # Check session window still valid
        if self.message_mode == "session":
            # 24h window from last user message
            if await self.session_expired():
                return PolicyResult(allowed=False, reason="session_expired")
        
        # Check template eligible
        if self.message_mode == "template":
            if not await self.template_eligible():
                return PolicyResult(allowed=False, reason="template_not_approved")
        
        return PolicyResult(allowed=True)

# Conversation management
class WhatsAppConversation:
    """Track conversation state per WhatsApp"""
    
    SESSION_WINDOW = 24 * 3600  # 24 hours
    
    async def check_conversation_policy(self, from_number: str) -> WhatsAppPolicy:
        # Check if user-initiated within window
        last_user = await self.get_last_message(from_number, "inbound")
        
        if last_user and (now() - last_user.timestamp).seconds < self.SESSION_WINDOW:
            return WhatsAppPolicy(message_mode="session")
        
        # Only templates allowed outside session
        return WhatsAppPolicy(message_mode="template")
```

---

## 9. Queue Priority Classes

### 9.1 Priority Lanes

```python
from enum import Enum

class QueueClass(Enum):
    CRITICAL = "critical"      # Security alerts, approvals
    INTERACTIVE = "interactive"  # Chat responses
    BACKGROUND = "background"  # Scheduled notifications
    BULK = "bulk"           # Marketing/newsletter

QUEUE_STREAMS = {
    QueueClass.CRITICAL: "comm:critical",
    QueueClass.INTERACTIVE: "comm:interactive", 
    QueueClass.BACKGROUND: "comm:background",
    QueueClass.BULK: "comm:bulk"
}

# Priority mapping examples
PRIORITY_MAPPING = {
    "security_alert": QueueClass.CRITICAL,
    "approval_request": QueueClass.CRITICAL,
    "reminder": QueueClass.BACKGROUND,
    "chat_response": QueueClass.INTERACTIVE,
    "newsletter": QueueClass.BULK
}

# Worker pools per class [STUB]
WORKER_CONFIG = {
    QueueClass.CRITICAL: {"workers": 4, "timeout": 5},
    QueueClass.INTERACTIVE: {"workers": 8, "timeout": 15},
    QueueClass.BACKGROUND: {"workers": 2, "timeout": 60},
    QueueClass.BULK: {"workers": 1, "timeout": 300}
}
```

---

## 10. Provider Failover

### 10.1 Failover Rules

```python
class ProviderFailover:
    """Define when failover is allowed"""
    
    @dataclass
    class FailoverRules:
        eligible: bool
        cooldown_s: int = 300
        require_acceptance: bool = False
        provider_affinity: list[str] = None
    
    RULES = {
        "sms": FailoverRules(
            eligible=True,  # Twilio → aggregator
            cooldown_s=300,
            require_acceptance=True
        ),
        "email": FailoverRules(
            eligible=True,  # SES ↔ SendGrid in some orgs
            cooldown_s=600,
            require_acceptance=False,
            provider_affinity=["ses", "sendgrid"]
        ),
        "whatsapp": FailoverRules(
            eligible=False,  # Usually locked
            require_acceptance=False
        ),
        "push": FailoverRules(
            eligible=False,  # Not same shape
            require_acceptance=False
        )
    }
```

---

## 11. API Contracts

### 11.1 Send Message

```python
POST /api/v1/comm/send
  Request:
    {
      "channel": "sms|whatsapp|email|push",
      "recipient": "+1234567890",
      "content": {...},
      "sender_profile_id": "...",
      "priority_class": "interactive",  # Optional
      "idempotency_key": "...",  # Optional override
      "risk_class": "normal|high",  # For approvals
      "approval_token": "...",  # If risk_class=high
      "metadata": {...}
    }
  Response:
    {
      "message_id": "...",
      "status": "queued",
      "status_url": "/api/v1/comm/status/...",
      "phase": "accepted",
      "first_delivery_expected": "..."
    }
```

### 11.2 Prepare (Policy Check)

```python
POST /api/v1/comm/prepare
  # Check if send is allowed WITHOUT enqueueing
  # Returns policy result
  Request: same as /send
  Response:
    {
      "allowed": true|false,
      "reason": "...",
      "suppressed": true|false
    }
```

### 11.3 Inbound Webhook

```python
POST /api/v1/comm/webhooks/{provider}
  # twilio|meta|sendgrid|ses|firebase
  # Signature verified internally
  # Returns normalized
  Response:
    {
      "channel": "...",
      "provider": "...",
      "provider_message_id": "...",
      "external_sender": "...",
      "content": {...},
      "conversation_ref": "..."
    }
```

### 11.4 Status

```python
GET /api/v1/comm/status/{message_id}
  Response:
    {
      "message_id": "...",
      "phase": "delivered",
      "status": "delivered",
      "terminal": true,
      "retryable": false,
      "provider_status_raw": "...",
      "delivered_at": "...",
      "retry_count": 2
    }
```

---

## 12. Observability

### 12.1 Key Metrics

| Metric | Type | Alert |
|--------|------|-------|
| provider_acceptance_rate | gauge | <0.98 |
| delivered_rate_{channel} | gauge | Target per channel |
| bounce_rate | gauge | >0.05 |
| complaint_rate | gauge | >0.01 |
| invalid_token_rate_{push} | gauge | >0.02 |
| whatsapp_policy_rejection_rate | gauge | >0.05 |
| retry_exhaustion_rate | gauge | >0.1 |
| dlq_depth_{channel} | gauge | >100 |
| status_callback_lag | histogram | >30s |
| webhook_verify_failure_rate | gauge | >0.01 |

---

## 13. Error Codes (RFC 9457)

| Code | Error | HTTP | Cause |
|------|-------|------|-------|
| C001 | channel-invalid | 400 | Unsupported channel |
| C002 | consent-denied | 403 | Recipient suppressed |
| C003 | quiet-hours | 403 | Outside allowed hours |
| C004 | sender-invalid | 400 | Sender not verified |
| C005 | idempotency-conflict | 409 | Duplicate message |
| C006 | approval-required | 403 | High-risk requires token |
| C007 | template-ineligible | 400 | WhatsApp policy |
| C008 | rate-limited | 429 | Provider rate limit |
| C009 | provider-error | 502 | Provider failure |

---

*Document owner: Communication Team*  
*Version: 2.0 (Implementation-ready)*  
*Last updated: 2026-04-18*