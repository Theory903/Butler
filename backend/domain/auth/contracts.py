"""Auth service contracts — domain interface.

Defines WHAT the auth service can do.
Implementation lives in services/auth/service.py.

Rule: This file must NOT import FastAPI, Starlette, or HTTP concerns.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from domain.base import DomainService


@dataclass(frozen=True)
class TokenPair:
    """Issued token pair from a successful auth operation."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 900  # 15 min in seconds


@dataclass(frozen=True)
class AccountContext:
    """Authenticated context — passed through every request.
    
    sub: The stable subject/principal ID (Identity Owner).
    sid: The stable session ID.
    aid: The selected Active Account ID (Context).
    amr: Authentication Methods Reference (e.g. ["pwd", "webauthn"]).
    acr: Authentication Assurance Level (e.g. "aal1", "aal2").
    """

    sub: str
    sid: str
    aid: str
    amr: list[str]
    acr: str
    device_id: str | None = None
    client_id: str | None = None

    # ── Gateway-layer aliases ────────────────────────────────────────────────
    # The gateway uses friendly names; these properties bridge to the OIDC
    # field names on the domain object without forking the data model.

    @property
    def account_id(self) -> str:
        """Alias for sub (stable principal identifier)."""
        return self.sub

    @property
    def session_id(self) -> str:
        """Alias for sid (stable session identifier)."""
        return self.sid

    @property
    def assurance_level(self) -> str:
        """Alias for acr (Authentication Context Class Reference)."""
        return self.acr

    @property
    def token_id(self) -> str | None:
        """jti — not stored on domain but referenced in gateway. Returns None."""
        return None



class AuthServiceContract(DomainService, ABC):
    """Auth domain service interface."""

    @abstractmethod
    async def register(
        self,
        email: str,
        password: str,
        display_name: str | None = None,
    ) -> TokenPair:
        """Create principal + password identity + session."""

    @abstractmethod
    async def login(
        self,
        email: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_id: str | None = None,
        client_id: str | None = None,
    ) -> TokenPair:
        """Authenticate by email/password. Returns token pair."""

    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> TokenPair:
        """Rotate refresh token. Detect reuse and revoke family on compromise."""

    @abstractmethod
    async def logout(self, session_id: str) -> None:
        """Revoke session and mark cached revocation in Redis."""

    @abstractmethod
    async def logout_all(self, sub: str) -> int:
        """Revoke ALL sessions for a principal."""

    @abstractmethod
    async def verify_token(self, token: str) -> dict:
        """Verify JWT signature and return claims dict."""

    @abstractmethod
    async def switch_account(self, session_id: str, target_account_id: str) -> TokenPair:
        """Switch the active account (aid) context for an existing session."""

    @abstractmethod
    async def reauthenticate(self, session_id: str, password: str) -> str:
        """Verify password to upgrade ACR for a sensitive operation (step-up)."""

    @abstractmethod
    async def generate_registration_options(self, principal_id: str) -> dict:
        """Create WebAuthn challenge for new passkey registration."""

    @abstractmethod
    async def verify_registration(
        self, principal_id: str, challenge: str, response: dict
    ) -> bool:
        """Verify WebAuthn attestation and store credential."""

    @abstractmethod
    async def generate_authentication_options(self, email: str | None = None) -> dict:
        """Create WebAuthn challenge for passkey login."""

    @abstractmethod
    async def verify_authentication(
        self, 
        challenge: str, 
        response: dict,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_id: str | None = None,
    ) -> TokenPair:
        """Verify WebAuthn assertion and issue tokens."""

    @abstractmethod
    async def get_jwks(self) -> dict:
        """Return RFC 7517 JWKS document."""

    @abstractmethod
    async def get_account(self, account_id: str) -> dict | None:
        """Get account info by ID."""

    # ── Phase 4: Multi-Account ────────────────────────────────────────────────

    @abstractmethod
    async def list_accounts(self, principal_id: str) -> list[dict]:
        """List all accounts belonging to a principal."""

    @abstractmethod
    async def create_account(self, principal_id: str, name: str) -> dict:
        """Create a new account context under a principal."""

    @abstractmethod
    async def list_sessions(self, principal_id: str) -> list[dict]:
        """List all active sessions for a principal (for device management)."""

    @abstractmethod
    async def revoke_session(self, principal_id: str, session_id: str) -> bool:
        """Revoke a specific session, verifying it belongs to the principal."""

    # ── Phase 5: Recovery & Lifecycle ─────────────────────────────────────────

    @abstractmethod
    async def initiate_password_reset(self, email: str) -> str | None:
        """Generate and store a one-time password reset token. Returns token (for email delivery)."""

    @abstractmethod
    async def confirm_password_reset(self, token: str, new_password: str) -> bool:
        """Validate reset token and update password hash. Revokes all sessions."""

    @abstractmethod
    async def generate_recovery_codes(self, principal_id: str, session_id: str) -> list[str]:
        """Generate a new set of recovery codes (invalidates prior set)."""

    @abstractmethod
    async def redeem_recovery_code(self, email: str, code: str) -> TokenPair:
        """Exchange a valid recovery code for a session (one-time use, AAL2)."""

    @abstractmethod
    async def get_principal(self, principal_id: str) -> dict | None:
        """Get principal (sub) info by ID."""


class IJWKSVerifier(ABC):
    """Abstraction over JWKSManager used by gateway/auth_middleware.py.

    The gateway middleware should depend on this interface, not on the
    concrete JWKSManager. Any JWKS-backed verifier (including test doubles
    and OIDC provider verifiers) can satisfy this contract.
    """

    @abstractmethod
    def get_public_keys(self) -> list[dict]:
        """Return the current set of JWK public keys."""

    @abstractmethod
    def verify_token(
        self,
        token: str,
        audience: str | None = None,
        issuer: str | None = None,
        leeway: int = 0,
    ) -> dict:
        """Verify a JWT and return its decoded claims.

        Raises jwt.InvalidTokenError (or subclass) on any verification failure.
        Never returns a claims dict if verification failed.
        """

    @abstractmethod
    async def rotate_keys(self) -> None:
        """Rotate JWKS — fetch fresh keys from the JWKS endpoint."""
