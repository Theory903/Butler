# Butler Auth & Identity Service

This package implements the **Identity Platform (v2.0)** for Butler, moving beyond basic email/password auth into a full-featured identity, multi-account, and delegated-auth provider.

> **Full Technical Spec:** [`../../../docs/02-services/auth.md`](../../../docs/02-services/auth.md)

## 🏗 Architecture & Modules

The Auth service follows Butler's strict semantic boundaries. It operates on `Principal` (human identity) and `Account` (business/data context) entities.

*   **`service.py`**: The main `AuthService` facade. It implements device management, account context switching, token lifecycles, passkey registration/login ceremonies (via WebAuthn), and recovery lifecycles.
*   **`oidc.py`**: A compliant OpenID Connect Authorization Server built on `authlib`. This handles PKCE-secured Authorization Code Grants for public clients linking into Butler.
*   **`jwt.py`**: Handles asymmetric token mapping (RS256/ES256) and manages the dynamic `JWKSManager` to rotate verification keys securely.
*   **`password.py`**: Specialized wrapper around Argon2id for enforcing OWASP-grade credential management.
*   **`credential_pool.py`**: Manages external IdP secrets and delegation contexts natively.
*   **`routes.py`**: Additional internal sub-routing. (Note: Most HTTP controllers are kept intentionally thin inside `backend/api/routes/auth.py`).

## ✨ Key Features
1.  **Passkeys / WebAuthn:** First-class secure hardware/biometric authentication utilizing redis-backed challenges.
2.  **OIDC Provider:** Fully supports `/.well-known/openid-configuration` with strict S256 PKCE enforcement.
3.  **Strict Semantic Divergence:** A single principal (`sub`) can own and switch between multiple account contexts (`aid`), maintaining strict cache/session isolation.
4.  **Assurance Escalation:** Sensitive actions (like `regenerate_recovery_codes`) require raising the session's Assurance Level to `aal2` via step-up reauthentication.
5.  **Blast-Radius Control:** Security events (like Password Resets) automatically invalidate `TokenFamilies` breadth-first and blacklist Active Sessions via Redis.

## 🛠 Dependencies
*   `webauthn` - For FIDO2/Passkey ceremonies.
*   `authlib` - For Async OIDC/OAuth 2.1 Provider implementation.
*   `passlib[argon2]` - For at-rest password and recovery code hashing.

## 🧪 Common Operations

**Step-up Authentication (Reauth)**
```python
# Elevate a session to AAL2 to perform a sensitive action
verified = await auth_service.reauthenticate(session_id, password)
if verified:
    codes = await auth_service.generate_recovery_codes(principal_id, session_id)
```

**Context Tracking**
```python
# Contexts hold both the human (Principal) and the active scope (Account)
ctx = await auth_service.get_context(session_id)
print(f"Human: {ctx.sub}, Scope: {ctx.aid}")
```
