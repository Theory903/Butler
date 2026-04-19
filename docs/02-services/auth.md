# Auth Service - Technical Specification

> **For:** Engineering  
> **For:** Engineering  
> **Status:** Active (v3.1) [ACTIVE: JWT, Social, Passkeys | GAPS: Multi-Account Sync]
> **Version:** 3.1  
> **Reference:** Butler identity platform for multi-device, multi-account, and OIDC delegated auth

---

## 0. Implementation Status

| Phase | Component | Status | Description |
|-------|-----------|--------|-------------|
| 1 | **Identity Model** | [IMPLEMENTED] | PostgreSQL core schemas |
| 2 | **JWT / JWKS** | [IMPLEMENTED] | RS256/ES256 signing engine |
| 3 | **Passkeys** | [IMPLEMENTED] | WebAuthn registration/auth |
| 4 | **Social Login** | [IMPLEMENTED] | Google, Apple, GitHub OIDC |
| 5 | **OIDC Provider** | [IMPLEMENTED] | Butler as IDP for Tools |
| 6 | **Account Switch** | [STUB] | State isolation and sync |

---

## 1. Service Overview

### 1.1 Purpose
The Auth service is Butler's **identity, authentication, session issuance, assurance, and token lifecycle platform**. It manages Butler accounts, linked identities, passkeys, session families, device-aware auth state, step-up authentication, and future delegated auth readiness for tools and external service connections.

### 1.2 Responsibilities
- Butler account and identity lifecycle
- authentication methods: passkeys, OAuth/OIDC, password, magic link, TOTP fallback
- access token, refresh token, and session issuance
- asymmetric signing and JWKS publication
- refresh token family rotation and replay detection
- multi-device and multi-account session management
- auth assurance levels and step-up auth
- linked identities and account switching
- logout and revocation propagation
- account recovery and security-sensitive reauthentication
- delegated auth readiness for future tool and ACP/browser flows

### 1.3 Boundaries
- Owns identity/session domain schema and lifecycle
- Persists through shared data platform adapters, but does **not** own profile, memory, or business-domain data
- Does NOT enforce final authorization policy (Security/Policy layer does that)
- Does NOT execute business actions or tool calls
- Does NOT reuse user JWTs as internal workload identity
- Does NOT allow imported Hermes code to define Butler identity semantics

### 1.4 Dependencies
- PostgreSQL (accounts, identities, sessions, token families, devices, passkeys)
- Redis (hot session cache, short-lived auth state, challenges, replay/risk cache)
- `webauthn` library (Passkeys/FIDO2)
- `authlib` library (Async OIDC/OAuth 2.1 Provider Implementation)
- Email / notification provider (magic link, recovery notifications)

### 1.5 Hermes Library Integration
Auth is **not** the main consumer of Hermes, but it may reuse selective compatibility helpers behind Butler-owned auth contracts.

**Allowed Hermes reference inputs:**
- `backend/integrations/hermes/agent/credential_pool.py` for provider credential handling patterns
- `backend/integrations/hermes/acp_adapter/auth.py` and `permissions.py` for future ACP compatibility

**Auth still owns:**
- Butler account identity
- passkey and password flows
- token and session issuance
- assurance levels and step-up semantics
- linked identity lifecycle
- delegated auth readiness model

See `docs/services/hermes-library-map.md` for the complete mapping.

### 1.6 Clear Separation: Auth vs Security

| Aspect | Auth Service | Security Service |
|--------|--------------|------------------|
| Identity | Butler accounts, credentials, linked identities | - |
| Sessions | creates, rotates, revokes, tracks assurance | monitors anomalies, consumes session risk signals |
| Claims | roles, scopes, auth method refs, assurance claims | uses claims for policy decisions |
| Permissions | may define default claim vocabulary | enforces authorization policy |
| Threat response | session invalidation, step-up, recovery lockouts | threat detection, abuse controls, blocking |

---

## 2. Identity Model

### 2.1 Core Concepts

| Concept | Meaning |
|---------|---------|
| Butler Account | primary principal in Butler |
| Identity | one login method linked to an account |
| Session | one active authenticated context per account/device/client |
| Device | client device metadata and trust state |
| Token Family | rotating refresh-token chain bound to a session |
| Active Account | currently selected principal on a multi-account client |

### 2.2 Multi-Account and Linked Identity Rules
- One Butler account may have multiple linked identities.
- One client may keep multiple signed-in Butler accounts.
- Every request must carry active account context.
- Account switching must not leak sessions, caches, or data across accounts.
- Linked identities can include password credentials, passkeys, Google, Apple, GitHub, and future enterprise identities.

### 2.3 Identity Types
- password credential
- passkey / WebAuthn credential set
- Google OIDC identity
- Apple identity
- GitHub identity
- magic-link recovery identity
- future delegated external-service identity

---

## 3. Authentication Methods

### 3.1 Method Priority

Preferred hierarchy for Butler:
1. passkeys / WebAuthn
2. OAuth / social sign-in
3. password + TOTP
4. magic link for fallback and recovery
5. recovery codes + support-assisted recovery path

### 3.2 Password Authentication

```python
from argon2 import PasswordHasher

class PasswordAuth:
    def __init__(self, user_repo, session_manager, risk_engine):
        self.user_repo = user_repo
        self.session_manager = session_manager
        self.risk_engine = risk_engine
        self.password_hasher = PasswordHasher()

    def verify_password(self, password: str, password_hash: str) -> bool:
        try:
            self.password_hasher.verify(password_hash, password)
            return True
        except Exception:
            return False

    def hash_password(self, password: str) -> str:
        return self.password_hasher.hash(password)
```

### 3.3 Passkeys / WebAuthn (First-Class)

Passkeys are a primary Butler auth method, not a postscript.

Support requirements:
- registration ceremony
- authentication ceremony
- discoverable credentials
- synced passkeys and device-bound passkeys
- credential metadata and trust state
- recovery fallback path

```python
class PasskeyAuth:
    async def begin_registration(self, account_id: str, device_info: dict) -> dict:
        challenge = self.challenge_service.issue("webauthn.register", account_id)
        return {
            "challenge": challenge,
            "rp": {"name": "Butler AI", "id": "butler.lasmoid.ai"},
            "user": {"id": account_id, "name": "user@masked"},
            "residentKey": "required",
            "userVerification": "preferred",
        }

    async def verify_registration(self, account_id: str, ceremony_result: dict) -> dict:
        # Verify challenge, origin, attestation / public key, sign counter
        return {"registered": True}

    async def begin_authentication(self, account_hint: str | None = None) -> dict:
        challenge = self.challenge_service.issue("webauthn.authenticate", account_hint)
        return {
            "challenge": challenge,
            "userVerification": "preferred",
            "allowCredentials": [],
        }

    async def verify_authentication(self, ceremony_result: dict, device_info: dict) -> "AuthResult":
        # Verify assertion, sign count, origin, rpId, challenge
        return await self.session_manager.create_interactive_session(...)
```

### 3.4 OpenID Connect (OIDC) Provider / Sign-In

Butler is an **OIDC Identity Provider** backed by `authlib`.
Public clients connecting to Butler must use **Authorization Code + PKCE (S256)**.

```yaml
providers:
  google:
    flow: authorization_code_pkce
    scopes: [openid, email, profile]
  apple:
    flow: authorization_code_pkce
    scopes: [name, email]
  github:
    flow: authorization_code_pkce
    scopes: [read:user, user:email]
```

Rules:
- no implicit flow
- exact redirect URI matching
- `S256` PKCE only
- no token delivery in browser fragments for Butler-native clients
- loopback/custom URI handling is client-type specific

### 3.5 Magic Link Authentication
Magic links remain valid as low-friction fallback and recovery path, but they are not Butler's flagship passwordless method.

### 3.6 Two-Factor / Backup Methods
- TOTP
- recovery codes
- recent-password reauth where required
- optional trusted-device lift when policy allows

---

## 4. Assurance Levels and Step-Up Auth

### 4.1 Internal Assurance Model

| Level | Meaning | Typical methods |
|------|---------|-----------------|
| `AAL1` | low assurance | password, magic link, basic social login |
| `AAL2` | strong user auth | TOTP, passkey, verified device |
| `AAL3-ish` | Butler high assurance | device-bound passkey + recent reauth + trusted device + clean risk state |

### 4.2 Step-Up Triggers
- new device
- new region or risky network
- account linking or unlinking
- session-family replay anomaly
- credential export / recovery changes
- high-sensitivity automation approval
- delegated auth creation for tools and external services

### 4.3 Step-Up Flow

```python
class StepUpManager:
    async def request_step_up(self, session_id: str, reason: str) -> dict:
        return {
            "step_up_required": True,
            "allowed_methods": ["passkey", "totp"],
            "reason": reason,
        }

    async def verify_step_up(self, session_id: str, method: str, payload: dict) -> dict:
        return {"elevated": True, "acr": "AAL2"}
```

---

## 5. Token Architecture

### 5.1 Token Types
- access token
- refresh token
- ID token (when acting in OIDC-compatible patterns)
- optional device-bound session token
- future delegation token for external tool/service auth

### 5.2 Signing Strategy
Use **asymmetric signing only** for Butler-issued tokens.

Requirements:
- RS256 or ES256
- JWKS endpoint with `kid`
- per-environment signing keys
- rotation schedule and grace period
- strict algorithm allowlist verification

```python
class SigningKeyStore:
    def active_signing_key(self, token_type: str) -> "SigningKey": ...
    def jwks_document(self) -> dict: ...

class TokenManager:
    def create_access_token(self, claims: dict, signing_key: "SigningKey") -> str:
        # Sign with RS256/ES256 and include kid
        ...
```

### 5.3 Access Token Claims

```json
{
  "sub": "usr_123",
  "sid": "ses_456",
  "aid": "acct_789",
  "amr": ["passkey"],
  "acr": "AAL2",
  "scope": "chat tools:read",
  "device_id": "dev_abc",
  "jti": "tok_xyz",
  "iss": "https://auth.butler.lasmoid.ai",
  "aud": "butler-gateway",
  "exp": 1713420000
}
```

### 5.4 Refresh Token Families

Refresh tokens belong to a **token family**.

Tracked fields:
- `session_id`
- `token_family_id`
- `parent_token_id`
- `rotation_counter`
- `device_id`
- `client_type`

Rules:
- every refresh rotates the token
- previous token is invalidated immediately
- reuse of an invalidated refresh token triggers replay detection
- suspicious replay revokes the whole token family or session branch

```python
class RefreshFamilyManager:
    async def rotate(self, family_id: str, current_jti: str, device_id: str) -> dict:
        # Atomically mark old token spent, mint new child token, increment rotation counter
        ...

    async def handle_replay(self, family_id: str, used_jti: str) -> None:
        # Revoke family and raise risk signal
        ...
```

---

## 6. Session Architecture

### 6.1 Session Classes
- `interactive_user_session`
- `background_refresh_session`
- `tool_delegation_session`
- `high_assurance_session`

### 6.2 Session Fields

```json
{
  "session_id": "ses_123",
  "account_id": "acct_123",
  "device_id": "dev_456",
  "client_id": "mobile_ios",
  "auth_method": "passkey",
  "assurance_level": "AAL2",
  "created_at": "...",
  "last_seen_at": "...",
  "idle_timeout": 86400,
  "absolute_expiry": "...",
  "refresh_family_id": "fam_789",
  "trusted_device": true,
  "risk_state": "clean"
}
```

### 6.3 Storage Model
- **PostgreSQL:** source of truth for accounts, identities, devices, sessions, token families, passkeys, recovery state
- **Redis:** hot session cache, challenge storage, short-lived auth state, replay/lockout cache, risk cache

### 6.4 Multi-Account Clients
- one client may hold multiple active Butler accounts
- one selected account is the active account context
- account switch is explicit and auditable

---

## 7. Linked Identities and Account Switching

### 7.1 Linked Identity Model

```sql
CREATE TABLE account_identities (
    id UUID PRIMARY KEY,
    account_id UUID NOT NULL,
    provider VARCHAR(32) NOT NULL,
    provider_subject TEXT NOT NULL,
    email TEXT,
    email_verified BOOLEAN,
    created_at TIMESTAMP NOT NULL,
    UNIQUE(provider, provider_subject)
);
```

### 7.2 Passkey Credential Model

```sql
CREATE TABLE passkey_credentials (
    id UUID PRIMARY KEY,
    account_id UUID NOT NULL,
    credential_id TEXT NOT NULL UNIQUE,
    public_key BYTEA NOT NULL,
    sign_count BIGINT,
    transports TEXT[],
    device_bound BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL,
    last_used_at TIMESTAMP,
    nickname TEXT
);
```

### 7.3 Switching Rules
- account switch requires explicit active account selection
- session caches are isolated by account
- linked-identity operations may trigger step-up auth

---

## 8. Logout, Revocation, and Recovery

### 8.1 Logout Modes
- local logout
- current-device logout
- all-device logout
- admin revocation
- token-family revocation
- future back-channel logout for relying parties / integrations

### 8.2 Back-Channel Logout Readiness
Butler should remain compatible with OIDC-style back-channel logout patterns for integrated relying parties or enterprise partners later.

### 8.3 Recovery Model
- recovery codes
- verified email recovery
- verified passkey recovery
- trusted-device assisted recovery
- cooldowns for sensitive changes
- session invalidation after recovery
- recent reauthentication for sensitive identity changes

---

## 9. Risk Engine Inputs

### 9.1 Risk Signals
- failed login rate
- ASN / network novelty
- geo novelty
- impossible travel
- new device
- emulator / rooted-device hints
- refresh token replay
- passkey ceremony anomaly
- session-switch anomaly
- future tool delegation anomaly

### 9.2 Outcomes
- allow
- allow with step-up
- challenge
- block
- quarantine session

Auth owns the session and assurance reaction. Security owns broader detection policy and cross-service threat enforcement.

---

## 10. API Contracts (Implemented)

### 10.1 Core Auth & OIDC
```yaml
POST /auth/register
POST /auth/login
POST /auth/refresh
POST /auth/logout
POST /auth/logout/all
GET  /.well-known/jwks.json
GET  /.well-known/openid-configuration
POST /auth/authorize
POST /auth/token
GET  /auth/userinfo
```

### 10.2 Passkeys (WebAuthn)
```yaml
POST /auth/passkeys/register/options
POST /auth/passkeys/register/verify
POST /auth/passkeys/login/options
POST /auth/passkeys/login/verify
```

### 10.3 Multi-Account Context & Sessions
```yaml
GET    /auth/accounts
POST   /auth/accounts
GET    /auth/sessions
DELETE /auth/sessions/{session_id}
```

### 10.4 Recovery & Lifecycle (High-Risk)
```yaml
POST /auth/reauth
POST /auth/password/reset/initiate
POST /auth/password/reset/confirm
POST /auth/recovery/codes
POST /auth/recovery/redeem
```

---

## 11. Security Notes

### 11.1 Password Security

```python
PASSWORD_CONFIG = {
    "min_length": 8,
    "require_uppercase": True,
    "require_lowercase": True,
    "require_digit": True,
    "require_special": False,
    "hashing_algorithm": "argon2id",
    "max_length": 128,
    "common_passwords_file": "common_passwords.txt",
}
```

### 11.2 JWT / Token Validation Rules
- verify `iss`, `aud`, `exp`, `nbf`, `jti`, and `kid`
- reject non-allowlisted algorithms
- no `HS256` shared-secret production design
- support JWKS caching with bounded TTL

### 11.3 Public Client Rules
- PKCE required
- exact redirect URI matching
- no implicit flow
- no silent trust in public-client secrets

---

## 12. Testing Strategy

### 12.1 Required Tests
- passkey registration and authentication ceremonies
- PKCE validation for public clients
- JWKS verification and key rotation
- refresh family rotation and replay detection
- multi-account switch isolation
- step-up auth escalation
- logout and revocation propagation
- recovery and recent-reauth flows

### 12.2 Integration Expectations
- current-device logout invalidates only the right session
- all-device logout revokes all active session families
- linked identity flows remain account-safe
- risk escalation can force step-up without losing account context

---

*Document owner: Auth Team*  
*Last updated: 2026-04-19*  
*Version: 3.0 (Production Ready)*
