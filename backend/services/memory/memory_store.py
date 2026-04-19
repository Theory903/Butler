"""ButlerMemoryStore — Phase 4.

The single policy-gated write dispatcher for all Butler memory writes.
Every memory write in Butler must go through this class — no code should
call DB/Redis/Qdrant/TurboQuant directly for memory storage.

Architecture:
  MemoryWriteRequest
        ↓
  MemoryWritePolicy.route()         ← decides tiers
        ↓                           ← enforces PII rules per tier
  ButlerMemoryStore._write_tier()   ← dispatches to correct backend
     HOT   → Redis (lpush + expire)
     WARM  → Qdrant warm (via HybridRetrieval or qdrant_client)
     COLD  → TurboQuantColdStore (async, PII-gated)
     GRAPH → Neo4j stub (Phase 6)
     STRUCT → PostgreSQL (MemoryEntry table)

Sovereignty rules:
  - Butler policy runs first, always. Backends cannot override tier decisions.
  - PII items are hard-blocked from COLD tier (pyturboquant cannot erase).
  - Hermes SessionDB receives a copy of session_message only, never as
    primary storage — Butler PostgreSQL is canonical.
  - COLD writes are async (thread-pool) to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
import json
import uuid
import structlog
from datetime import datetime, UTC
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from domain.memory.write_policy import (
    MemoryWritePolicy,
    MemoryWriteRequest,
    WriteRoute,
    StorageTier,
)
from domain.memory.models import MemoryEntry, MemoryStatus
from domain.memory.contracts import IColdStore, IMemoryWriteStore
from services.memory.knowledge_repo_contract import KnowledgeRepoContract

logger = structlog.get_logger(__name__)

# Redis session message TTL — 24 h rolling
_HOT_TTL_S = 86_400

# Max items in hot session list
_HOT_MAX = 50


@dataclass
class MemoryWriteResult:
    success: bool
    tiers_written: list[StorageTier]
    entry_id: str | None = None
    cold_id: str | None = None
    error: str | None = None


class ButlerMemoryStore(IMemoryWriteStore):
    """Policy-gated multi-tier memory write dispatcher.

    Depends only on domain contracts — no concrete store imports.
    Wired with concrete implementations by core/deps.py.

    Usage:
        store = ButlerMemoryStore(db=db, redis=redis, cold_store=cold_store)
        result = await store.write(MemoryWriteRequest(...))
    """

    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        cold_store: IColdStore,
        graph_repo: KnowledgeRepoContract | None = None,
        policy: MemoryWritePolicy | None = None,
    ):
        self._db = db
        self._redis = redis
        self._cold = cold_store          # IColdStore contract — no concrete import
        self._graph_repo = graph_repo    # KnowledgeRepoContract — no concrete import
        self._policy = policy or MemoryWritePolicy()

    async def write(self, request: MemoryWriteRequest) -> MemoryWriteResult:
        """Route and write a memory item per Butler policy."""
        route = self._policy.route(request)
        tiers_written: list[StorageTier] = []
        entry_id = None
        cold_id = None
        errors = []

        for tier in route.tiers:
            # PII gate — hard block before any write attempt
            if not self._policy.enforce_pii_rules(request, tier):
                logger.warning(
                    "memory_pii_blocked",
                    tier=tier.value,
                    memory_type=request.memory_type,
                    account_id=request.account_id,
                )
                continue

            try:
                tier_id = await self._write_tier(tier, request, route)
                tiers_written.append(tier)
                if tier == StorageTier.STRUCT:
                    entry_id = tier_id
                if tier == StorageTier.COLD:
                    cold_id = tier_id
            except Exception as exc:
                logger.exception(
                    "memory_tier_write_failed",
                    tier=tier.value,
                    memory_type=request.memory_type,
                    error=str(exc),
                )
                errors.append(f"{tier.value}: {exc}")

        # Hermes SessionDB sidecar — copy only, never primary
        if self._policy.should_write_hermes_session_db(request):
            await self._write_hermes_session_sidecar(request)

        if errors and not tiers_written:
            return MemoryWriteResult(
                success=False,
                tiers_written=[],
                error="; ".join(errors),
            )

        logger.info(
            "memory_written",
            tiers=[t.value for t in tiers_written],
            memory_type=request.memory_type,
            account_id=request.account_id,
        )

        return MemoryWriteResult(
            success=True,
            tiers_written=tiers_written,
            entry_id=entry_id,
            cold_id=cold_id,
        )

    # ── Tier dispatchers ──────────────────────────────────────────────────────

    async def _write_tier(
        self,
        tier: StorageTier,
        request: MemoryWriteRequest,
        route: WriteRoute,
    ) -> str | None:
        match tier:
            case StorageTier.HOT:
                return await self._write_hot(request)
            case StorageTier.WARM:
                return await self._write_warm(request)
            case StorageTier.COLD:
                return await self._write_cold(request)
            case StorageTier.STRUCT:
                return await self._write_struct(request)
            case StorageTier.GRAPH:
                return await self._write_graph(request)
            case _:
                logger.warning("unknown_storage_tier", tier=str(tier))
                return None

    async def _write_hot(self, request: MemoryWriteRequest) -> str:
        """Redis LPUSH + LTRIM + EXPIRE — session context window."""
        if not request.session_id:
            return "no_session"

        key = f"butler:memory:hot:{request.account_id}:{request.session_id}"
        record = json.dumps({
            "memory_type": request.memory_type,
            "content": request.content if isinstance(request.content, str) else json.dumps(request.content),
            "importance": request.importance,
            "ts": datetime.now(UTC).isoformat(),
        })

        pipe = self._redis.pipeline()
        pipe.lpush(key, record)
        pipe.ltrim(key, 0, _HOT_MAX - 1)
        pipe.expire(key, _HOT_TTL_S)
        await pipe.execute()
        return key

    async def _write_warm(self, request: MemoryWriteRequest) -> str | None:
        """Qdrant warm tier — full-precision embedding vectors."""
        from services.ml.embeddings import EmbeddingService
        from infrastructure.config import settings
        from infrastructure.memory.qdrant_client import qdrant_client
        
        warm_id = str(uuid.uuid4())
        content_str = request.content if isinstance(request.content, str) else json.dumps(request.content)
        
        # 1. Generate embedding
        embedder = EmbeddingService(settings.EMBEDDING_MODEL)
        vector = await embedder.embed(content_str)
        
        # 2. Upsert to Qdrant
        await qdrant_client.upsert(
            collection_name="butler_memories",
            points=[{
                "id": warm_id,
                "vector": vector,
                "payload": {
                    "account_id": request.account_id,
                    "memory_type": request.memory_type,
                    "content": content_str,
                    "importance": request.importance,
                    "ts": datetime.now(UTC).isoformat(),
                }
            }]
        )
        return warm_id

    async def _write_graph(self, request: MemoryWriteRequest) -> str | None:
        """Graph tier — Identity and relationship linkage."""
        if self._graph_repo is None:
            logger.debug("graph_tier_skipped", reason="no_graph_repo_injected")
            return None

        account_uuid = uuid.UUID(request.account_id)
        content = request.content
        if isinstance(content, dict) and "name" in content:
            entity = await self._graph_repo.upsert_entity(
                account_id=account_uuid,
                entity_type=content.get("type", "ENTITY"),
                name=content["name"],
                summary=content.get("summary"),
                metadata=content.get("metadata"),
            )
            return str(entity.id)

        return None

    async def _write_struct(self, request: MemoryWriteRequest) -> str:
        """PostgreSQL canonical storage — respects archival policy."""
        # 1. Archive superseded facts if applicable
        if request.metadata.get("supersedes"):
            old_id = uuid.UUID(request.metadata["supersedes"])
            await self._archive_record(request.account_id, old_id)

        # 2. Create new record
        entry = MemoryEntry(
            id=uuid.uuid4(),
            account_id=uuid.UUID(request.account_id),
            memory_type=request.memory_type,
            content=request.content,
            importance=request.importance,
            source=request.metadata.get("source", "conversation"),
            session_id=request.session_id,
            status=MemoryStatus.ACTIVE,
            valid_from=datetime.now(UTC),
            metadata_col=request.metadata
        )
        self._db.add(entry)
        await self._db.flush()
        return str(entry.id)

    async def _write_cold(self, request: MemoryWriteRequest) -> str:
        """Compressed cold storage tier (asynchronous)."""
        from services.ml.embeddings import EmbeddingService
        from infrastructure.config import settings

        cold_id = str(uuid.uuid4())
        content_str = request.content if isinstance(request.content, str) else json.dumps(request.content)

        # 1. Generate embedding
        embedder = EmbeddingService(settings.EMBEDDING_MODEL)
        vector = await embedder.embed(content_str)

        # 2. Index into cold store (IColdStore.index is sync but thread-safe)
        self._cold.index(
            entry_id=cold_id,
            embedding=vector,
            payload={
                "account_id": request.account_id,
                "memory_type": request.memory_type,
                "content": content_str,
                "importance": request.importance,
            }
        )
        return cold_id

    async def _archive_record(self, account_id: str, entry_id: uuid.UUID):
        """Mark a record as DEPRECATED in Postgres. Also archives in graph repo if injected."""
        from sqlalchemy import update

        # 1. Update Postgres
        stmt = update(MemoryEntry).where(
            MemoryEntry.id == entry_id,
            MemoryEntry.account_id == uuid.UUID(account_id),
        ).values(
            status=MemoryStatus.DEPRECATED,
            valid_until=datetime.now(UTC),
        )
        await self._db.execute(stmt)

        # 2. Update graph repo — only if injected
        if self._graph_repo is not None:
            await self._graph_repo.archive_entity(uuid.UUID(account_id), entry_id)

    async def archive(self, account_id: str, entry_id: Any) -> None:  # IMemoryWriteStore
        """Satisfy IMemoryWriteStore.archive contract."""
        await self._archive_record(account_id, uuid.UUID(str(entry_id)))

    async def _write_hermes_session_sidecar(self, request: MemoryWriteRequest) -> None:
        """Write a copy to Hermes SessionDB via Redis for FTS replay.

        This is a secondary copy — Butler HOT tier is canonical.
        If Hermes SessionDB is unavailable, log and continue; never fail the write.
        """
        if not request.session_id:
            return
        try:
            key = f"hermes:session:messages:{request.session_id}"
            record = json.dumps({
                "content": request.content if isinstance(request.content, str) else json.dumps(request.content),
                "ts": datetime.now(UTC).isoformat(),
            })
            pipe = self._redis.pipeline()
            pipe.lpush(key, record)
            pipe.ltrim(key, 0, 99)
            pipe.expire(key, _HOT_TTL_S)
            await pipe.execute()
        except Exception as exc:
            logger.warning("hermes_session_sidecar_failed", error=str(exc))
