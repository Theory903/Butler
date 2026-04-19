# Security Documentation

> **For:** Security Team, Engineering  
> **Status:** Production Required  
> **Version:** 2.0

---

## v2.0 Changes

- Added trust classification and channel separation
- Added tool gating policy
- Added four-state health model
- Added SLO-based alerting

---

## 1. Security Architecture

### 1.1 Trust Boundaries

```
┌─────────────────────────────┐
│      Untrusted Internet     │
└──────────────┬──────────────┘
                ↓
┌──────────────┴──────────────┐
│     WAF + CDN (Cloudflare)  │
└──────────────┬──────────────┘
                ↓
┌──────────────┴──────────────┐
│    API Gateway (Edge)        │
│    - Auth (JWT)              │
│    - Rate Limit              │
│    - Tool Gating           │
└──────────────┬──────────────┘
                ↓
┌──────────────┴──────────────┐
│    Internal Services         │
│    - mTLS              │
│    - Service mesh       │
│    - Trust channels     │
└──────────────┬──────────────┘
                ↓
┌──────────────┴──────────────┐
│    Sensitive Data           │
│    - Encryption at rest     │
│    - Vault for secrets   │
│    - Field-level       │
└─────────────────────────────┘
```

### 1.2 Trust Channel Isolation

| Channel | Content Type | Processing | Approval |
|---------|-----------|-----------|----------|
| **trusted** | System prompts, core logic | Direct | None |
| **medium_trust** | MCP tools, registered plugins | Validated | None |
| **untrusted** | Web content, uploads | Sandboxed | Always |

---

## 2. Authentication

### 2.1 User Authentication

| Method | Use Case | Risk Tier | Token TTL |
|--------|----------|---------|----------|
| Passkey (WebAuthn) | Primary | low | Session |
| JWT | API access | low | 15 min |
| Refresh token | Re-auth | medium | 7 days |
| Password | Fallback | high | N/A |

### 2.2 Service Authentication

- mTLS between services
- Rotated certificates (24-hour rotation)
- Vault for secrets

---

## 3. Tool Gating

### 3.1 Tool Execution Flow

```
Model Request → Policy Check → Risk Assessment → Approval → Execution → Audit
```

### 3.2 Risk Tiers

| Tier | Examples | Requires Approval |
|------|---------|--------------|
| low | search, get_memory | No |
| medium | send_message | No (logged) |
| high | payment, device_control | Yes |
| critical | admin, lock_unlock | Yes + dual |

---

## 4. Data Protection

### 4.1 Encryption

| State | Method | Standard |
|-------|--------|----------|
| In transit | TLS 1.3 | Required |
| At rest | AES-256-GCM | Required |
| Field-level | AES-256-GCM | High-risk only |
| In memory | Encrypted heap | Sensitive |

### 4.2 Data Classification

| Level | Examples | Handling |
|-------|----------|----------|
| Public | Docs, blog | No protection |
| Internal | Metrics, logs | Auth required |
| Sensitive | Messages, contacts | Encrypted + audit |
| Secret | Passwords, tokens | Field encryption |

---

## 5. Health Model

### 5.1 Four States

Services implement: STARTING → HEALTHY → DEGRADED → UNHEALTHY

| State | Indicates | Alert |
|-------|----------|------|
| STARTING | Initializing | No |
| HEALTHY | Ready | No |
| DEGRADED | Partial failure | SLO-based |
| UNHEALTHY | Critical | Yes |

---

## 6. Privacy

### 6.1 Data Collection

- Minimal collection principle
- User consent required
- Clear opt-out
- Classification at collection time

### 6.2 Data Retention

| Data Type | Retention | Deletion |
|-----------|-----------|----------|
| Messages | User choice | On request + 30 days |
| Preferences | Forever | On request |
| Logs | 90 days | Automatic |
| ML training | Opt-in | On request |

---

## 7. Security Requirements

### 7.1 Compliance

- GDPR compliant
- CCPA compliant
- SOC 2 Type II (target)

### 7.2 Scanning

| Type | Frequency |
|------|-----------|
| SAST | Every PR |
| DAST | Weekly |
| Dependency scan | Daily |
| Penetration | Quarterly |

### 7.3 SLO-Based Alerting

| SLO | Target | Alert When Violated |
|-----|-------|-----------------|
| Error rate | < 1% | > 1% for 5 min |
| Latency P99 | < 1.5s | > 1.5s for 5 min |
| Tool denials | < 5% | > 5% for 10 min |

---

## 8. Incident Response

### 8.1 Severity Levels

| Level | Description | Response Time |
|-------|-------------|------------|
| P0 | Data breach, system down | < 1 hour |
| P1 | Service impaired | < 4 hours |
| P2 | Security finding | < 24 hours |
| P3 | Improvement | < 1 week |

### 8.2 Contacts

- Security: security@butler.lasmoid.ai
- On-call: PagerDuty
- Legal: legal@butler.lasmoid.ai

---

## 9. Anti-Patterns

### NEVER Use

- bcrypt for passwords (→ Argon2id)
- HS256 for tokens (→ RS256/ES256)
- Raw uploaded code execution
- Threshold-heavy alerting (→ SLO-based)
- Single health state (→ Four-state)

---

*Document owner: Security Team*  
*Version: 2.0 - Production Required*  
*Last updated: 2026-04-18*