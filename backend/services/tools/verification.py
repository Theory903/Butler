"""ToolVerifier — v3.1 production enforcement.

Policy checks follow the trust hierarchy approved in the implementation plan:
  1. JWT/session claims  (fast, no I/O)
  2. Redis hot cache     (sub-ms)
  3. DB / policy store  on cache miss or high-risk tools

Risk-tier floor map:
  low      → always allowed (no extra gate)
  medium   → require "standard" account tier or above
  high     → require "pro" account tier OR explicit approval token
  critical → require valid, bound approval token (always)

Side-effect classes:
  read     → no approval gate
  write    → idempotency key required (enforced by executor)
  execute  → requires "pro" tier or above
  external → requires approval token

Approval token contract (bound to account + tool + risk tier):
  Format: "{account_id}:{tool_name}:{risk_tier}:{expiry_unix}"
  Signed with HMAC-SHA256 (butler.security.crypto.sign_approval)
  Verified with time.time() < expiry_unix
"""

from __future__ import annotations

import hashlib
import hmac
import time
import logging
from typing import Optional, TYPE_CHECKING

import jsonschema
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from domain.tools.models import ToolDefinition
from domain.tools.contracts import VerificationResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── Account tier ordering ─────────────────────────────────────────────────────
_TIER_RANK: dict[str, int] = {
    "free": 0,
    "standard": 1,
    "pro": 2,
    "enterprise": 3,
}

# ── Risk tier floor requirements ──────────────────────────────────────────────
_RISK_TIER_FLOOR: dict[str, str] = {
    "low": "free",
    "medium": "standard",
    "high": "pro",
    "critical": "pro",     # + approval token always required
}

# ── Side-effect class gates ───────────────────────────────────────────────────
_SIDE_EFFECT_TIER_FLOOR: dict[str, str] = {
    "read": "free",
    "write": "free",       # idempotency enforced by executor
    "execute": "pro",
    "external": "free",    # approval gate applied separately
}

_SIDE_EFFECT_NEEDS_APPROVAL: frozenset[str] = frozenset({"external"})
_APPROVAL_ALWAYS_REQUIRED: frozenset[str] = frozenset({"critical"})

# Cache TTL for account scopes
_SCOPE_CACHE_TTL_S = 300   # 5-minute hot cache


class ToolVerifier:
    """Pre/post execution verification for tools.

    Injected into ToolExecutor. Requires redis + db for real policy enforcement.
    """

    def __init__(
        self,
        redis: Optional[Redis] = None,
        db: Optional[AsyncSession] = None,
        approval_secret: str = "",
    ) -> None:
        self._redis = redis
        self._db = db
        self._approval_secret = approval_secret

    async def verify_preconditions(
        self,
        tool: ToolDefinition,
        params: dict,
        account_id: str,
        account_tier: str = "free",
        approval_token: Optional[str] = None,
        session_scopes: Optional[set[str]] = None,
    ) -> VerificationResult:
        """Check all preconditions before tool execution."""
        checks: list[tuple[str, bool]] = []

        # 1. Input schema validation
        schema_valid = self._validate_schema(tool.input_schema, params)
        checks.append(("schema", schema_valid))

        # 2. Risk-tier floor check (account tier must meet minimum)
        risk_ok = self._check_risk_tier(tool.risk_tier, account_tier)
        checks.append(("risk_tier", risk_ok))

        # 3. Side-effect class gate
        side_effect_ok = self._check_side_effect_class(tool.side_effect_class, account_tier)
        checks.append(("side_effect_class", side_effect_ok))

        # 4. Permission / scope check (JWT → Redis → DB)
        has_permission = await self._check_permission(
            tool, account_id, session_scopes=session_scopes
        )
        checks.append(("permission", has_permission))

        # 5. Approval token (required for critical risk, external side-effects, or high-risk + no pro tier)
        needs_approval = self._needs_approval(tool, account_tier)
        if needs_approval:
            token_ok = self._verify_approval_token(
                approval_token, account_id, tool.name, tool.risk_tier
            )
            checks.append(("approval_token", token_ok))

        passed = all(ok for _, ok in checks)
        reason = None if passed else next(
            (name for name, ok in checks if not ok),
            "precondition_failed",
        )
        return VerificationResult(passed=passed, checks=checks, reason=reason)

    async def verify_postconditions(
        self,
        tool: ToolDefinition,
        params: dict,
        result: dict,
    ) -> VerificationResult:
        """Check postconditions — did the tool do what it claimed?"""
        checks: list[tuple[str, bool]] = []

        # 1. Output schema validation
        if tool.output_schema:
            schema_valid = self._validate_schema(tool.output_schema, result)
            checks.append(("output_schema", schema_valid))

        # 2. Side-effect verification
        side_effect_ok = await self._verify_side_effects(
            tool.name, tool.side_effect_class or "read", params, result
        )
        checks.append(("side_effects", side_effect_ok))

        passed = all(ok for _, ok in checks)
        reason = "output_validation_failed" if not passed else None
        return VerificationResult(passed=passed, checks=checks, reason=reason)

    # ── Schema validation ─────────────────────────────────────────────────────

    def _validate_schema(self, schema: dict | None, data: dict) -> bool:
        try:
            if schema:
                jsonschema.validate(instance=data, schema=schema)
            return True
        except jsonschema.ValidationError as exc:
            logger.debug("tool.schema_invalid", error=str(exc.message))
            return False

    # ── Risk tier ─────────────────────────────────────────────────────────────

    def _check_risk_tier(self, risk_tier: str, account_tier: str) -> bool:
        """Account tier must meet the risk tier's minimum floor."""
        floor = _RISK_TIER_FLOOR.get(risk_tier or "low", "free")
        account_rank = _TIER_RANK.get(account_tier, 0)
        floor_rank = _TIER_RANK.get(floor, 0)
        ok = account_rank >= floor_rank
        if not ok:
            logger.debug(
                "tool.risk_tier_blocked",
                risk_tier=risk_tier,
                account_tier=account_tier,
                required=floor,
            )
        return ok

    # ── Side-effect class ─────────────────────────────────────────────────────

    def _check_side_effect_class(self, side_effect_class: str, account_tier: str) -> bool:
        """Side-effect class may require a minimum account tier."""
        floor = _SIDE_EFFECT_TIER_FLOOR.get(side_effect_class or "read", "free")
        return _TIER_RANK.get(account_tier, 0) >= _TIER_RANK.get(floor, 0)

    def _needs_approval(self, tool: ToolDefinition, account_tier: str) -> bool:
        """Determine if this tool call requires a bound approval token."""
        if tool.risk_tier in _APPROVAL_ALWAYS_REQUIRED:
            return True
        if (tool.side_effect_class or "read") in _SIDE_EFFECT_NEEDS_APPROVAL:
            return True
        # High-risk tools require approval if below pro tier
        if tool.risk_tier == "high" and _TIER_RANK.get(account_tier, 0) < _TIER_RANK["pro"]:
            return True
        return False

    # ── Approval token ────────────────────────────────────────────────────────

    def _verify_approval_token(
        self,
        token: Optional[str],
        account_id: str,
        tool_name: str,
        risk_tier: str,
    ) -> bool:
        """Verify a bound approval token.

        Token format: "{account_id}:{tool_name}:{risk_tier}:{expiry_unix}"
        Signed with HMAC-SHA256 using self._approval_secret.
        The token string is "{payload_b64}.{signature_hex}".
        """
        if not token:
            logger.debug("tool.approval_token_missing", tool=tool_name)
            return False
        try:
            parts = token.split(".")
            if len(parts) != 2:
                return False
            payload_str, sig_hex = parts
            # Verify signature
            expected_sig = hmac.new(
                self._approval_secret.encode(),
                payload_str.encode(),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(sig_hex, expected_sig):
                logger.warning("tool.approval_token_bad_sig", tool=tool_name)
                return False
            # Decode and validate binding
            import base64
            payload = base64.b64decode(payload_str + "==").decode()
            bound_account, bound_tool, bound_risk, expiry_str = payload.split(":")
            if (
                bound_account != account_id
                or bound_tool != tool_name
                or bound_risk != risk_tier
            ):
                logger.warning("tool.approval_token_wrong_binding", tool=tool_name)
                return False
            if time.time() > float(expiry_str):
                logger.info("tool.approval_token_expired", tool=tool_name)
                return False
            return True
        except Exception as exc:
            logger.warning("tool.approval_token_parse_error", tool=tool_name, error=str(exc))
            return False

    # ── Permission / scope ────────────────────────────────────────────────────

    async def _check_permission(
        self,
        tool: ToolDefinition,
        account_id: str,
        session_scopes: Optional[set[str]] = None,
    ) -> bool:
        """Check tool required_scopes against account's active scopes.

        Trust hierarchy:
          1. session_scopes (from JWT claims — fastest, no I/O)
          2. Redis hot cache
          3. DB query on cache miss
        """
        required = set(tool.required_scopes or [])
        if not required:
            return True  # No scopes required — always allowed

        # Tier 1: JWT/session claims
        if session_scopes is not None:
            return required.issubset(session_scopes)

        # Tier 2: Redis hot cache
        if self._redis:
            try:
                cache_key = f"account:scopes:{account_id}"
                cached = await self._redis.smembers(cache_key)
                if cached:
                    account_scopes = {s.decode() if isinstance(s, bytes) else s for s in cached}
                    return required.issubset(account_scopes)
            except Exception as exc:
                logger.warning("tool.scope_cache_error", account_id=account_id, error=str(exc))

        # Tier 3: DB — only for non-trivial tools or cache miss
        if self._db:
            try:
                from domain.auth.models import AccountScope
                from sqlalchemy import select
                stmt = select(AccountScope.scope).where(AccountScope.account_id == account_id)
                result = await self._db.execute(stmt)
                scopes = {row.scope for row in result}
                # Repopulate cache
                if self._redis and scopes:
                    cache_key = f"account:scopes:{account_id}"
                    await self._redis.sadd(cache_key, *scopes)
                    await self._redis.expire(cache_key, _SCOPE_CACHE_TTL_S)
                return required.issubset(scopes)
            except Exception as exc:
                logger.warning("tool.scope_db_error", account_id=account_id, error=str(exc))

        # Fail-open for non-critical tools (no infra available) — log it
        logger.warning(
            "tool.permission_fail_open",
            tool=tool.name,
            account_id=account_id,
            reason="no_infra_available",
        )
        return tool.risk_tier not in ("high", "critical")

    # ── Side-effect verification ──────────────────────────────────────────────

    async def _verify_side_effects(
        self,
        tool_name: str,
        side_effect_class: str,
        params: dict,
        result: dict,
    ) -> bool:
        """Verify the tool's claimed side-effect actually occurred.

        Read-only tools: trivially True.
        Write/external tools: check result.status == "success" and no error key.
        Tool-specific overrides can be added to _TOOL_VERIFIERS.
        """
        if side_effect_class == "read":
            return True

        # Generic write/execute check: result must contain no error
        if "error" in result or result.get("status") == "failed":
            logger.warning(
                "tool.side_effect_error",
                tool=tool_name,
                status=result.get("status"),
                error=result.get("error"),
            )
            return False

        # Tool-specific verifiers
        verifier = _TOOL_VERIFIERS.get(tool_name)
        if verifier:
            return await verifier(params, result, self._db)

        # Default: trust the result if no error
        return True


# ── Tool-specific side-effect verifiers ───────────────────────────────────────
# Registered per tool_name. Signature: async (params, result, db) -> bool

async def _verify_send_email(params: dict, result: dict, db) -> bool:
    """Verify email was accepted by the SMTP layer."""
    return bool(result.get("message_id") or result.get("queued"))

async def _verify_create_calendar_event(params: dict, result: dict, db) -> bool:
    return bool(result.get("event_id") or result.get("id"))

_TOOL_VERIFIERS: dict = {
    "send_email": _verify_send_email,
    "create_calendar_event": _verify_create_calendar_event,
}
