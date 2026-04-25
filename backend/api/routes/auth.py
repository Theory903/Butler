"""Auth routes — thin HTTP layer, no business logic.

All work is delegated to AuthService.
Errors flow up as Problem exceptions and are handled by the global handler.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.auth import (
    AccountResponse,
    CreateAccountRequest,
    IdentityContextResponse,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetInitiateRequest,
    PrincipalResponse,
    ReauthRequest,
    ReauthResponse,
    RecoveryCodesResponse,
    RedeemRecoveryCodeRequest,
    RefreshTokenRequest,
    RegisterRequest,
    SessionInfo,
    TokenResponse,
    WebAuthnLoginRequest,
    WebAuthnLoginVerifyRequest,
    WebAuthnRegistrationVerifyRequest,
)
from core.deps import get_cache, get_db
from core.errors import Problem
from services.auth.jwt import get_jwks_manager
from services.auth.password import PasswordService
from services.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

_password_service = PasswordService()  # Stateless, safe to share


def _get_auth_service(
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_cache),
) -> AuthService:
    """Build AuthService with dependencies injected."""
    return AuthService(
        db=db,
        redis=cache,
        jwks=get_jwks_manager(),
        passwords=_password_service,
    )


async def get_current_sid(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise Problem(type="missing-authorization", title="Authorization Required", status=401)
    token = authorization[7:]
    # verify_token is now internal to AuthService or can be used via jwks directly for fast path
    claims = get_jwks_manager().verify_token(token)
    return claims["sid"]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    req: RegisterRequest,
    auth: AuthService = Depends(_get_auth_service),
) -> TokenResponse:
    """Register a new account and receive tokens."""
    tokens = await auth.register(req.email, req.password, req.display_name)
    return TokenResponse(**asdict(tokens))


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    request: Request,
    auth: AuthService = Depends(_get_auth_service),
) -> TokenResponse:
    """Authenticate with email + password."""
    tokens = await auth.login(
        email=req.email,
        password=req.password,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        device_id=request.headers.get("X-Device-ID"),
    )
    return TokenResponse(**asdict(tokens))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    req: RefreshTokenRequest,
    auth: AuthService = Depends(_get_auth_service),
) -> TokenResponse:
    """Rotate refresh token and get a new token pair."""
    tokens = await auth.refresh_token(req.refresh_token)
    return TokenResponse(**asdict(tokens))


@router.post("/logout", status_code=204)
async def logout(
    sid: str = Depends(get_current_sid),
    auth: AuthService = Depends(_get_auth_service),
) -> None:
    """Revoke the current session."""
    await auth.logout(sid)


@router.post("/switch", response_model=TokenResponse)
async def switch_account(
    target_aid: str,
    auth: AuthService = Depends(_get_auth_service),
    sid: str = Depends(get_current_sid),
) -> TokenResponse:
    """Switch active account context."""
    tokens = await auth.switch_account(sid, target_aid)
    return TokenResponse(**asdict(tokens))


@router.get("/.well-known/jwks.json", include_in_schema=True)
async def jwks(
    auth: AuthService = Depends(_get_auth_service),
) -> dict:
    """RFC 7517 JWKS document — public keys for JWT verification."""
    return await auth.get_jwks()


@router.get("/me", response_model=IdentityContextResponse)
async def me(
    sid: str = Depends(get_current_sid),
    auth: AuthService = Depends(_get_auth_service),
) -> IdentityContextResponse:
    """Get current account info."""
    ctx = await auth.get_context(sid)
    if not ctx:
        raise Problem(type="session-invalid", title="Session Invalid", status=401)

    principal = await auth.get_principal(ctx.sub)
    account = await auth.get_account(ctx.aid) if ctx.aid else None

    return IdentityContextResponse(
        principal=PrincipalResponse(**principal),
        active_account=AccountResponse(**account) if account else None,
    )


# ── WebAuthn (Passkeys) ───────────────────────────────────────────────────


@router.post("/passkey/register/options")
async def register_passkey_options(
    sid: str = Depends(get_current_sid),
    auth: AuthService = Depends(_get_auth_service),
) -> dict:
    """Generate options for registering a new passkey."""
    ctx = await auth.get_context(sid)
    if not ctx:
        raise Problem(type="session-invalid", title="Session Invalid", status=401)
    return await auth.generate_registration_options(ctx.sub)


@router.post("/passkey/register/verify", status_code=204)
async def register_passkey_verify(
    req: WebAuthnRegistrationVerifyRequest,
    sid: str = Depends(get_current_sid),
    auth: AuthService = Depends(_get_auth_service),
) -> None:
    """Verify and store a new passkey."""
    ctx = await auth.get_context(sid)
    if not ctx:
        raise Problem(type="session-invalid", title="Session Invalid", status=401)

    success = await auth.verify_registration(ctx.sub, req.challenge, req.response)
    if not success:
        raise Problem(type="webauthn-failed", title="Passkey Registration Failed", status=400)


@router.post("/passkey/login/options")
async def login_passkey_options(
    req: WebAuthnLoginRequest,
    auth: AuthService = Depends(_get_auth_service),
) -> dict:
    """Generate options for passkey authentication (login)."""
    return await auth.generate_authentication_options(req.email)


@router.post("/passkey/login/verify", response_model=TokenResponse)
async def login_passkey_verify(
    req: WebAuthnLoginVerifyRequest,
    request: Request,
    auth: AuthService = Depends(_get_auth_service),
) -> TokenResponse:
    """Verify passkey assertion and issue tokens."""
    tokens = await auth.verify_authentication(
        challenge=req.challenge,
        response=req.response,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        device_id=request.headers.get("X-Device-ID"),
    )
    return TokenResponse(**asdict(tokens))


# ── OIDC / OAuth 2.1 ───────────────────────────────────────────────────────


@router.get("/.well-known/openid-configuration", include_in_schema=True)
async def oidc_discovery():
    """OIDC Discovery endpoint."""
    from infrastructure.config import settings
    from services.auth.oidc import get_oidc_discovery

    return get_oidc_discovery(settings.JWT_ISSUER)


@router.get("/authorize")
@router.post("/authorize")
async def authorize(
    request: Request,
    auth: AuthService = Depends(_get_auth_service),
    db: AsyncSession = Depends(get_db),
):
    """Handle OIDC authorization request."""
    from services.auth.oidc import create_oidc_server

    server = create_oidc_server(db, auth._jwks)

    # This is a stub for the consent screen.
    # In a real app, we'd render a page here if logged in, or redirect to login.
    # For now, we assume Butler's single-tenant or auto-consent for demo.
    return await server.create_authorization_response(request, grant_user=None)


@router.post("/token")
async def token_endpoint(
    request: Request,
    auth: AuthService = Depends(_get_auth_service),
    db: AsyncSession = Depends(get_db),
):
    """Handle OAuth token exchange."""
    from services.auth.oidc import create_oidc_server

    server = create_oidc_server(db, auth._jwks)
    return await server.create_token_response(request)


@router.get("/userinfo")
async def userinfo(
    sid: str = Depends(get_current_sid),
    auth: AuthService = Depends(_get_auth_service),
):
    """OIDC UserInfo endpoint."""
    ctx = await auth.get_context(sid)
    if not ctx:
        raise Problem(type="session-invalid", title="Session Invalid", status=401)

    principal = await auth.get_principal(ctx.sub)
    return {
        "sub": str(principal["id"]),
        "email": principal["email"],
        "email_verified": True,
        "name": principal.get("name", principal["email"]),
    }


# ── Phase 4: Multi-Account & Session Management ───────────────────────────────


@router.get("/accounts", response_model=list[AccountResponse])
async def list_accounts(
    sid: str = Depends(get_current_sid),
    auth: AuthService = Depends(_get_auth_service),
) -> list[AccountResponse]:
    """List all account contexts under the current principal."""
    ctx = await auth.get_context(sid)
    if not ctx:
        raise Problem(type="session-invalid", title="Session Invalid", status=401)
    accounts = await auth.list_accounts(ctx.sub)
    return [AccountResponse(**a) for a in accounts]


@router.post("/accounts", response_model=AccountResponse, status_code=201)
async def create_account(
    req: CreateAccountRequest,
    sid: str = Depends(get_current_sid),
    auth: AuthService = Depends(_get_auth_service),
) -> AccountResponse:
    """Create a new account context under the current principal."""
    ctx = await auth.get_context(sid)
    if not ctx:
        raise Problem(type="session-invalid", title="Session Invalid", status=401)
    account = await auth.create_account(ctx.sub, req.name)
    return AccountResponse(**account)


@router.get("/sessions", response_model=list[SessionInfo])
async def list_sessions(
    sid: str = Depends(get_current_sid),
    auth: AuthService = Depends(_get_auth_service),
) -> list[SessionInfo]:
    """List all active sessions for the current principal (device management)."""
    ctx = await auth.get_context(sid)
    if not ctx:
        raise Problem(type="session-invalid", title="Session Invalid", status=401)
    sessions = await auth.list_sessions(ctx.sub)
    return [SessionInfo(**s) for s in sessions]


@router.delete("/sessions/{target_sid}", status_code=204)
async def revoke_session(
    target_sid: str,
    sid: str = Depends(get_current_sid),
    auth: AuthService = Depends(_get_auth_service),
) -> None:
    """Revoke a specific session by ID (remote logout / device management)."""
    ctx = await auth.get_context(sid)
    if not ctx:
        raise Problem(type="session-invalid", title="Session Invalid", status=401)
    ok = await auth.revoke_session(ctx.sub, target_sid)
    if not ok:
        raise Problem(type="session-not-found", title="Session Not Found", status=404)


# ── Phase 5: Recovery & Lifecycle ─────────────────────────────────────────────


@router.post("/reauth", response_model=ReauthResponse)
async def reauth(
    req: ReauthRequest,
    sid: str = Depends(get_current_sid),
    auth: AuthService = Depends(_get_auth_service),
) -> ReauthResponse:
    """Step-up reauthentication — elevates current session to AAL2 for 15 minutes."""
    verified = await auth.reauthenticate(sid, req.password)
    if not verified:
        raise Problem(type="reauth-failed", title="Reauthentication Failed", status=401)
    return ReauthResponse(verified=True)


@router.post("/recovery/codes", response_model=RecoveryCodesResponse)
async def generate_recovery_codes(
    sid: str = Depends(get_current_sid),
    auth: AuthService = Depends(_get_auth_service),
) -> RecoveryCodesResponse:
    """Generate 10 new recovery codes (requires step-up/AAL2). Invalidates previous codes."""
    ctx = await auth.get_context(sid)
    if not ctx:
        raise Problem(type="session-invalid", title="Session Invalid", status=401)
    codes = await auth.generate_recovery_codes(ctx.sub, sid)
    return RecoveryCodesResponse(codes=codes)


@router.post("/recovery/redeem", response_model=TokenResponse)
async def redeem_recovery_code(
    req: RedeemRecoveryCodeRequest,
    auth: AuthService = Depends(_get_auth_service),
) -> TokenResponse:
    """Exchange a valid recovery code for a session."""
    tokens = await auth.redeem_recovery_code(req.email, req.code)
    return TokenResponse(**asdict(tokens))


@router.post("/password/reset/initiate", status_code=202)
async def initiate_password_reset(
    req: PasswordResetInitiateRequest,
    auth: AuthService = Depends(_get_auth_service),
) -> dict:
    """Initiate password reset flow. Always returns 202 (no email enumeration)."""
    await auth.initiate_password_reset(req.email)
    return {"message": "If an account exists, a reset email has been sent."}


@router.post("/password/reset/confirm", status_code=204)
async def confirm_password_reset(
    req: PasswordResetConfirmRequest,
    auth: AuthService = Depends(_get_auth_service),
) -> None:
    """Confirm password reset with token. Revokes all active sessions."""
    ok = await auth.confirm_password_reset(req.token, req.new_password)
    if not ok:
        raise Problem(
            type="reset-token-invalid",
            title="Reset Token Invalid or Expired",
            status=400,
        )
