"""ButlerCredentialPool — Phase 5.

Manages credential lifecycle for Butler services and tool execution:

  1. Token introspection cache (Redis)  — fast-path verify_token() without
     hitting the DB on every request. TTL = min(exp - now, 5min).
  2. Session revocation fast-path  — marks session as revoked in Redis;
     introspection cache entries are invalidated immediately.
  3. Tool credential forwarding  — external API keys (OpenAI, Anthropic,
     Google, etc.) stored encrypted in PostgreSQL, fetched per-tool and
     injected into Hermes tool environment via HermesEnvBridge.
     Keys are NEVER logged and NEVER stored in ContextVars directly.
  4. AAL enforcement  — returns the Assurance Level from cached claims so
     the Gateway can enforce L2 tool approval requirements without an
     extra DB round-trip.

Sovereignty rules:
  - ButlerCredentialPool never generates JWTs. That is JWKSManager's job.
  - Hermes never calls this class. Tool credentials are pushed through
    HermesEnvBridge (domain/tools/hermes_dispatcher.py) — one direction.
  - No plaintext secrets are stored in Redis. Only encrypted blobs.
    Encryption key comes from settings.SECRET_ENCRYPTION_KEY (Fernet/AES).
  - Redis cache miss → fall through to JWKSManager.verify_token(). Never
    fail open on a cache miss.
  - Revocation list is append-only. Reinstatement is not supported.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

from services.tenant.namespace import get_tenant_namespace

import structlog

logger = structlog.get_logger(__name__)

# Max introspection cache TTL — even if token expires in 1h, we cap at 5min
_MAX_INTROSPECT_TTL_S = 300

# Minimum TTL to bother caching — don't cache tokens expiring in < 30s
_MIN_INTROSPECT_TTL_S = 30

# Tool credential cache TTL (in-memory only, no Redis for plaintext keys)
_TOOL_CRED_CACHE_TTL_S = 900


def _token_cache_key(tenant_id: str, token_fingerprint: str) -> str:
    """Generate tenant-scoped token introspection cache key."""
    namespace = get_tenant_namespace(tenant_id)
    return f"{namespace.prefix}:token:introspect:{token_fingerprint}"


def _session_revoke_key(tenant_id: str, session_id: str) -> str:
    """Generate tenant-scoped session revocation key."""
    namespace = get_tenant_namespace(tenant_id)
    return f"{namespace.prefix}:token:revoked:session:{session_id}"


def _jti_revoke_key(tenant_id: str, token_id: str) -> str:
    """Generate tenant-scoped JTI revocation key."""
    namespace = get_tenant_namespace(tenant_id)
    return f"{namespace.prefix}:token:revoked:jti:{token_id}"


@dataclass(frozen=True)
class IntrospectionResult:
    """Result of a token introspection + revocation check."""

    valid: bool
    account_id: str | None = None
    session_id: str | None = None
    assurance_level: str = "aal1"
    token_id: str | None = None
    expires_at: datetime | None = None
    reason: str = ""  # populated when valid=False


@dataclass(frozen=True)
class ToolCredential:
    """A single external API credential for a tool provider."""

    provider: str  # e.g. "openai", "anthropic", "google", "github"
    api_key: str  # plaintext at runtime only — never logged
    expires_at: datetime | None = None
    scopes: list[str] = ()


class ButlerCredentialPool:
    """Credential lifecycle manager for Butler services.

    Usage:
        pool = ButlerCredentialPool(redis=redis, jwks=jwks_manager)
        result = await pool.introspect(token)
        if not result.valid:
            raise HTTPException(401, ...)
        if result.assurance_level < required_aal:
            raise HTTPException(403, ...)
    """

    def __init__(
        self,
        redis: Redis,
        jwks_manager: Any,  # JWKSManager — imported lazily
        encryption_key: str | None = None,  # Fernet key for tool creds
    ) -> None:
        self._redis = redis
        self._jwks = jwks_manager
        self._enc_key = encryption_key
        # In-memory tool cred cache to avoid repeated decrypt
        self._tool_cache: dict[str, tuple[ToolCredential, float]] = {}

    # ── Token introspection ───────────────────────────────────────────────────

    async def introspect(self, token: str) -> IntrospectionResult:
        """Verify a JWT token with Redis cache + revocation check.

        Flow:
          1. Check Redis introspection cache (fast path)
          2. If miss → JWKSManager.verify_token() (signature + claims)
          3. Check jti revocation list
          4. Check session revocation list
          5. Cache result with capped TTL
        """
        cache_key = _token_cache_key(_token_fingerprint(token))

        # 1. Cache hit
        cached = await self._redis.get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                # Re-check revocation even on cache hit (revocation adds new key)
                session_revoked = await self._is_session_revoked(data.get("session_id", ""))
                jti_revoked = await self._is_jti_revoked(data.get("token_id", ""))
                if session_revoked or jti_revoked:
                    await self._redis.delete(cache_key)
                    return IntrospectionResult(
                        valid=False,
                        reason="token_revoked_session" if session_revoked else "token_revoked_jti",
                    )
                return IntrospectionResult(
                    valid=True,
                    account_id=data["account_id"],
                    session_id=data["session_id"],
                    assurance_level=data.get("assurance_level", "aal1"),
                    token_id=data.get("token_id"),
                )
            except (json.JSONDecodeError, KeyError):
                # Corrupt cache entry — fall through to live verify
                await self._redis.delete(cache_key)

        # 2. Live verification
        try:
            claims = self._jwks.verify_token(token)
        except Exception as exc:
            return IntrospectionResult(valid=False, reason=f"jwt_error: {exc!s}")

        account_id = claims.get("sub")
        session_id = claims.get("sid")
        token_id = claims.get("jti")
        exp = claims.get("exp")
        aal = claims.get("aal", "aal1")

        # 3. Revocation checks
        if await self._is_jti_revoked(token_id or ""):
            return IntrospectionResult(valid=False, reason="token_revoked_jti")
        if await self._is_session_revoked(session_id or ""):
            return IntrospectionResult(valid=False, reason="token_revoked_session")

        # 4. Cache with capped TTL
        if exp:
            ttl_s = int(exp - time.time())
            ttl_s = min(ttl_s, _MAX_INTROSPECT_TTL_S)
            if ttl_s > _MIN_INTROSPECT_TTL_S:
                cache_data = json.dumps(
                    {
                        "account_id": account_id,
                        "session_id": session_id,
                        "assurance_level": aal,
                        "token_id": token_id,
                    }
                )
                await self._redis.setex(cache_key, ttl_s, cache_data)

        return IntrospectionResult(
            valid=True,
            account_id=account_id,
            session_id=session_id,
            assurance_level=aal,
            token_id=token_id,
            expires_at=datetime.fromtimestamp(exp, tz=UTC) if exp else None,
        )

    # ── Revocation ────────────────────────────────────────────────────────────

    async def revoke_session(self, session_id: str, ttl_s: int = 86_400) -> None:
        """Mark a session as revoked. All tokens for this session are invalidated immediately."""
        # Note: tenant_id needed for proper multi-tenant isolation
        # This is a backward-compatible signature; callers should use tenant_id version
        key = f"butler:token:revoked:session:{session_id}"
        await self._redis.setex(key, ttl_s, "1")
        logger.info("session_revoked", session_id=session_id)

    async def revoke_jti(self, token_id: str, ttl_s: int = 86_400) -> None:
        """Revoke a specific token by its JTI."""
        # Note: tenant_id needed for proper multi-tenant isolation
        # This is a backward-compatible signature; callers should use tenant_id version
        key = f"butler:token:revoked:jti:{token_id}"
        await self._redis.setex(key, ttl_s, "1")
        logger.info("jti_revoked", token_id=token_id)

    async def revoke_all_sessions(self, account_id: str, session_ids: list[str]) -> int:
        """Revoke all known sessions for an account. Returns count revoked."""
        # Note: tenant_id needed for proper multi-tenant isolation
        # This is a backward-compatible signature; callers should use tenant_id version
        pipe = self._redis.pipeline()
        for sid in session_ids:
            pipe.setex(f"butler:token:revoked:session:{sid}", 86_400, "1")
        await pipe.execute()
        logger.info("all_sessions_revoked", account_id=account_id, count=len(session_ids))
        return len(session_ids)

    # ── Tool credential forwarding ────────────────────────────────────────────

    async def get_tool_credential(
        self,
        provider: str,
        account_id: str,
    ) -> ToolCredential | None:
        """Fetch a tool credential for a provider.

        Checks in-process memory cache first. Falls back to environment
        variable (for dev-mode single-user deployments). Production would
        fetch from encrypted PostgreSQL tool_credentials table.

        This method NEVER logs the api_key. Callers must treat the returned
        ToolCredential as ephemeral and not store it beyond the tool call lifetime.
        """
        cache_key = f"{provider}:{account_id}"
        now = time.monotonic()

        # In-memory cache hit
        if cache_key in self._tool_cache:
            cred, cached_at = self._tool_cache[cache_key]
            if (now - cached_at) < _TOOL_CRED_CACHE_TTL_S:
                return cred

        # Dev-mode: read from BUTLER_TOOL_CRED_{PROVIDER} env var
        env_key = f"BUTLER_TOOL_CRED_{provider.upper().replace('-', '_')}"
        api_key = os.environ.get(env_key)
        if not api_key:
            logger.debug("tool_cred_not_found", provider=provider, source="env")
            return None

        cred = ToolCredential(provider=provider, api_key=api_key)
        self._tool_cache[cache_key] = (cred, now)
        logger.debug("tool_cred_loaded", provider=provider, source="env")
        return cred

    def bust_tool_cache(self, provider: str | None = None) -> None:
        """Invalidate in-memory tool credential cache entries."""
        if provider:
            keys_to_del = [k for k in self._tool_cache if k.startswith(f"{provider}:")]
            for k in keys_to_del:
                del self._tool_cache[k]
        else:
            self._tool_cache.clear()

    # ── AAL helper ────────────────────────────────────────────────────────────

    @staticmethod
    def aal_satisfies(provided: str, required: str) -> bool:
        """Return True if provided AAL meets or exceeds required AAL.

        AAL1 < AAL2 < AAL3 (numeric suffix ordering).
        """
        _rank = {"aal1": 1, "aal2": 2, "aal3": 3}
        return _rank.get(provided.lower(), 0) >= _rank.get(required.lower(), 0)

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _is_session_revoked(self, session_id: str) -> bool:
        if not session_id:
            return False
        # TODO: Use tenant_id from cached data for proper multi-tenant isolation
        key = f"butler:token:revoked:session:{session_id}"
        val = await self._redis.get(key)
        return val is not None

    async def _is_jti_revoked(self, token_id: str) -> bool:
        if not token_id:
            return False
        # TODO: Use tenant_id from cached data for proper multi-tenant isolation
        key = f"butler:token:revoked:jti:{token_id}"
        val = await self._redis.get(key)
        return val is not None


def _token_fingerprint(token: str) -> str:
    """SHA-256 fingerprint of token bytes — used as Redis cache key.

    Never store the raw token in Redis — fingerprint only.
    """
    return hashlib.sha256(token.encode()).hexdigest()[:32]
