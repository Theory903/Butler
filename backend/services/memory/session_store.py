from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from redis.asyncio import Redis

from domain.memory.contracts import (
    ContextPack,
    IColdStore,
    IMemoryWriteStore,
    MemoryServiceContract,
)
from domain.memory.write_policy import MemoryWriteRequest
from services.tenant.namespace import get_tenant_namespace

logger = structlog.get_logger(__name__)

# Max HOT messages retrieved for context
_HOT_CONTEXT_LIMIT = 20

# Score threshold below which cold results are ignored in context
_COLD_SCORE_THRESHOLD = 0.3

# Default token budget if no richer context builder is available
_DEFAULT_CONTEXT_TOKEN_BUDGET = 4096

# Redis session summary TTL fallback when the upstream payload has no TTL metadata
_DEFAULT_SESSION_SUMMARY_TTL_S = 7 * 24 * 60 * 60


@dataclass(slots=True)
class ConversationTurnRecord:
    """Lightweight turn record for context assembly.

    This record stays intentionally transport-safe and ORM-free so that
    the session store can work in degraded mode without pulling model types
    into the hot path.
    """

    role: str
    content: str
    ts: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "ts": self.ts,
            **self.metadata,
        }


class ButlerSessionStore:
    """Orchestrator's session-scoped memory interface.

    Responsibilities:
    - append hot session turns through the policy-gated memory store
    - flush durable long-term memory through the same store
    - assemble a ContextPack for orchestration
    - prefer MemoryService.build_context() when a canonical memory service is injected
    - degrade safely to HOT + summary + COLD recall when the richer path is unavailable

    Design notes:
    - This class never writes directly to Qdrant/Postgres/Neo4j/TurboQuant.
    - It only writes through IMemoryWriteStore.
    - It may read Redis directly for HOT context and session summary.
    - It may read the cold tier directly for degraded recall if injected.
    """

    def __init__(
        self,
        account_id: str,
        session_id: str,
        redis: Redis,
        memory_store: IMemoryWriteStore,
        cold_store: IColdStore | None = None,
        memory_service: MemoryServiceContract | None = None,
        *,
        hot_context_limit: int = _HOT_CONTEXT_LIMIT,
        context_token_budget: int = _DEFAULT_CONTEXT_TOKEN_BUDGET,
        cold_score_threshold: float = _COLD_SCORE_THRESHOLD,
        tenant_id: str | None = None,  # P0 hardening: required for TenantNamespace
    ) -> None:
        if hot_context_limit <= 0:
            raise ValueError("hot_context_limit must be greater than 0")
        if context_token_budget <= 0:
            raise ValueError("context_token_budget must be greater than 0")
        if not (0.0 <= cold_score_threshold <= 1.0):
            raise ValueError("cold_score_threshold must be between 0.0 and 1.0")

        self._account_id = account_id
        self._session_id = session_id
        self._redis = redis
        self._store = memory_store
        self._cold = cold_store
        self._memory = memory_service
        self._hot_context_limit = hot_context_limit
        # P0 hardening: Use TenantNamespace for Redis key formatting
        self._tenant_id = tenant_id or account_id  # Use account_id as fallback
        self._namespace = get_tenant_namespace(self._tenant_id)
        self._context_token_budget = context_token_budget
        self._cold_score_threshold = cold_score_threshold

    # ── Turn recording ────────────────────────────────────────────────────────

    async def append_turn(
        self,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a conversation turn.

        Routes via IMemoryWriteStore using the canonical session_message write
        policy, which drives HOT storage and any approved sidecars.
        """
        normalized_role = (role or "").strip() or "user"
        normalized_content = (content or "").strip()
        if not normalized_content:
            logger.debug(
                "session_turn_ignored_empty_content",
                role=normalized_role,
                session_id=self._session_id,
            )
            return

        write_request = MemoryWriteRequest(
            memory_type="session_message",
            content={
                "role": normalized_role,
                "content": normalized_content,
                **(metadata or {}),
            },
            account_id=self._account_id,
            session_id=self._session_id,
            provenance="conversation",
            importance=0.5,
            metadata={
                "role": normalized_role,
                "ts": datetime.now(UTC).isoformat(),
                **(metadata or {}),
            },
        )

        await self._store.write(write_request, tenant_id=self._tenant_id)
        logger.debug(
            "session_turn_appended",
            role=normalized_role,
            session_id=self._session_id,
        )

    async def flush_to_long_term(
        self,
        content: str,
        memory_type: str = "episode",
        importance: float = 0.6,
        has_pii: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Write distilled long-term memory through the canonical write store."""
        normalized_content = (content or "").strip()
        if not normalized_content:
            logger.debug(
                "session_long_term_flush_ignored_empty_content",
                session_id=self._session_id,
                memory_type=memory_type,
            )
            return

        await self._store.write(
            MemoryWriteRequest(
                memory_type=memory_type,
                content=normalized_content,
                account_id=self._account_id,
                session_id=self._session_id,
                provenance="conversation",
                importance=float(importance),
                age_days=0.0,
                has_pii=bool(has_pii),
                metadata=metadata or {},
            ),
            tenant_id=self._tenant_id,
        )
        logger.debug(
            "session_flushed_to_long_term",
            memory_type=memory_type,
            session_id=self._session_id,
        )

    # ── Context assembly ──────────────────────────────────────────────────────

    async def get_context(
        self,
        query: str,
        limit: int = _HOT_CONTEXT_LIMIT,
    ) -> ContextPack:
        """Assemble a ContextPack for the orchestrator kernel.

        Strategy:
        1. Prefer canonical MemoryService.build_context() when injected.
        2. Fall back to HOT Redis turns + summary + optional cold recall.
        """
        normalized_limit = max(1, min(limit, self._hot_context_limit))
        normalized_query = (query or "").strip()

        if self._memory is not None:
            try:
                context = await self._memory.build_context(
                    self._account_id,
                    normalized_query,
                    self._session_id,
                )
                logger.debug(
                    "session_context_built_via_memory_service",
                    session_id=self._session_id,
                    account_id=self._account_id,
                    query=normalized_query[:120],
                )
                return context
            except Exception as exc:
                logger.warning(
                    "session_context_build_via_memory_service_failed",
                    session_id=self._session_id,
                    account_id=self._account_id,
                    error=str(exc),
                )

        hot_history = await self._get_hot_context(normalized_limit)
        summary_anchor = await self._get_summary_anchor()
        relevant_memories = await self._get_fallback_relevant_memories(
            normalized_query,
            normalized_limit,
        )

        context_pack = ContextPack(
            session_history=hot_history,
            relevant_memories=relevant_memories,
            preferences=[],
            entities=[],
            summary_anchor=summary_anchor,
            context_token_budget=self._context_token_budget,
        )

        logger.debug(
            "session_context_built_fallback",
            session_id=self._session_id,
            account_id=self._account_id,
            hot_turns=len(hot_history),
            memory_count=len(relevant_memories),
            has_summary=bool(summary_anchor),
        )
        return context_pack

    async def _get_hot_context(self, limit: int) -> list[dict[str, Any]]:
        """Fetch recent turns from Redis HOT tier.

        Redis list items are written with LPUSH at the head, so LRANGE(0..n)
        returns newest-first; we reverse to provide oldest-first prompt order.  [oai_citation:1‡Redis](https://redis.io/docs/latest/commands/lpush/?utm_source=chatgpt.com)
        """
        key = self._hot_key
        try:
            raw_items = await self._redis.lrange(key, 0, limit - 1)
        except Exception as exc:
            logger.warning(
                "hot_context_fetch_failed",
                session_id=self._session_id,
                account_id=self._account_id,
                error=str(exc),
            )
            return []

        turns: list[dict[str, Any]] = []
        for raw in reversed(raw_items):
            decoded = self._decode_redis_value(raw)
            if decoded is None:
                continue

            try:
                payload = json.loads(decoded)
            except (json.JSONDecodeError, TypeError, ValueError):
                logger.debug(
                    "hot_context_item_invalid_json_ignored",
                    session_id=self._session_id,
                )
                continue

            normalized = self._normalize_hot_turn_payload(payload)
            if normalized is not None:
                turns.append(normalized)

        return turns

    async def _get_summary_anchor(self) -> str | None:
        """Fetch the running session summary anchor from Redis if present."""
        raw_session = None
        try:
            raw_session = await self._redis.get(self._session_summary_key)
        except Exception as exc:
            logger.warning(
                "session_summary_fetch_failed",
                session_id=self._session_id,
                account_id=self._account_id,
                error=str(exc),
            )
            return None

        if raw_session is None:
            return None

        decoded = self._decode_redis_value(raw_session)
        if not decoded:
            return None

        try:
            session_data = json.loads(decoded)
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.warning(
                "session_summary_invalid_json",
                session_id=self._session_id,
                account_id=self._account_id,
            )
            return None

        summary = session_data.get("running_summary")
        if not isinstance(summary, str):
            return None

        cleaned = summary.strip()
        return cleaned or None

    async def _get_fallback_relevant_memories(
        self,
        query: str,
        limit: int,
    ) -> list[Any]:
        """Fallback retrieval path when canonical MemoryService is unavailable.

        Order of preference:
        1. cold tier recall, filtered by account and score
        2. no results if cold tier is absent or query is empty
        """
        if not query or self._cold is None:
            return []

        try:
            raw_results = await self._cold.recall(
                self._account_id,
                query,
                top_k=limit,
            )
        except Exception as exc:
            logger.warning(
                "fallback_cold_recall_failed",
                session_id=self._session_id,
                account_id=self._account_id,
                error=str(exc),
            )
            return []

        filtered: list[Any] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue

            score = item.get("score", 0.0)
            try:
                numeric_score = float(score)
            except (TypeError, ValueError):
                numeric_score = 0.0

            if numeric_score < self._cold_score_threshold:
                continue

            metadata = item.get("metadata", {}) or {}
            if metadata.get("account_id") not in {None, "", self._account_id}:
                continue

            content = item.get("content")
            if content is None and isinstance(metadata, dict):
                content = metadata.get("content")

            if content is None:
                continue

            filtered.append(
                self._build_fallback_memory_record(
                    content=content,
                    score=numeric_score,
                    metadata=metadata,
                )
            )

        filtered.sort(
            key=lambda item: (
                -float(getattr(item, "score", 0.0)),
                str(getattr(item, "memory_type", "")),
                str(getattr(item, "content", ""))[:120],
            )
        )
        return filtered[:limit]

    def _build_fallback_memory_record(
        self,
        *,
        content: Any,
        score: float,
        metadata: dict[str, Any],
    ) -> _FallbackMemoryRecord:
        return _FallbackMemoryRecord(
            memory_type=str(metadata.get("memory_type", "cold_recall")),
            content=str(content),
            score=float(score),
            metadata=metadata,
        )

    def _normalize_hot_turn_payload(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Normalize stored Redis turn payloads into a consistent shape."""
        if not isinstance(payload, dict):
            return None

        role = str(payload.get("role", "")).strip() or "user"
        content = payload.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        content = content.strip()
        if not content:
            return None

        ts = payload.get("ts") or payload.get("timestamp")
        if not isinstance(ts, str) or not ts.strip():
            ts = datetime.now(UTC).isoformat()

        metadata = {
            key: value
            for key, value in payload.items()
            if key not in {"role", "content", "ts", "timestamp"}
        }

        turn = ConversationTurnRecord(
            role=role,
            content=content,
            ts=ts,
            metadata=metadata,
        )
        return turn.to_dict()

    def _decode_redis_value(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except UnicodeDecodeError:
                return None
        if isinstance(value, str):
            return value
        return str(value)

    @property
    def _hot_key(self) -> str:
        # P0 hardening: Use TenantNamespace for Redis key formatting
        return f"{self._namespace.prefix}:memory:hot:{self._session_id}"

    @property
    def _session_summary_key(self) -> str:
        # P0 hardening: Use TenantNamespace.session() for Redis key formatting
        return self._namespace.session(self._session_id)

    # ── Optional summary helper ───────────────────────────────────────────────

    async def upsert_summary_anchor(
        self,
        summary: str,
        *,
        ttl_seconds: int = _DEFAULT_SESSION_SUMMARY_TTL_S,
    ) -> None:
        """Persist or update the running summary anchor in Redis."""
        cleaned = (summary or "").strip()
        if not cleaned:
            return

        existing_payload: dict[str, Any] = {}
        try:
            raw_existing = await self._redis.get(self._session_summary_key)
            if raw_existing is not None:
                decoded = self._decode_redis_value(raw_existing)
                if decoded:
                    existing_payload = json.loads(decoded)
        except Exception:
            logger.debug(
                "session_summary_existing_payload_load_failed",
                session_id=self._session_id,
                account_id=self._account_id,
            )

        existing_payload["running_summary"] = cleaned
        existing_payload["updated_at"] = datetime.now(UTC).isoformat()

        await self._redis.setex(
            self._session_summary_key,
            ttl_seconds,
            json.dumps(existing_payload),
        )

    # ── Observability ─────────────────────────────────────────────────────────

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def account_id(self) -> str:
        return self._account_id


@dataclass(slots=True)
class _FallbackMemoryRecord:
    """Minimal memory-shaped object for degraded context assembly."""

    memory_type: str
    content: str
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
