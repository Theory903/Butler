# Security Documentation

**Purpose:** Complete security baseline for Butler AI

---

## OVERVIEW

5 security documents covering: baseline, crypto standards, key management, data classification, AI security.

---

## WHERE TO LOOK

| Document | Lines | Purpose |
|----------|-------|---------|
| SECURITY_BASELINE.md | 601 | Core principles, TLS 1.3, mTLS, encryption at rest |
| crypto-standards.md | 120 | AES-256-GCM, RSA-OAEP, Argon2id, ECDSA, X25519 |
| key-management.md | 208 | Key hierarchy, envelope encryption, rotation |
| data-classification.md | 140 | PUBLIC/INTERNAL/SENSITIVE/SECRET handling |
| ai-security.md | 406 | OWASP Top 10 for LLMs, prompt injection, tool gating |
| SECURITY.md | 140 | Security guidelines summary |

---

## REQUIREMENTS (MANDATORY)

| Requirement | Standard |
|-------------|----------|
| Transport | TLS 1.3 |
| Internal | mTLS |
| Encryption | AES-256-GCM |
| Key exchange | X25519 |
| Signing | ECDSA |
| Password hash | Argon2id (NOT bcrypt) |
| Data classification | 4 levels with handling rules |

---

## ANTI-PATTERNS

- NEVER use bcrypt for passwords (use Argon2id)
- NEVER skip data classification
- NEVER use outdated TLS versions
- NEVER skip mTLS for internal services