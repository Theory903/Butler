"""Auth API schemas — Pydantic request/response DTOs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

# ── Requests ──────────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128, description="Minimum 8 characters")
    display_name: str | None = Field(None, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LogoutAllRequest(BaseModel):
    """Optional body — or can be called without body."""


# ── WebAuthn / Passkeys ───────────────────────────────────────────────────────


class WebAuthnRegistrationVerifyRequest(BaseModel):
    challenge: str
    response: dict  # The AuthenticatorAttestationResponse


class WebAuthnLoginRequest(BaseModel):
    email: EmailStr | None = None


class WebAuthnLoginVerifyRequest(BaseModel):
    challenge: str
    response: dict  # The AuthenticatorAssertionResponse


# ── Responses ─────────────────────────────────────────────────────────────────


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = Field(description="Access token TTL in seconds")


class PrincipalResponse(BaseModel):
    id: str
    email: str
    status: str
    created_at: datetime


class AccountResponse(BaseModel):
    id: str
    principal_id: str
    name: str
    settings: dict
    created_at: datetime


class IdentityContextResponse(BaseModel):
    principal: PrincipalResponse
    active_account: AccountResponse | None


# ── Phase 4: Multi-Account ────────────────────────────────────────────────────


class CreateAccountRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class SessionInfo(BaseModel):
    id: str
    auth_method: str
    assurance_level: str
    ip_address: str | None
    user_agent: str | None
    device_id: str | None
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime


# ── Phase 5: Recovery & Lifecycle ─────────────────────────────────────────────


class PasswordResetInitiateRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class RecoveryCodesResponse(BaseModel):
    codes: list[str]
    warning: str = "Store these codes securely. They cannot be shown again."


class RedeemRecoveryCodeRequest(BaseModel):
    email: EmailStr
    code: str


class ReauthRequest(BaseModel):
    password: str


class ReauthResponse(BaseModel):
    verified: bool
    acr: str = "aal2"
