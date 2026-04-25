"""ButlerSessionManager — Phase 3.

Butler owns session state. Hermes session_context vars are applied here,
scoped to a single request/WebSocket lifespan, then torn down.

Responsibilities:
  - Register / refresh session in Redis (TTL-based)
  - Store session metadata in PostgreSQL (lazy, on first message)
  - Set Hermes ContextVars (set_session_vars) for the request lifespan
  - Provide session history interface consumed by OrchestratorService
  - Ensure each concurrent request gets isolated session state
    (contextvars — concurrency-safe, no os.environ bleed)

What it does NOT do:
  - Decide execution strategy (RuntimeKernel)
  - Know about tools or memory tiers
  - Block on Hermes internal session file I/O
"""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from services.tenant.namespace import get_tenant_namespace

# P0 hardening: Removed direct Hermes import for session context
# Butler-owned session context implementation pending
# from integrations.hermes.gateway.session_context import set_session_vars, clear_session_vars

logger = structlog.get_logger(__name__)

# Session TTL in Redis — 24 h rolling window
_SESSION_TTL_S = 86_400

# History record limit returned to Orchestrator per request
_HISTORY_LIMIT = 20


@dataclass
class ButlerSession:
    """Immutable snapshot of a session at request time."""

    session_id: str
    account_id: str
    channel: str
    platform: str  # Hermes platform value (api, telegram, slack…)
    assurance_level: str = "AAL1"
    device_id: str | None = None
    resume_token: str | None = None
    running_summary: str | None = None  # Persistent context anchor (Markdown)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ButlerSessionManager:
    """Session lifecycle owner for Butler.

    Injected into gateway routes. OrchestratorService calls
    get_history() and append_message() through this interface.
    """

    def __init__(self, redis: Redis, db: AsyncSession):
        self._redis = redis
        self._db = db

    # ── Public: bootstrap ─────────────────────────────────────────────────────

    async def bootstrap(
        self,
        account_id: str,
        channel: str = "api",
        device_id: str | None = None,
        resume_token: str | None = None,
    ) -> ButlerSession:
        """Create a new session, register in Redis, return ButlerSession."""
        session_id = f"ses_{uuid.uuid4().hex[:16]}"
        platform = _channel_to_platform(channel)

        session = ButlerSession(
            session_id=session_id,
            account_id=str(account_id),
            channel=channel,
            platform=platform,
            device_id=device_id,
            resume_token=f"res_{uuid.uuid4().hex[:8]}",
        )

        await self._store_session_redis(session)
        logger.info(
            "session_bootstrapped", session_id=session_id, account_id=account_id, channel=channel
        )
        return session

    async def get_or_create(
        self,
        session_id: str,
        account_id: str,
        channel: str = "api",
        assurance_level: str = "AAL1",
        device_id: str | None = None,
        tenant_id: str | None = None,  # P0 hardening: required for TenantNamespace
    ) -> ButlerSession:
        """Fetch an existing session from Redis or create a new one."""
        # P0 hardening: Use TenantNamespace for Redis key formatting
        namespace = get_tenant_namespace(tenant_id or account_id)
        session_key = namespace.session(session_id)

        raw = await self._redis.get(session_key)
        if raw:
            data = json.loads(raw)
            session = ButlerSession(**data)
            # Refresh TTL
            await self._redis.expire(session_key, _SESSION_TTL_S)
            return session

        platform = _channel_to_platform(channel)
        session = ButlerSession(
            session_id=session_id,
            account_id=str(account_id),
            channel=channel,
            platform=platform,
            assurance_level=assurance_level,
            device_id=device_id,
        )
        await self._store_session_redis(session, tenant_id)
        return session

    async def invalidate(self, session_id: str, tenant_id: str | None = None) -> None:
        """Delete session from Redis (logout / session expiry)."""
        # P0 hardening: Use TenantNamespace for Redis key formatting
        namespace = get_tenant_namespace(tenant_id or "default")
        session_key = namespace.session(session_id)
        history_key = f"{namespace.prefix}:history:{session_id}"

        await self._redis.delete(session_key)
        await self._redis.delete(history_key)
        logger.info("session_invalidated", session_id=session_id)

    # ── Public: history ───────────────────────────────────────────────────────

    async def get_history(
        self, session_id: str, limit: int = _HISTORY_LIMIT, tenant_id: str | None = None
    ) -> list[dict]:
        """Return the last N messages for this session (Redis list, newest-first)."""
        # P0 hardening: Use TenantNamespace for Redis key formatting
        namespace = get_tenant_namespace(tenant_id or "default")
        history_key = f"{namespace.prefix}:history:{session_id}"

        raw_messages = await self._redis.lrange(
            history_key,
            0,
            limit - 1,
        )
        messages = []
        for raw in reversed(raw_messages):
            with suppress(json.JSONDecodeError, ValueError):
                messages.append(json.loads(raw))
        return messages

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tenant_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Append a message to this session's history in Redis."""
        # P0 hardening: Use TenantNamespace for Redis key formatting
        namespace = get_tenant_namespace(tenant_id or "default")
        history_key = f"{namespace.prefix}:history:{session_id}"

        record = json.dumps(
            {
                "role": role,
                "content": content,
                "ts": datetime.now(UTC).isoformat(),
                **({"metadata": metadata} if metadata else {}),
            }
        )
        pipe = self._redis.pipeline()
        pipe.lpush(history_key, record)
        pipe.ltrim(history_key, 0, 99)  # keep last 100
        pipe.expire(history_key, _SESSION_TTL_S)
        await pipe.execute()

    async def update_summary(
        self, session_id: str, summary: str, tenant_id: str | None = None
    ) -> None:
        """Update the running summary anchor in Redis."""
        # P0 hardening: Use TenantNamespace for Redis key formatting
        namespace = get_tenant_namespace(tenant_id or "default")
        session_key = namespace.session(session_id)

        raw = await self._redis.get(session_key)
        if not raw:
            return
        data = json.loads(raw)
        data["running_summary"] = summary
        await self._redis.setex(session_key, _SESSION_TTL_S, json.dumps(data))
        logger.info("session_summary_updated", session_id=session_id)

    # ── Context manager: Butler session context ──────────────────────────────────

    @asynccontextmanager
    async def butler_context(self, session: ButlerSession):
        """Apply Butler session context for the request lifespan.

        Usage (in route handler):
            async with session_mgr.butler_context(session):
                result = await orchestrator.intake(envelope)

        P0 hardening: Butler-owned session context implementation pending.
        For now, this is a no-op context manager.
        """
        # P0 hardening: Butler-owned session context pending
        # For now, use no-op until Butler-owned implementation is added
        yield self
        # P0 hardening: Butler-owned session context cleanup pending

    # ── Private ───────────────────────────────────────────────────────────────

    async def _store_session_redis(
        self, session: ButlerSession, tenant_id: str | None = None
    ) -> None:
        data = json.dumps(
            {
                "session_id": session.session_id,
                "account_id": session.account_id,
                "channel": session.channel,
                "platform": session.platform,
                "assurance_level": session.assurance_level,
                "device_id": session.device_id,
                "resume_token": session.resume_token,
                "running_summary": session.running_summary,
                "created_at": session.created_at.isoformat(),
            }
        )
        # P0 hardening: Use TenantNamespace for Redis key formatting
        namespace = get_tenant_namespace(tenant_id or session.account_id)
        session_key = namespace.session(session.session_id)
        await self._redis.setex(session_key, _SESSION_TTL_S, data)


# ── Helpers ───────────────────────────────────────────────────────────────────

_CHANNEL_PLATFORM_MAP = {
    "api": "api",
    "telegram": "telegram",
    "slack": "slack",
    "discord": "discord",
    "whatsapp": "whatsapp",
    "web": "web",
    "voice": "voice",
    "mcp": "mcp",
}


def _channel_to_platform(channel: str) -> str:
    return _CHANNEL_PLATFORM_MAP.get(channel.lower(), "api")
