from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, cast

import structlog
from redis.asyncio import Redis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from domain.memory.contracts import IColdStore, IMemoryWriteStore
from domain.memory.models import MemoryEntry, MemoryStatus
from domain.memory.write_policy import (
    MemoryWritePolicy,
    MemoryWriteRequest,
    StorageTier,
    WriteRoute,
)
from domain.ml.contracts import EmbeddingContract
from infrastructure.config import settings
from infrastructure.memory.qdrant_client import qdrant_client
from services.memory.knowledge_repo_contract import KnowledgeRepoContract
from services.tenant.namespace import get_tenant_namespace

if TYPE_CHECKING:
    from services.memory.consent_manager import ConsentManager

logger = structlog.get_logger(__name__)

_HOT_TTL_S = 86_400
_HOT_MAX = 50
_HERMES_SIDECAR_MAX = 100
_HOT_SCHEMA_VERSION = "v1"


@dataclass(slots=True)
class MemoryWriteResult:
    success: bool
    tiers_written: list[StorageTier]
    entry_id: str | None = None
    warm_id: str | None = None
    cold_id: str | None = None
    graph_id: str | None = None
    error: str | None = None
    warnings: list[str] | None = None


class ButlerMemoryStore(IMemoryWriteStore):
    """Policy-gated multi-tier memory write dispatcher.

    Important operational rule:
    - This class must remain request-scoped or unit-of-work scoped if it owns
      an AsyncSession. Do not promote it to a process singleton.
    """

    def __init__(
        self,
        *,
        db: AsyncSession,
        redis: Redis,
        embedder: EmbeddingContract,
        cold_store: IColdStore,
        graph_repo: KnowledgeRepoContract | None = None,
        policy: MemoryWritePolicy | None = None,
        consent_manager: ConsentManager | None = None,
    ) -> None:
        self._db = db
        self._redis = redis
        self._embedder = embedder
        self._cold = cold_store
        self._graph_repo = graph_repo
        self._consent = consent_manager
        self._policy = policy or MemoryWritePolicy(consent_manager=consent_manager)

    async def write(
        self,
        request: MemoryWriteRequest,
        tenant_id: str,  # Required for multi-tenant isolation
    ) -> MemoryWriteResult:
        """Route and write a memory item according to Butler policy.

        Args:
            tenant_id: Required tenant UUID for multi-tenant isolation
        """
        route = self._policy.route(request)

        tiers_written: list[StorageTier] = []
        warnings: list[str] = []
        errors: list[str] = []

        entry_id: str | None = None
        warm_id: str | None = None
        cold_id: str | None = None
        graph_id: str | None = None

        # 1. Check for PII and scrub if necessary before any tier writes
        if self._consent is not None and request.account_id:
            try:
                acc_uuid = uuid.UUID(request.account_id)
                if isinstance(request.content, str):
                    original_content = request.content
                    scrubbed_content = await self._consent.scrub_text(acc_uuid, original_content)
                    if scrubbed_content != original_content:
                        request.content = scrubbed_content
                        request.is_scrubbed = True
                        logger.info("memory_content_scrubbed", account_id=request.account_id)
                elif isinstance(request.content, dict):
                    # For dicts, we attempt to scrub values recursively if they are strings
                    async def _scrub_dict(d: dict) -> dict:
                        new_d = {}
                        for k, v in d.items():
                            if isinstance(v, str):
                                new_d[k] = await self._consent.scrub_text(acc_uuid, v)
                            elif isinstance(v, dict):
                                new_d[k] = await _scrub_dict(v)
                            else:
                                new_d[k] = v
                        return new_d

                    original_json = json.dumps(request.content)
                    request.content = await _scrub_dict(request.content)
                    if json.dumps(request.content) != original_json:
                        request.is_scrubbed = True
                        logger.info("memory_content_dict_scrubbed", account_id=request.account_id)
            except Exception as exc:
                logger.warning("scrubbing_failed", error=str(exc))
                warnings.append(f"scrubbing_failed: {exc}")

        for tier in route.tiers:
            # 2. Gate Graph writes based on consent
            if tier == StorageTier.GRAPH and self._consent is not None:
                try:
                    if not self._consent.can_commit_to_graph(uuid.UUID(request.account_id)):
                        warning = f"Graph commit denied for account {request.account_id}"
                        warnings.append(warning)
                        continue
                except Exception:
                    pass

            if not self._policy.enforce_pii_rules(request, tier):
                warning = (
                    f"PII-gated write blocked for tier={tier.value}, "
                    f"memory_type={request.memory_type}"
                )
                warnings.append(warning)
                logger.warning(
                    "memory_pii_blocked",
                    tier=tier.value,
                    memory_type=request.memory_type,
                    account_id=request.account_id,
                )
                continue

            try:
                tier_result = await self._write_tier(
                    tier=tier,
                    request=request,
                    route=route,
                    tenant_id=tenant_id,
                )

                if tier_result is not None:
                    tiers_written.append(tier)

                if tier == StorageTier.STRUCT:
                    entry_id = tier_result
                elif tier == StorageTier.WARM:
                    warm_id = tier_result
                elif tier == StorageTier.COLD:
                    cold_id = tier_result
                elif tier == StorageTier.GRAPH:
                    graph_id = tier_result

            except Exception as exc:  # boundary layer
                error_text = f"{tier.value}: {exc}"
                errors.append(error_text)
                logger.exception(
                    "memory_tier_write_failed",
                    tier=tier.value,
                    memory_type=request.memory_type,
                    account_id=request.account_id,
                    error=str(exc),
                )

        if self._policy.should_write_hermes_session_db(request):
            try:
                await self._write_hermes_session_sidecar(request)
            except Exception as exc:  # never fail the primary write path
                warnings.append(f"hermes_session_sidecar_failed: {exc}")
                logger.warning("hermes_session_sidecar_failed", error=str(exc))

        if errors and not tiers_written:
            return MemoryWriteResult(
                success=False,
                tiers_written=[],
                entry_id=entry_id,
                warm_id=warm_id,
                cold_id=cold_id,
                graph_id=graph_id,
                error="; ".join(errors),
                warnings=warnings or None,
            )

        logger.info(
            "memory_written",
            account_id=request.account_id,
            memory_type=request.memory_type,
            tiers=[tier.value for tier in tiers_written],
            entry_id=entry_id,
            warm_id=warm_id,
            cold_id=cold_id,
            graph_id=graph_id,
            warnings=warnings,
        )

        return MemoryWriteResult(
            success=True,
            tiers_written=tiers_written,
            entry_id=entry_id,
            warm_id=warm_id,
            cold_id=cold_id,
            graph_id=graph_id,
            warnings=warnings or None,
        )

    async def archive(self, account_id: str, entry_id: Any) -> None:
        """Satisfy IMemoryWriteStore.archive contract."""
        await self._archive_record(account_id=account_id, entry_id=uuid.UUID(str(entry_id)))

    async def _write_tier(
        self,
        *,
        tier: StorageTier,
        request: MemoryWriteRequest,
        route: WriteRoute,
        tenant_id: str,  # Required for multi-tenant isolation
    ) -> str | None:
        del route  # reserved for future audit/explainability expansion

        if tier == StorageTier.HOT:
            return await self._write_hot(request, tenant_id)
        if tier == StorageTier.WARM:
            return await self._write_warm(request, tenant_id)
        if tier == StorageTier.COLD:
            return await self._write_cold(request, tenant_id)
        if tier == StorageTier.STRUCT:
            return await self._write_struct(request, tenant_id)
        if tier == StorageTier.GRAPH:
            return await self._write_graph(request, tenant_id)

        logger.warning("unknown_storage_tier", tier=str(tier))
        return None

    async def _write_hot(self, request: MemoryWriteRequest, tenant_id: str) -> str:
        """Redis rolling hot window for session-local context."""
        if not request.session_id:
            return "no_session"

        key = self._hot_key(request.account_id, request.session_id, tenant_id)
        now_iso = datetime.now(UTC).isoformat()

        record = {
            "schema_version": _HOT_SCHEMA_VERSION,
            "entry_id": str(uuid.uuid4()),
            "memory_type": request.memory_type,
            "session_id": request.session_id,
            "account_id": request.account_id,
            "content": self._jsonable_content(request.content),
            "importance": request.importance,
            "source": self._safe_metadata(request.metadata).get("source", "conversation"),
            "sensitivity": self._safe_metadata(request.metadata).get("sensitivity", "unknown"),
            "redacted": bool(self._safe_metadata(request.metadata).get("redacted", False)),
            "ts": now_iso,
        }

        async with self._redis.pipeline(transaction=True) as pipe:
            await (
                pipe.lpush(key, json.dumps(record))
                .ltrim(key, 0, _HOT_MAX - 1)
                .expire(key, _HOT_TTL_S)
                .execute()
            )

        return key

    async def _write_warm(self, request: MemoryWriteRequest, tenant_id: str) -> str | None:
        """Warm semantic tier in Qdrant."""
        if settings.VECTOR_STORE_BACKEND != "qdrant":
            return None

        warm_id = str(uuid.uuid4())
        content_str = self._content_to_text(request.content)
        vector = await self._embedder.embed(content_str)

        if qdrant_client._client is None:
            await qdrant_client.connect()

        client = cast(Any, qdrant_client.client)
        payload = {
            "tenant_id": tenant_id,
            "account_id": request.account_id,
            "memory_type": request.memory_type,
            "session_id": request.session_id,
            "importance": request.importance,
            "content": content_str,
            "ts": datetime.now(UTC).isoformat(),
            "metadata": self._safe_metadata(request.metadata),
        }

        await client.upsert(
            collection_name="butler_memories",
            points=[
                {
                    "id": warm_id,
                    "vector": vector,
                    "payload": payload,
                }
            ],
        )

        return warm_id

    async def _write_cold(self, request: MemoryWriteRequest, tenant_id: str) -> str:
        """Cold semantic tier.

        Uses a thread hop because many cold-store backends are sync and can block.
        """
        cold_id = str(uuid.uuid4())
        content_str = self._content_to_text(request.content)
        vector = await self._embedder.embed(content_str)

        payload = {
            "tenant_id": tenant_id,
            "account_id": request.account_id,
            "memory_type": request.memory_type,
            "session_id": request.session_id,
            "importance": request.importance,
            "content": content_str,
            "metadata": self._safe_metadata(request.metadata),
            "ts": datetime.now(UTC).isoformat(),
        }

        await asyncio.to_thread(
            self._index_cold_sync,
            cold_id,
            vector,
            payload,
        )
        return cold_id

    def _index_cold_sync(
        self,
        entry_id: str,
        embedding: list[float],
        payload: dict[str, Any],
    ) -> None:
        """Thread-hop target for cold indexing."""
        if hasattr(self._cold, "index"):
            self._cold.index(entry_id=entry_id, embedding=embedding, payload=payload)
            return

        if hasattr(self._cold, "add_sync"):
            self._cold.add_sync(entry_id=entry_id, embedding=embedding, payload=payload)
            return

        raise AttributeError(
            "Injected cold store does not expose supported sync index method "
            "(expected 'index' or 'add_sync')."
        )

    async def _write_struct(self, request: MemoryWriteRequest, tenant_id: str) -> str:
        """Canonical relational write."""
        if request.metadata.get("supersedes"):
            superseded_id = uuid.UUID(str(request.metadata["supersedes"]))
            await self._archive_record(
                account_id=request.account_id,
                entry_id=superseded_id,
            )

        metadata = self._safe_metadata(request.metadata)

        embedding: list[float] | None = None
        if settings.VECTOR_STORE_BACKEND == "postgres":
            content_str = self._content_to_text(request.content)
            embedding = await self._embedder.embed(content_str)

        entry = MemoryEntry(
            id=uuid.uuid4(),
            tenant_id=uuid.UUID(tenant_id),
            account_id=uuid.UUID(request.account_id),
            memory_type=request.memory_type,
            content=self._jsonable_content(request.content),
            embedding=embedding,
            importance=request.importance,
            source=str(metadata.get("source", "conversation")),
            session_id=request.session_id,
            status=MemoryStatus.ACTIVE,
            valid_from=datetime.now(UTC),
            metadata_col=metadata,
        )

        self._db.add(entry)
        await self._db.flush()

        return str(entry.id)

    async def _write_graph(self, request: MemoryWriteRequest, tenant_id: str) -> str | None:
        """Graph write for entities and relationships."""
        if self._graph_repo is None:
            logger.debug("graph_tier_skipped", reason="no_graph_repo_injected")
            return None

        account_uuid = uuid.UUID(request.account_id)
        uuid.UUID(tenant_id)
        content = request.content

        if not isinstance(content, dict):
            return None

        if {"source_name", "target_name", "relation"} <= set(content.keys()):
            source_name = str(content["source_name"])
            target_name = str(content["target_name"])
            relation = str(content["relation"])

            source_entity = await self._graph_repo.upsert_entity(
                account_id=account_uuid,
                entity_type=str(content.get("source_type", "ENTITY")),
                name=source_name,
                summary=content.get("source_summary"),
                metadata=content.get("source_metadata"),
            )
            target_entity = await self._graph_repo.upsert_entity(
                account_id=account_uuid,
                entity_type=str(content.get("target_type", "ENTITY")),
                name=target_name,
                summary=content.get("target_summary"),
                metadata=content.get("target_metadata"),
            )

            await self._graph_repo.upsert_edge(
                account_id=account_uuid,
                source_id=source_entity.id,
                target_id=target_entity.id,
                relation=relation,
            )
            return f"{source_entity.id}:{target_entity.id}:{relation}"

        if "name" in content:
            entity = await self._graph_repo.upsert_entity(
                account_id=account_uuid,
                entity_type=str(content.get("type", "ENTITY")),
                name=str(content["name"]),
                summary=content.get("summary"),
                metadata=content.get("metadata"),
            )
            return str(entity.id)

        return None

    async def _archive_record(self, *, account_id: str, entry_id: uuid.UUID) -> None:
        """Soft-archive a relational record and mirror archive to graph if supported."""
        stmt = (
            update(MemoryEntry)
            .where(
                MemoryEntry.id == entry_id,
                MemoryEntry.account_id == uuid.UUID(account_id),
            )
            .values(
                status=MemoryStatus.DEPRECATED,
                valid_until=datetime.now(UTC),
            )
        )
        await self._db.execute(stmt)

        if self._graph_repo is not None:
            try:
                await self._graph_repo.archive_entity(uuid.UUID(account_id), entry_id)
            except Exception:
                logger.exception(
                    "graph_archive_mirror_failed",
                    account_id=account_id,
                    entry_id=str(entry_id),
                )

    async def _write_hermes_session_sidecar(self, request: MemoryWriteRequest) -> None:
        """Secondary session-message copy for Hermes compatibility."""
        if not request.session_id:
            return

        key = f"hermes:session:messages:{request.session_id}"
        record = {
            "content": self._jsonable_content(request.content),
            "ts": datetime.now(UTC).isoformat(),
        }

        async with self._redis.pipeline(transaction=True) as pipe:
            await (
                pipe.lpush(key, json.dumps(record))
                .ltrim(key, 0, _HERMES_SIDECAR_MAX - 1)
                .expire(key, _HOT_TTL_S)
                .execute()
            )

    def _hot_key(self, account_id: str, session_id: str, tenant_id: str | None = None) -> str:
        # P0 hardening: Use TenantNamespace for Redis key formatting
        namespace = get_tenant_namespace(tenant_id or account_id)
        return f"{namespace.prefix}:memory:hot:{session_id}"

    def _content_to_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False, sort_keys=True)

    def _jsonable_content(self, content: Any) -> Any:
        if isinstance(content, (dict, list, str, int, float, bool)) or content is None:
            return content
        return self._content_to_text(content)

    def _safe_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        def _serialize(value: Any) -> Any:
            if isinstance(value, Enum):
                return value.value
            if isinstance(value, uuid.UUID):
                return str(value)
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, dict):
                return {str(k): _serialize(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_serialize(item) for item in value]
            if isinstance(value, tuple):
                return [_serialize(item) for item in value]
            if isinstance(value, set):
                return [_serialize(item) for item in sorted(value, key=str)]
            return value

        return cast(dict[str, Any], _serialize(dict(metadata or {})))
