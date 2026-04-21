"""ButlerSessionStore — Phase 4.

The Orchestrator's memory interface. Provides a clean, session-scoped
API for recording conversation turns and assembling context packs.

Used by:
  - OrchestratorService.intake() / intake_streaming() → append_turn()
  - DurableExecutor → get_context() before each kernel step
  - MemoryService (called at end of turn) → flush_to_long_term()

Sovereignty rules:
  - All writes go through ButlerMemoryStore, which enforces policy.
  - ButlerSessionStore never writes to any storage backend directly.
  - Context assembly merges HOT (Redis), WARM (Qdrant stub), and COLD
    (TurboQuant) into a single ContextPack for the Orchestrator.
  - Hermes memory plugins are never consulted here. They are auxiliary
    copies, not the Butler context source.
"""

from __future__ import annotations

import json
import structlog
from datetime import datetime, UTC
from dataclasses import dataclass, field

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from domain.memory.write_policy import MemoryWritePolicy, MemoryWriteRequest, StorageTier
from domain.memory.contracts import ContextPack, IMemoryWriteStore, IColdStore

logger = structlog.get_logger(__name__)

# Max HOT messages retrieved for context
_HOT_CONTEXT_LIMIT = 20

# Score threshold below which cold results are ignored in context
_COLD_SCORE_THRESHOLD = 0.3


@dataclass
class ConversationTurnRecord:
    """Lightweight turn record for context assembly (no ORM dependency)."""
    role: str
    content: str
    ts: str
    metadata: dict = field(default_factory=dict)


class ButlerSessionStore:
    """Orchestrator's session-scoped memory interface.

    Depends on IMemoryWriteStore and IColdStore contracts — no concrete imports.
    All writes route through the injected memory store (policy-gated).
    """

    def __init__(
        self,
        account_id: str,
        session_id: str,
        redis: Redis,
        memory_store: IMemoryWriteStore,
        cold_store: IColdStore | None = None,
    ):
        self._account_id = account_id
        self._session_id = session_id
        self._redis = redis
        self._store = memory_store
        self._cold = cold_store
        self._policy = MemoryWritePolicy()

    # ── Turn recording ────────────────────────────────────────────────────────

    async def append_turn(
        self,
        role: str,
        content: str,
        metadata: dict | None = None,
    ) -> None:
        """Record a conversation turn.

        Routes via ButlerMemoryStore → HOT tier (Redis) + session_message
        sidecar to Hermes SessionDB.
        """
        await self._store.write(MemoryWriteRequest(
            memory_type="session_message",
            content={"role": role, "content": content, **(metadata or {})},
            account_id=self._account_id,
            session_id=self._session_id,
            provenance="conversation",
            importance=0.5,
        ))
        logger.debug("session_turn_appended", role=role, session_id=self._session_id)

    async def flush_to_long_term(
        self,
        content: str,
        memory_type: str = "episode",
        importance: float = 0.6,
        has_pii: bool = False,
    ) -> None:
        """Write a distilled episode to long-term memory after a turn completes.

        Routes via ButlerMemoryStore → WARM + STRUCT (or COLD if old enough).
        Called by OrchestratorService after a successful assistant turn.
        """
        await self._store.write(MemoryWriteRequest(
            memory_type=memory_type,
            content=content,
            account_id=self._account_id,
            session_id=self._session_id,
            provenance="conversation",
            importance=importance,
            age_days=0.0,
            has_pii=has_pii,
        ))
        logger.debug("session_flushed_to_long_term", memory_type=memory_type, session_id=self._session_id)

    # ── Context assembly ──────────────────────────────────────────────────────

    async def get_context(self, query: str, limit: int = _HOT_CONTEXT_LIMIT) -> ContextPack:
        """Assemble a ContextPack for the Orchestrator kernel."""
        hot = await self._get_hot_context(limit)
        
        # Fetch running summary from Redis (if exists)
        summary = None
        raw_session = await self._redis.get(f"butler:session:{self._session_id}")
        if raw_session:
            session_data = json.loads(raw_session)
            summary = session_data.get("running_summary")

        return ContextPack(
            session_history=hot,
            relevant_memories=[],
            preferences=[],
            entities=[],
            summary_anchor=summary,
            context_token_budget=4096,
        )

    async def _get_hot_context(self, limit: int) -> list[dict]:
        """Fetch recent turns from Redis HOT tier."""
        key = f"butler:memory:hot:{self._account_id}:{self._session_id}"
        try:
            raw_items = await self._redis.lrange(key, 0, limit - 1)
            turns = []
            for raw in reversed(raw_items):  # reverse to get oldest-first
                if isinstance(raw, bytes):
                    raw = raw.decode()
                try:
                    turns.append(json.loads(raw))
                except (json.JSONDecodeError, ValueError):
                    pass
            return turns
        except Exception as exc:
            logger.warning("hot_context_fetch_failed", error=str(exc))
            return []

    # ── Observability ─────────────────────────────────────────────────────────

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def account_id(self) -> str:
        return self._account_id
