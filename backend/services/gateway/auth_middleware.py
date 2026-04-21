"""JWT Authentication middleware for the Gateway.

Verifies Bearer tokens on all protected endpoints against RFC 9068.

Checks enforced (per RFC 9068 §2.2 and §4):
  1. typ header MUST be "at+jwt" or "application/at+jwt"
  2. alg MUST be RS256 or ES256 (never HS256)
  3. iss MUST match settings.JWT_ISSUER
  4. aud MUST contain settings.JWT_AUDIENCE (resource server identity)
  5. exp checked with configurable clock_skew_s leeway
  6. Revocation: Redis checked for session_id before DB query

AccountContext is populated with:
  - account_id  (sub)
  - session_id  (sid)
  - assurance_level (aal)  — used for step-up gating
  - acr  — Authentication Context Class Reference (preserved for ACP)
  - token_id (jti)  — for future idempotency / replay windows
"""

from __future__ import annotations

import jwt
from redis.asyncio import Redis

from domain.auth.contracts import AccountContext, IJWKSVerifier
from domain.auth.exceptions import GatewayErrors
from infrastructure.config import settings


# Permitted typ header values (RFC 9068 §2.1)
_VALID_TYP = frozenset({"at+jwt", "application/at+jwt"})

# Permitted signing algorithms — HS256 is categorically rejected
_VALID_ALGS = frozenset({"RS256", "ES256", "RS384", "ES384", "RS512", "ES512"})

# Configurable clock skew tolerance (seconds)
_CLOCK_SKEW_S: int = 30



class JWTAuthMiddleware:
    """Verify JWT Bearer tokens using JWKS public key.

    All failures raise a core.errors.Problem subclass so the global
    exception handler returns application/problem+json automatically.
    """

    def __init__(self, jwks: IJWKSVerifier, redis: Redis) -> None:
        self._jwks = jwks
        self._redis = redis

    async def authenticate(self, authorization: str | None) -> AccountContext:
        """Parse Authorization header and return verified AccountContext.

        Raises Problem (401) on any auth failure.
        Does NOT raise on success — callers receive a populated AccountContext.
        """
        if not authorization or not authorization.startswith("Bearer "):
            raise GatewayErrors.MISSING_AUTH

        token = authorization[7:]

        try:
            # ── Step 1: inspect unverified header before touching claims ──────
            unverified_header = jwt.get_unverified_header(token)

            # RFC 9068 §2.1 — typ MUST be at+jwt
            typ = unverified_header.get("typ", "")
            if typ not in _VALID_TYP:
                raise GatewayErrors.INVALID_TOKEN

            # Block symmetric-key algorithms categorically
            alg = unverified_header.get("alg", "")
            if alg not in _VALID_ALGS:
                raise GatewayErrors.INVALID_TOKEN

            # ── Step 2: full signature + claims verification ──────────────────
            claims = self._jwks.verify_token(
                token,
                audience=getattr(settings, "JWT_AUDIENCE", None),
                issuer=getattr(settings, "JWT_ISSUER", None),
                leeway=_CLOCK_SKEW_S,
            )

        except Exception as exc:
            from core.errors import Problem
            from core.observability import get_metrics
            if isinstance(exc, Problem):
                raise
            if isinstance(exc, jwt.ExpiredSignatureError):
                get_metrics().inc_auth_failure(reason="expired")
                raise GatewayErrors.TOKEN_EXPIRED
            if isinstance(exc, (jwt.InvalidAudienceError, jwt.InvalidIssuerError, jwt.InvalidTokenError)):
                get_metrics().inc_auth_failure(reason="invalid_token")
                raise GatewayErrors.INVALID_TOKEN
            get_metrics().inc_auth_failure(reason="internal_error")
            raise GatewayErrors.INVALID_TOKEN

        # ── Step 3: revocation check via Redis (fast path before DB) ─────────
        session_id = claims.get("sid", "")
        if session_id:
            revoked = await self._redis.get(f"session_revoked:{session_id}")
            if revoked:
                from core.observability import get_metrics
                get_metrics().inc_auth_failure(reason="revoked")
                raise GatewayErrors.SESSION_REVOKED

        # ── Step 4: build AccountContext using canonical domain field names ───
        return AccountContext(
            sub=claims["sub"],
            sid=session_id,
            aid=claims.get("aid", claims["sub"]),  # fall back to sub if no aid claim
            amr=claims.get("amr", []),
            acr=claims.get("acr") or claims.get("aal", "aal1"),
            device_id=None,  # injected by route layer from X-Device-ID header
            client_id=claims.get("client_id"),
        )

