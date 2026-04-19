# Security Baseline

> **For:** All Engineering Teams  
> **Status:** Production Required  
> **Version:** 2.0  
> **Owner:** Security Team

---

## v2.0 Changes

- Added trust classification model
- Added channel separation
- Added tool gating policy
- Added memory isolation guarantees
- Updated health model with startup/liveness/readiness/degraded

---

## 1. Core Security Principles

The following principles apply **universally** across all Butler services:

| Principle | Implementation |
|-----------|----------------|
| **Encrypt data at rest** | AES-256-GCM for all persistent data |
| **Encrypt data in transit** | TLS 1.3 everywhere; mTLS for internal services |
| **Sign actions** | All high-risk actions signed with HMAC |
| **Verify outputs** | All tool/ML outputs validated before execution |
| **Approve risky behavior** | Human approval for high-risk actions |
| **Log everything important** | Immutable audit trail for security events |
| **Classify trust** | Content trust levels with processing pipelines |
| **Separate channels** | Untrusted/medium/trusted channel isolation |
| **Gate tools** | Policy-based tool execution control |

---

## 2. Network Security

### 2.1 TLS Configuration

| Traffic Type | Requirement | Implementation |
|--------------|-------------|----------------|
| Public HTTPS | TLS 1.3 (minimum TLS 1.2) | Nginx/Traefik with modern ciphers |
| Internal service-to-service | **mTLS** | Linkerd or Istio service mesh |
| Database connections | TLS required | PostgreSQL, Redis TLS enabled |
| External API calls | TLS 1.3 | Client cert validation |

**Configuration:**
```yaml
# nginx.conf - public endpoints
ssl_protocols TLSv1.3 TLSv1.2;
ssl_ciphers ECDHE-ECDSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA512;
ssl_prefer_server_ciphers on;
ssl_session_timeout 1d;
ssl_session_tickets off;
```

### 2.2 Internal mTLS

```
┌─────────┐     mTLS      ┌─────────┐
│Gateway  │←─────────────→│Orchestr.│
│(8000)   │              │(8002)   │
└─────────┘              └─────────┘
       │                        │
       │   mTLS (service mesh) │
       ▼                        ▼
┌─────────┐              ┌─────────┐
│ Memory  │←─────────────→│  Tools │
│(8003)   │              │(8005)   │
└─────────┘              └─────────┘
```

All internal services use mutual TLS with:
- Service identity certificates (SPIFFE format)
- Automatic rotation every 24 hours
- Certificate verification against trust anchor

---

## 3. Trust Classification Model

### 3.1 Trust Levels

```
┌─────────────────────────────────────────────────────────────┐
│                 TRUST CLASSIFICATION                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  TRUSTED (system)                                            │
│    ├─ System prompts                                         │
│    ├─ Core logic                                             │
│    └─ Butler-owned code                                      │
│                                                              │
│  MEDIUM_TRUST (controlled)                                    │
│    ├─ MCP adapters                                          │
│    ├─ Registered tools                                       │
│    └─ Approved plugins                                      │
│                                                              │
│  UNTRUSTED (untrusted)                                      │
│    ├─ Web content (scraped/retrieved)                       │
│    ├─ OCR output                                             │
│    ├─ User uploads                                          │
│    ├─ Email content                                         │
│    └─ External API responses                                │
│                                                              │
│  PROCESSING:                                                │
│    ┌──────────┐   ┌──────────┐   ┌──────────┐              │
│    │ Channel  │→ │ Sanitize │→ │ Validate │→ │ Action   │              │
│    │Classifier│   │+Detect   │   │+Parse    │   │ Planner  │              │
│    └──────────┘   └──────────┘   └──────────┘   └──────────┘              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Channel Separation

Each trust level runs in isolated processing channels:

```python
TRUST_CHANNELS = {
    "trusted": {
        "description": "System-controlled execution",
        "allowed_operations": ["read", "write", "execute"],
        "requires_approval": False,
        "audit_level": "summary",
    },
    "medium_trust": {
        "description": "Butler-verified capability",
        "allowed_operations": ["read", "write"],
        "requires_approval": False,
        "audit_level": "full",
    },
    "untrusted": {
        "description": "External/unverified input",
        "allowed_operations": ["read_only"],
        "requires_approval": True,
        "requires_human_review": True,
        "audit_level": "full",
    }
}
```

### 3.3 Processing Pipeline

```python
class ContentTrustClassifier:
    """Classify content trust level"""
    
    TRUST_LEVELS = {
        "system_prompt": "trusted",
        "user_direct": "trusted", 
        "retrieved_memory": "medium_trust",
        "web_content": "untrusted",
        "ocr_output": "untrusted",
        "email_content": "untrusted",
        "uploaded_file": "untrusted",
        "external_api": "untrusted",
    }
    
    def classify(self, source: str) -> str:
        return self.TRUST_LEVELS.get(source, "untrusted")
    
    def get_processing_pipeline(self, source: str) -> list[str]:
        """Get processing steps based on trust level"""
        
        trust = self.classify(source)
        
        if trust == "trusted":
            return ["parse"]
        elif trust == "medium_trust":
            return ["sanitize", "validate", "parse"]
        else:  # untrusted
            return ["sanitize", "detect_injection", "validate", "parse", "isolate"]
```

---

## 4. Tool Gating Policy

### 4.1 Tool Execution Control

Tools NEVER execute directly from model requests. All tool execution goes through policy gating:

```python
class ToolGatingPolicy:
    """Policy-based tool execution control"""
    
    # Risk tiers
    RISK_TIERS = {
        "low": {
            "examples": ["search", "get_memory", "get_context", "time"],
            "requires_approval": False,
        },
        "medium": {
            "examples": ["send_message", "create_event", "send_email"],
            "requires_approval": False,
            "log_for_review": True,
        },
        "high": {
            "examples": ["payment", "device_control", "delete_data"],
            "requires_approval": True,
            "audit": True,
        },
        "critical": {
            "examples": ["admin_action", "lock_unlock", "camera_access"],
            "requires_approval": True,
            "dual_authorization": True,
            "audit": True,
        }
    }
    
    async def evaluate(
        self,
        tool_name: str,
        params: dict,
        context: ToolExecutionContext
    ) -> ToolGatingResult:
        """Evaluate tool execution request"""
        
        # 1. Check tool exists
        tool = await self.get_tool(tool_name)
        if not tool:
            return ToolGatingResult(allowed=False, reason="tool_not_found")
        
        # 2. Check risk tier
        risk_tier = tool.risk_tier
        
        # 3. Check user permissions
        if not await self.has_permission(context.user_id, tool_name):
            return ToolGatingResult(allowed=False, reason="permission_denied")
        
        # 4. Check approval requirement
        if self.RISK_TIERS[risk_tier].get("requires_approval"):
            if not context.approved:
                return ToolGatingResult(
                    allowed=False,
                    reason="requires_approval",
                    approval_type=risk_tier
                )
        
        # 5. Log for audit
        await self.audit.log(tool_name, params, context, risk_tier)
        
        return ToolGatingResult(allowed=True)
```

### 4.2 Idempotency Requirements

All tools with side effects MUST implement idempotency:

```python
class ToolSpec:
    """Tool specification with policy requirements"""
    
    required_fields = [
        "name",           # Unique identifier
        "description",    # Human-readable
        "input_schema",   # JSON Schema
        "output_schema", # JSON Schema
        "risk_tier",     # low/medium/high/critical
        "idempotent",    # True if safe to retry
        "idempotency_key", # Session ID or similar
    ]
    
    # Example: send_message tool
    send_message = ToolSpec(
        name="send_message",
        risk_tier="medium",
        idempotent=True,
        idempotency_key="message_idempotency_key",  # Server-generated
        input_schema={
            "recipient": {"type": "string"},
            "content": {"type": "string"},
            "idempotency_key": {"type": "string", "generated": True}
        },
        output_schema={
            "message_id": {"type": "string"},
            "sent_at": {"type": "timestamp"}
        }
    )
```

---

## 5. Memory Isolation

### 5.1 Access Control by Classification

Memory content is classified and access-controlled:

```python
class MemoryIsolation:
    """Memory access isolation"""
    
    # Sensitive memory classes requiring isolation
    RESTRICTED_CLASSES = [
        "payment_information",
        "authentication_credentials",
        "security_settings",
        "private_messages",
        "health_data",
        "financial_data"
    ]
    
    async def filter_retrieval(
        self,
        retrieved_docs: list[Document],
        query_context: QueryContext
    ) -> list[Document]:
        """Filter retrieved documents based on access"""
        
        filtered = []
        
        for doc in retrieved_docs:
            # Check classification
            if doc.classification in self.RESTRICTED_CLASSES:
                # Verify task purpose
                if not self.task_justifies_access(query_context.task, doc.classification):
                    await self.audit.log_access_denied(
                        doc.id, 
                        query_context.user_id, 
                        "classification"
                    )
                    continue
                
                # Verify user has access
                if not await self.user_can_access(query_context.user_id, doc):
                    await self.audit.log_access_denied(
                        doc.id,
                        query_context.user_id,
                        "permission"
                    )
                    continue
            
            filtered.append(doc)
        
        return filtered
```

---

## 6. Encryption Standards

### 6.1 Data at Rest

| Data Type | Algorithm | Mode | Key Management |
|-----------|-----------|------|----------------|
| Database fields | AES-256 | GCM | Per-tenant data key |
| Object storage | AES-256 | GCM | Per-object data key |
| Backups | AES-256 | GCM | Backup-specific key |
| Log archives | AES-256 | GCM | Archive key |
| Vector embeddings | AES-256 | GCM | If contains PII |

### 6.2 Field-Level Encryption

Required for **high-risk data**:
- Refresh tokens
- API secrets
- OAuth credentials  
- Recovery codes
- Financial identifiers
- Government IDs

---

## 7. Authentication

### 7.1 Password Storage

**Required:** Argon2id (not bcrypt)

### 7.2 Passkeys / WebAuthn

Passkeys are **preferred authentication**. Passwords are fallback only.

### 7.3 Session Management

```python
class SessionManager:
    async def create_session(
        self,
        user_id: str,
        device_id: str,
        ip_address: str,
        mfa_verified: bool = False
    ) -> Session:
        """Create session with proper lifecycle"""
        
        access_token = self.generate_token()  # Short-lived: 15 min
        refresh_token = self.generate_token()  # Long-lived: 7 days
        
        # Store refresh token hash (NOT plaintext)
        refresh_hash = hash_token(refresh_token)
        
        session = Session(
            user_id=user_id,
            device_id=device_id,
            access_token=access_token,
            refresh_token_hash=refresh_hash,
            access_expires=datetime.utcnow() + timedelta(minutes=15),
            refresh_expires=datetime.utcnow() + timedelta(days=7),
            created_at=datetime.utcnow(),
            last_active=datetime.utcnow(),
            mfa_verified=mfa_verified,
            risk_score=await self.calculate_risk(user_id, ip_address)
        )
        
        await self.session_store.save(session)
        
        return session, access_token, refresh_token
```

---

## 8. Authorization Model

### 8.1 Permission Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                    PERMISSION MODEL                         │
├─────────────────────────────────────────────────────────────┤
│  Role ──────→ Permission ──────→ Resource                  │
│    │              │                    │                   │
│    │              │                    ├─ action (read/write)│
│    │              │                    ├─ scope (global/tenant)│
│    │              │                    └─ conditions         │
│    │              │                                            │
│    │              └─ belongs to role                          │
│    │                                                           │
│    └─ assigned to user                                        │
│                                                               │
│  Approval Tier ──→ Required for                              │
│       │                                                        │
│       ├─ none        : search, summarize, reminders          │
│       ├─ implicit    : send message (logged)                 │
│       ├─ explicit    : send email, create event              │
│       └─ critical    : payments, lock/unlock, delete data   │
└─────────────────────────────────────────────────────────────┘
```

---

## 9. Health Model (v2.0)

### 9.1 Health States

Butler services distinguish FOUR health states (Kubernetes-inspired):

| State | Description | Indicates | Action |
|-------|------------|----------|--------|
| **STARTING** | Initializing, loading config | Service booting | Wait, don't alert |
| **HEALTHY** | Ready to serve traffic | All checks pass | Serve traffic |
| **DEGRADED** | Serving with issues | Partial failure | Monitor, alert on threshold |
| **UNHEALTHY** | Cannot serve | Critical failure | Alert, escalate |

### 9.2 Health Check Implementation

```python
class ServiceHealth:
    """Four-state health model"""
    
    async def check(self) -> HealthStatus:
        """Determine current health state"""
        
        # Check 1: Startup complete?
        if not self.startup_complete:
            return HealthStatus(
                state="STARTING",
                message="Service initializing",
                checks={"startup": "in_progress"}
            )
        
        # Check 2: Dependencies healthy?
        deps = await self.check_dependencies()
        if deps.failed:
            return HealthStatus(
                state="UNHEALTHY",
                message=f"Dependency failed: {deps.failed}",
                checks={"dependencies": "failed"}
            )
        
        # Check 3: Critical functions working?
        critical = await self.check_critical_functions()
        if critical.errors > self.degraded_threshold:
            return HealthStatus(
                state="DEGRADED",
                message=f"Errors: {critical.errors}",
                checks={"critical": "degraded"}
            )
        
        # Check 4: All good
        return HealthStatus(
            state="HEALTHY",
            message="All checks passed",
            checks={"startup": "complete", "deps": "ok", "critical": "ok"}
        )
```

---

## 10. Audit Logging

### 10.1 Immutable Audit Log

```python
class AuditLogger:
    """Immutable audit trail for high-risk actions"""
    
    HIGH_RISK_ACTIONS = [
        "message_send",
        "email_send",
        "device_control",
        "lock_unlock",
        "camera_access",
        "memory_delete",
        "permission_change",
        "session_create",
        "session_revoke",
        "password_change",
        "mfa_enable",
        "api_key_create",
        "payment_initiate",
        "tool_execution",
        "access_denied"
    ]
    
    async def log(self, action: str, user_id: str, details: dict):
        """Append-only log (no delete)"""
        
        if action in self.HIGH_RISK_ACTIONS:
            log_entry = {
                "id": str(uuid4()),
                "timestamp": datetime.utcnow().isoformat(),
                "action": action,
                "user_id": user_id,
                "details": details,
                "ip_address": details.get("ip_address"),
                "device_id": details.get("device_id"),
                "hash": self.compute_log_hash(action, user_id, details)
            }
            
            await self.audit_store.append(log_entry)
            await self.forward_to_siem(log_entry)
```

### 10.2 PII Redaction

```python
class LogRedactor:
    """Redact PII from logs at source"""
    
    REDACT_PATTERNS = [
        (r'\btoken=([^\s&]+)', 'token=***'),
        (r'Bearer\s+([A-Za-z0-9\-._~+/]+=*)', 'Bearer ***'),
        (r'password["\s:]+([^\s&]+)', 'password: ***'),
        (r'"email"\s*:\s*"([^"]+)', '"email": "***"'),
        (r'"phone"\s*:\s*"([^+]+)', '"phone": "***"'),
        (r'\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}', '****-****-****-****'),
    ]
```

---

## 11. Rate Limiting

### 11.1 Rate Limit Tiers

```python
class RateLimiter:
    USER_LIMITS = {
        "message_send": {"rate": 60, "window": 60},      # 60/min
        "email_send": {"rate": 20, "window": 60},          # 20/min
        "api_request": {"rate": 1000, "window": 3600},    # 1000/hr
        "auth_login": {"rate": 5, "window": 300},         # 5/5min
        "password_reset": {"rate": 3, "window": 3600},      # 3/hr
    }
    
    IP_LIMITS = {
        "global": {"rate": 100, "window": 60},             # 100/min per IP
        "auth": {"rate": 10, "window": 300},                # 10/5min per IP
    }
```

---

## 12. Service-Specific Security

### 12.1 Gateway

| Control | Implementation |
|---------|----------------|
| TLS | TLS 1.3, strong ciphers |
| JWT validation | Signature + expiry + audience check |
| Request signing | X-Signature header for sensitive endpoints |
| WAF | Cloudflare/AWS WAF rules |
| Body size limit | 1MB max (configurable per endpoint) |
| Replay protection | Nonce in requests, 5-minute window |

### 12.2 Auth Service

| Control | Implementation |
|---------|----------------|
| Password hashing | Argon2id (not bcrypt) |
| MFA | TOTP + WebAuthn passkeys |
| Token storage | Refresh token hash (not plaintext) |
| Device binding | Device fingerprint + user binding |
| Session lifecycle | 15min access / 7day refresh |
| Step-up auth | Re-auth for sensitive actions |

### 12.3 Tools Service

| Control | Implementation |
|---------|----------------|
| Request signing | HMAC-SHA256 for tool calls |
| Tool gating | Policy-based evaluation |
| Policy engine | OPA integration |
| Idempotency | Required for all side-effect tools |
| Approval check | Before critical tools execute |

### 12.4 Memory Service

| Control | Implementation |
|---------|----------------|
| Access control | Classification-based |
| Isolation | Trust channel separation |
| Sensitive data | Restricted classes |
| Audit | Full access logging |

---

## 13. Security Monitoring

### 13.1 SLO-Based Alerting

Alerts are triggered by SLO violations, NOT arbitrary thresholds:

| SLO | Target | Alert Condition |
|-----|-------|--------------|
| Error rate | < 1% | > 1% for 5 min |
| Latency P99 | < 1.5s | > 1.5s for 5 min |
| Availability | 99.9% | < 99.9% in window |
| Tool denials | < 5% | > 5% for 10 min |

### 13.2 Security Alerts

| Alert | Condition | Severity |
|-------|-----------|----------|
| Failed logins | >20/user/hour | P2 |
| Suspicious activity | >10x normal rate | P1 |
| Permission denied | >50/hour | P2 |
| Admin actions | Any | P3 |
| Payment attempt | Any | P2 |
| Mass delete | >100 records | P1 |
| Tool denial rate | >5% for 10 min | P1 |
| Trust violation | Any | P1 |

---

## 14. Dependency & Supply Chain

### 14.1 Dependency Scanning

```yaml
scanning:
  frequency: "daily"
  tools:
    - "trivy"          # Container vulnerabilities
    - "safety"         # Python dependencies
    - "npm audit"      # JavaScript dependencies
    - "OWASP Dependency Check"
  
  actions:
    - "block build on HIGH severity"
    - "alert on CRITICAL"
    - "auto-create CVE ticket"
```

### 14.2 Model Supply Chain

| Check | Implementation |
|-------|----------------|
| Model pinning | SHA256 hash of model files |
| Provenance | Model source verified |
| Version control | All versions stored |
| Review process | ML team review before deploy |

---

## Summary

All services **MUST** implement:

- [ ] TLS 1.3 for all external traffic
- [ ] mTLS for all internal traffic  
- [ ] AES-256-GCM for data at rest
- [ ] Trust classification model
- [ ] Channel separation for untrusted content
- [ ] Tool gating policy with risk tiers
- [ ] Memory isolation for sensitive classes
- [ ] Four-state health model
- [ ] SLO-based alerting
- [ ] Argon2id for password hashing
- [ ] WebAuthn/passkeys as primary auth
- [ ] Permission model with approval tiers
- [ ] Immutable audit logging for high-risk actions
- [ ] PII redaction in logs
- [ ] Rate limiting per user + IP
- [ ] Field-level encryption for sensitive data
- [ ] Signed requests for critical actions

---

*Document owner: Security Team*  
*Version: 2.0 - Production Required*  
*Last updated: 2026-04-18*