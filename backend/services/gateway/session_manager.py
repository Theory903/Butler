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
import structlog
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import AsyncGenerator, Optional

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from integrations.hermes.gateway.session_context import set_session_vars, clear_session_vars

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
    platform: str                      # Hermes platform value (api, telegram, slack…)
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
        logger.info("session_bootstrapped", session_id=session_id, account_id=account_id, channel=channel)
        return session

    async def get_or_create(
        self,
        session_id: str,
        account_id: str,
        channel: str = "api",
        assurance_level: str = "AAL1",
        device_id: str | None = None,
    ) -> ButlerSession:
        """Fetch an existing session from Redis or create a new one."""
        raw = await self._redis.get(f"butler:session:{session_id}")
        if raw:
            data = json.loads(raw)
            session = ButlerSession(**data)
            # Refresh TTL
            await self._redis.expire(f"butler:session:{session_id}", _SESSION_TTL_S)
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
        await self._store_session_redis(session)
        return session

    async def invalidate(self, session_id: str) -> None:
        """Delete session from Redis (logout / session expiry)."""
        await self._redis.delete(f"butler:session:{session_id}")
        await self._redis.delete(f"butler:session:history:{session_id}")
        logger.info("session_invalidated", session_id=session_id)

    # ── Public: history ───────────────────────────────────────────────────────

    async def get_history(self, session_id: str, limit: int = _HISTORY_LIMIT) -> list[dict]:
        """Return the last N messages for this session (Redis list, newest-first)."""
        raw_messages = await self._redis.lrange(
            f"butler:session:history:{session_id}",
            0,
            limit - 1,
        )
        messages = []
        for raw in reversed(raw_messages):
            try:
                messages.append(json.loads(raw))
            except (json.JSONDecodeError, ValueError):
                pass
        return messages

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict | None = None,
    ) -> None:
        """Append a message to this session's history in Redis."""
        record = json.dumps({
            "role": role,
            "content": content,
            "ts": datetime.now(UTC).isoformat(),
            **({"metadata": metadata} if metadata else {}),
        })
        pipe = self._redis.pipeline()
        pipe.lpush(f"butler:session:history:{session_id}", record)
        pipe.ltrim(f"butler:session:history:{session_id}", 0, 99)  # keep last 100
        pipe.expire(f"butler:session:history:{session_id}", _SESSION_TTL_S)
        await pipe.execute()

    async def update_summary(self, session_id: str, summary: str) -> None:
        """Update the running summary anchor in Redis."""
        raw = await self._redis.get(f"butler:session:{session_id}")
        if not raw:
            return
        data = json.loads(raw)
        data["running_summary"] = summary
        await self._redis.setex(f"butler:session:{session_id}", _SESSION_TTL_S, json.dumps(data))
        logger.info("session_summary_updated", session_id=session_id)

    # ── Context manager: Hermes session vars ──────────────────────────────────

    @asynccontextmanager
    async def hermes_context(self, session: ButlerSession):
        """Apply Hermes session ContextVars for the request lifespan.

        Usage (in route handler):
            async with session_mgr.hermes_context(session):
                result = await orchestrator.intake(envelope)

        Concurrency-safe: uses contextvars, not os.environ.
        """
        tokens = set_session_vars(
            platform=session.platform,
            chat_id=session.session_id,
            user_id=session.account_id,
            session_key=f"butler:main:{session.session_id}",
        )
        try:
            yield session
        finally:
            clear_session_vars(tokens)

    # ── Private ───────────────────────────────────────────────────────────────

    async def _store_session_redis(self, session: ButlerSession) -> None:
        data = json.dumps({
            "session_id": session.session_id,
            "account_id": session.account_id,
            "channel": session.channel,
            "platform": session.platform,
            "assurance_level": session.assurance_level,
            "device_id": session.device_id,
            "resume_token": session.resume_token,
            "running_summary": session.running_summary,
            "created_at": session.created_at.isoformat(),
        })
        await self._redis.setex(f"butler:session:{session.session_id}", _SESSION_TTL_S, data)


# ── Helpers ───────────────────────────────────────────────────────────────────

_CHANNEL_PLATFORM_MAP = {
    "api":       "api",
    "telegram":  "telegram",
    "slack":     "slack",
    "discord":   "discord",
    "whatsapp":  "whatsapp",
    "web":       "web",
    "voice":     "voice",
    "mcp":       "mcp",
}


def _channel_to_platform(channel: str) -> str:
    return _CHANNEL_PLATFORM_MAP.get(channel.lower(), "api")
