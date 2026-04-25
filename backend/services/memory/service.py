from __future__ import annotations

import json
import logging
import uuid
from typing import TYPE_CHECKING, Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.memory.contracts import (
    ContextPack,
    IMemoryRecorder,
    IMemoryWriteStore,
    MemoryServiceContract,
)
from domain.memory.evolution import MemoryAction
from domain.memory.models import (
    ConversationTurn,
    ExplicitPreference,
    MemoryEntry,
    UserConstraint,
)
from domain.memory.policy import MemoryPolicy
from domain.ml.contracts import EmbeddingContract
from domain.orchestration.router import OperationRouter
from services.memory.anchored_summarizer import AnchoredSummarizer
from services.memory.context_builder import ContextBuilder
from services.memory.evolution_engine import MemoryEvolutionEngine
from services.memory.graph_extraction import KnowledgeExtractionEngine
from services.memory.knowledge_repo_contract import KnowledgeRepoContract
from services.memory.resolution_engine import EntityResolutionEngine
from services.memory.retrieval import RetrievalFusionEngine
from services.memory.understanding_service import UnderstandingService
from services.tenant.namespace import get_tenant_namespace

if TYPE_CHECKING:
    from services.memory.consent_manager import ConsentManager

logger = logging.getLogger(__name__)

_SESSION_REDIS_TTL_SECONDS = 86400 * 7
_DEFAULT_COMPRESS_FETCH_LIMIT = 100
_DEFAULT_HISTORY_LIMIT = 50
_DEFAULT_CONTEXT_HISTORY_LIMIT = 20


class MemoryService(MemoryServiceContract):
    """Butler orchestrated memory service.

    This is the canonical integration layer for:
    - conversational turn recording
    - retrieval + context assembly
    - reconciliation-aware storage
    - anchored session summarization
    - graph extraction at session end
    - preference / relationship convenience APIs

    Design rules:
    - storage backends are never written directly from callers
    - all durable writes route through IMemoryWriteStore
    - session compression is summary-anchor based
    - graph commits are consent-gated
    """

    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        embedder: EmbeddingContract,
        retrieval: RetrievalFusionEngine,
        evolution: MemoryEvolutionEngine,
        resolution: EntityResolutionEngine,
        understanding: UnderstandingService,
        context_builder: ContextBuilder,
        knowledge_repo: KnowledgeRepoContract,
        extraction: KnowledgeExtractionEngine,
        store: IMemoryWriteStore,
        summarizer: AnchoredSummarizer,
        episodic: IMemoryRecorder | None = None,
        consent_manager: ConsentManager | None = None,
        memory_policy: MemoryPolicy | None = None,
        operation_router: OperationRouter | None = None,
    ) -> None:
        self._db = db
        self._redis = redis
        self._embedder = embedder
        self._retrieval = retrieval
        self._evolution = evolution
        self._resolution = resolution
        self._episodic = episodic
        self._understanding = understanding
        self._context_builder = context_builder
        self._knowledge_repo = knowledge_repo
        self._extraction = extraction
        self._store = store
        self._summarizer = summarizer
        self._consent = consent_manager
        self._memory_policy = memory_policy or MemoryPolicy.default()
        self._operation_router = operation_router

    @property
    def episodic(self) -> IMemoryRecorder | None:
        return self._episodic

    @episodic.setter
    def episodic(self, engine: IMemoryRecorder) -> None:
        self._episodic = engine

    async def store(
        self,
        account_id: str,
        memory_type: str,
        content: dict[str, Any] | str,
        tenant_id: str | None = None,
        **kwargs: Any,
    ) -> MemoryEntry | None:
        """Store memory through reconciliation-aware write routing.

        Args:
            tenant_id: Tenant scope for multi-tenant isolation. Defaults to
                account_id (single-tenant-per-account fallback).
        """
        effective_tenant_id = tenant_id or account_id

        # Check memory operation admission through router
        if self._operation_router:
            from domain.orchestration.router import AdmissionDecision, OperationRequest, OperationType

            operation_request = OperationRequest(
                operation_type=OperationType.MEMORY_WRITE,
                tenant_id=effective_tenant_id,
                account_id=account_id,
                user_id=kwargs.get("user_id"),
                tool_name=None,
                risk_tier=None,
                estimated_cost=None,
            )

            _, admission = self._operation_router.route(operation_request)
            if admission.decision != AdmissionDecision.ALLOW:
                logger.warning(
                    "memory_write_denied_by_router",
                    extra={
                        "account_id": account_id,
                        "memory_type": memory_type,
                        "reason": admission.reason,
                    },
                )
                return None

        metadata = self._extract_metadata(kwargs)
        text_repr = self._to_text_repr(content)

        try:
            decision = await self._evolution.reconcile(
                account_id=account_id,
                new_fact=text_repr,
                context=metadata.get("reconciliation_context"),
            )

            if decision.action == MemoryAction.CONTRADICT and decision.target_memory_id:
                logger.warning(
                    "memory_contradiction_detected",
                    extra={
                        "account_id": account_id,
                        "memory_type": memory_type,
                        "target_memory_id": str(decision.target_memory_id),
                        "reason": decision.reason,
                    },
                )
                metadata["conflicts_with"] = str(decision.target_memory_id)

            write_metadata = {
                **metadata,
                "action_reason": decision.reason,
                "reconciliation": self._safe_model_dump(decision),
                "supersedes": (
                    str(decision.target_memory_id)
                    if decision.action == MemoryAction.SUPERSEDE and decision.target_memory_id
                    else None
                ),
            }

            from domain.memory.write_policy import MemoryWriteRequest

            write_request = MemoryWriteRequest(
                memory_type=memory_type,
                content=content,
                account_id=account_id,
                session_id=kwargs.get("session_id"),
                importance=float(kwargs.get("importance", 0.5)),
                age_days=float(kwargs.get("age_days", 0.0)),
                provenance=str(kwargs.get("provenance", "conversation")),
                has_pii=bool(kwargs.get("has_pii", False)),
                source=str(kwargs.get("source", "")),
                metadata=write_metadata,
            )

            result = await self._store.write(write_request, tenant_id=effective_tenant_id)
            await self._db.commit()

            if not result.entry_id:
                logger.info(
                    "memory_store_completed_without_struct_entry",
                    extra={
                        "account_id": account_id,
                        "memory_type": memory_type,
                        "tiers_written": [tier.value for tier in result.tiers_written],
                    },
                )
                return None

            stmt = select(MemoryEntry).where(MemoryEntry.id == uuid.UUID(result.entry_id))
            db_result = await self._db.execute(stmt)
            return db_result.scalar_one_or_none()

        except Exception:
            await self._db.rollback()
            logger.exception(
                "memory_store_failed",
                extra={
                    "account_id": account_id,
                    "memory_type": memory_type,
                },
            )
            raise

    async def recall(
        self,
        account_id: str,
        query: str,
        memory_types: list[str] | None = None,
        limit: int = 10,
        tenant_id: str | None = None,
    ) -> list[MemoryEntry]:
        """Recall relevant memories.

        Args:
            tenant_id: Tenant scope for multi-tenant isolation. Defaults to
                account_id (single-tenant-per-account fallback).
        """
        effective_tenant_id = tenant_id or account_id
        scored_memories = await self._retrieval.search(
            account_id=account_id,
            query=query,
            memory_types=memory_types,
            limit=limit,
            tenant_id=effective_tenant_id,
        )
        return [item.memory for item in scored_memories]

    async def get_session_context(
        self,
        account_id: str,
        session_id: str,
        query: str,
    ) -> ContextPack:
        """Assemble the orchestrator-facing context pack."""
        try:
            account_uuid = uuid.UUID(account_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid account_id: {account_id}") from exc

        scored_memories = await self._retrieval.search(account_id=account_id, query=query)
        history = await self.get_session_history(
            account_id=account_id,
            session_id=session_id,
            limit=_DEFAULT_CONTEXT_HISTORY_LIMIT,
        )

        session_payload = await self._get_session_payload(session_id, account_id)
        summary_anchor = self._extract_running_summary(session_payload)

        pref_stmt = select(ExplicitPreference).where(ExplicitPreference.account_id == account_uuid)
        pref_result = await self._db.execute(pref_stmt)
        preferences = list(pref_result.scalars().all())

        constraint_stmt = select(UserConstraint).where(
            UserConstraint.account_id == account_uuid,
            UserConstraint.active.is_(True),
        )
        constraint_result = await self._db.execute(constraint_stmt)
        constraints = list(constraint_result.scalars().all())

        resolved_entity = None
        try:
            resolved_entity = await self._resolution.resolve(account_id, query)
        except Exception:
            logger.exception(
                "entity_resolution_failed_during_context_build",
                extra={"account_id": account_id, "query": query},
            )

        entities = [resolved_entity] if resolved_entity is not None else []

        return self._context_builder.assemble(
            history=history,
            memories=scored_memories,
            preferences=preferences,
            entities=entities,
            constraints=constraints,
            summary_anchor=summary_anchor,
        )

    async def store_turn(
        self,
        account_id: str,
        session_id: str,
        role: str,
        content: str,
        tenant_id: str | None = None,
        **kwargs: Any,
    ) -> ConversationTurn:
        """Persist one conversation turn and trigger understanding analysis.
        
        Args:
            account_id: Account ID
            session_id: Session ID
            role: Message role
            content: Message content
            tenant_id: Tenant ID for multi-tenant isolation (Phase 3)
            **kwargs: Additional metadata
        """
        try:
            account_uuid = uuid.UUID(account_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid account_id: {account_id}") from exc

        metadata = kwargs.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}

        turn = ConversationTurn(
            account_id=account_uuid,
            session_id=session_id,
            role=role,
            content=content,
            turn_index=int(kwargs.get("turn_index", 0)),
            intent=kwargs.get("intent"),
            tool_calls=kwargs.get("tool_calls"),
            metadata_col=metadata,
        )

        try:
            self._db.add(turn)

            if role == "user":
                try:
                    await self._understanding.analyze_turn(account_id, role, content, tenant_id)
                except Exception:
                    logger.exception(
                        "understanding_analysis_failed",
                        extra={
                            "account_id": account_id,
                            "session_id": session_id,
                        },
                    )

            await self._db.commit()
            return turn

        except Exception:
            await self._db.rollback()
            logger.exception(
                "store_turn_failed",
                extra={
                    "account_id": account_id,
                    "session_id": session_id,
                    "role": role,
                },
            )
            raise

    async def compress_session(self, account_id: str, session_id: str) -> str:
        """Generate or update the anchored session summary."""
        history = await self.get_session_history(
            account_id=account_id,
            session_id=session_id,
            limit=_DEFAULT_COMPRESS_FETCH_LIMIT,
        )
        if not history:
            return ""

        turn_dicts = [{"role": turn.role, "content": turn.content} for turn in history]
        session_payload = await self._get_session_payload(session_id, account_id)
        existing_summary = self._extract_running_summary(session_payload)

        try:
            if existing_summary:
                new_summary = await self._summarizer.merge_summary(
                    existing_summary=existing_summary,
                    new_history=turn_dicts[-10:],
                    account_id=account_id,
                )
            else:
                new_summary = await self._summarizer.generate_initial_summary(
                    turn_dicts,
                    account_id=account_id,
                )
        except Exception:
            logger.exception(
                "session_compression_failed",
                extra={
                    "account_id": account_id,
                    "session_id": session_id,
                },
            )
            return existing_summary or ""

        cleaned_summary = (new_summary or "").strip()
        if not cleaned_summary:
            return existing_summary or ""

        session_payload["running_summary"] = cleaned_summary
        await self._set_session_payload(session_id, session_payload, account_id)

        logger.info(
            "session_compressed",
            extra={
                "account_id": account_id,
                "session_id": session_id,
                "summary_len": len(cleaned_summary),
            },
        )
        return cleaned_summary

    async def get_session_history(
        self,
        account_id: str,
        session_id: str,
        limit: int = _DEFAULT_HISTORY_LIMIT,
    ) -> list[ConversationTurn]:
        """Fetch session history in turn order."""
        try:
            account_uuid = uuid.UUID(account_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid account_id: {account_id}") from exc

        stmt = (
            select(ConversationTurn)
            .where(
                ConversationTurn.account_id == account_uuid,
                ConversationTurn.session_id == session_id,
            )
            .order_by(ConversationTurn.turn_index.asc(), ConversationTurn.created_at.asc())
            .limit(limit)
        )

        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def build_context(
        self,
        account_id: str,
        query: str,
        session_id: str,
        tenant_id: str | None = None,
    ) -> ContextPack:
        """Assemble the orchestrator-facing context pack.

        Args:
            tenant_id: Tenant scope for multi-tenant isolation. Defaults to
                account_id (single-tenant-per-account fallback).
        """
        try:
            account_uuid = uuid.UUID(account_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid account_id: {account_id}") from exc

        effective_tenant_id = tenant_id or account_id
        scored_memories = await self._retrieval.search(
            account_id=account_id, query=query, tenant_id=effective_tenant_id
        )
        history = await self.get_session_history(
            account_id=account_id,
            session_id=session_id,
            limit=_DEFAULT_CONTEXT_HISTORY_LIMIT,
        )

        session_payload = await self._get_session_payload(session_id, account_id)
        summary_anchor = self._extract_running_summary(session_payload)

        pref_stmt = select(ExplicitPreference).where(ExplicitPreference.account_id == account_uuid)
        pref_result = await self._db.execute(pref_stmt)
        preferences = list(pref_result.scalars().all())

        constraint_stmt = select(UserConstraint).where(
            UserConstraint.account_id == account_uuid,
            UserConstraint.active.is_(True),
        )
        constraint_result = await self._db.execute(constraint_stmt)
        constraints = list(constraint_result.scalars().all())

        resolved_entity = None
        try:
            resolved_entity = await self._resolution.resolve(account_id, query)
        except Exception:
            logger.exception(
                "entity_resolution_failed_during_context_build",
                extra={"account_id": account_id, "query": query},
            )

        entities = [resolved_entity] if resolved_entity is not None else []

        return self._context_builder.assemble(
            history=history,
            memories=scored_memories,
            preferences=preferences,
            entities=entities,
            constraints=constraints,
            summary_anchor=summary_anchor,
        )

    async def update_entity(
        self,
        account_id: str,
        entity_name: str,
        facts: dict[str, Any],
    ) -> MemoryEntry | None:
        """Convenience helper to update an entity in graph + canonical memory."""
        account_uuid = uuid.UUID(account_id)

        await self._knowledge_repo.upsert_entity(
            account_id=account_uuid,
            entity_type=str(facts.get("type", "ORG")),
            name=entity_name,
            summary=facts.get("summary"),
            metadata=facts,
        )

        return await self.store(
            account_id=account_id,
            memory_type="entity",
            content={"name": entity_name, "facts": facts},
            tags=["entity"],
            metadata={"entity_name": entity_name},
        )

    async def set_preference(
        self,
        account_id: str,
        key: str,
        value: str,
        confidence: float,
    ) -> MemoryEntry | None:
        """Convenience helper for explicit preference storage."""
        return await self.store(
            account_id=account_id,
            memory_type="preference",
            content={"key": key, "value": value},
            confidence=confidence,
            metadata={"preference_key": key},
        )

    async def add_relationship(
        self,
        account_id: str,
        source_name: str,
        target_name: str,
        relation: str,
    ) -> None:
        """Resolve two entities and create a graph relationship."""
        account_uuid = uuid.UUID(account_id)

        source = await self._resolution.resolve(account_id, source_name)
        target = await self._resolution.resolve(account_id, target_name)

        if source is None or target is None:
            logger.warning(
                "relationship_resolution_failed",
                extra={
                    "account_id": account_id,
                    "source_name": source_name,
                    "target_name": target_name,
                    "relation": relation,
                },
            )
            return

        await self._knowledge_repo.upsert_edge(
            account_id=account_uuid,
            source_id=source.id,
            target_id=target.id,
            relation_type=relation,
            metadata={
                "source_name": source_name,
                "target_name": target_name,
                "relation": relation,
            },
        )

        logger.info(
            "relationship_created",
            extra={
                "account_id": account_id,
                "source_id": str(source.id),
                "target_id": str(target.id),
                "relation": relation,
            },
        )

    async def end_session(self, account_id: str, session_id: str, tenant_id: str | None = None) -> Any | None:
        """Capture an episode and optionally distill it into the graph layer.
        
        Args:
            account_id: Account ID
            session_id: Session ID
            tenant_id: Tenant ID for multi-tenant isolation (Phase 3)
        """
        episode = None

        if self._episodic is None:
            logger.warning(
                "end_session_without_episodic_engine",
                extra={
                    "account_id": account_id,
                    "session_id": session_id,
                },
            )
            return None

        episode = await self._episodic.capture_episode(account_id, session_id, tenant_id)

        history = await self.get_session_history(account_id, session_id)
        if not history:
            return episode

        full_text = "\n".join(f"{turn.role}: {turn.content}" for turn in history)
        account_uuid = uuid.UUID(account_id)

        if self._consent is not None:
            try:
                if not self._consent.can_commit_to_graph(account_uuid):
                    logger.info(
                        "graph_commit_denied_by_policy",
                        extra={
                            "account_id": account_id,
                            "session_id": session_id,
                        },
                    )
                    return episode

                full_text = await self._consent.scrub_episodic_stream(account_uuid, full_text)
            except Exception:
                logger.exception(
                    "consent_boundary_failed",
                    extra={
                        "account_id": account_id,
                        "session_id": session_id,
                    },
                )
                return episode

        try:
            await self._extraction.extract_and_store(
                account_id=account_id,
                text=full_text,
                source_id=episode.id if episode is not None else uuid.uuid4(),
                source_type="episode",
            )
        except Exception:
            logger.exception(
                "graph_extraction_failed_at_session_end",
                extra={
                    "account_id": account_id,
                    "session_id": session_id,
                },
            )

        return episode

    async def get_langchain_memory(self, session_id: str, account_id: str) -> Any:
        """Create LangChain-compatible memory adapter for this session."""
        from langchain.memory import ButlerMemoryAdapter

        return ButlerMemoryAdapter(session_id=session_id, account_id=account_id, memory_service=self)

    def _extract_metadata(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        metadata = kwargs.get("metadata", {})
        base = dict(metadata) if isinstance(metadata, dict) else {}

        passthrough_keys = {
            "confidence",
            "tags",
            "source",
            "has_pii",
            "provenance",
            "importance",
            "age_days",
        }
        for key in passthrough_keys:
            if key in kwargs and key not in base:
                base[key] = kwargs[key]

        return base

    def _to_text_repr(self, content: dict[str, Any] | str) -> str:
        if isinstance(content, str):
            return content
        try:
            return json.dumps(content, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return str(content)

    async def _get_session_payload(
        self, session_id: str, tenant_id: str | None = None
    ) -> dict[str, Any]:
        # P0 hardening: Use TenantNamespace for Redis key formatting
        namespace = get_tenant_namespace(tenant_id or "default")
        session_key = namespace.session(session_id)

        raw = await self._redis.get(session_key)
        if raw is None:
            return {}

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="ignore")

        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            logger.warning("invalid_session_payload_json", extra={"session_id": session_id})
            return {}

    async def _set_session_payload(
        self, session_id: str, payload: dict[str, Any], tenant_id: str | None = None
    ) -> None:
        # P0 hardening: Use TenantNamespace for Redis key formatting
        namespace = get_tenant_namespace(tenant_id or "default")
        session_key = namespace.session(session_id)

        await self._redis.setex(
            session_key,
            _SESSION_REDIS_TTL_SECONDS,
            json.dumps(payload, ensure_ascii=False),
        )

    def _extract_running_summary(self, session_payload: dict[str, Any]) -> str | None:
        summary = session_payload.get("running_summary")
        if not isinstance(summary, str):
            return None

        cleaned = summary.strip()
        return cleaned or None

    def _safe_model_dump(self, value: Any) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            dumped = value.model_dump()
            if isinstance(dumped, dict):
                return dumped
        if isinstance(value, dict):
            return value

    async def forget(
        self,
        account_id: str,
        memory_id: str | None = None,
        content_filter: str | None = None,
        tenant_id: str | None = None,
    ) -> int:
        """Forget/delete memories with tenant-scoped filtering (Phase 3: right-to-erasure).

        Args:
            account_id: Account ID
            memory_id: Specific memory ID to delete
            content_filter: Filter by content substring
            tenant_id: Tenant scope for multi-tenant isolation

        Returns:
            Number of memories deleted
        """
        effective_tenant_id = tenant_id or account_id

        if memory_id:
            # Delete specific memory by ID with tenant check
            try:
                mem_uuid = uuid.UUID(memory_id)
            except (ValueError, TypeError):
                return 0

            from domain.memory.models import MemoryStatus

            stmt = (
                delete(MemoryEntry)
                .where(
                    MemoryEntry.id == mem_uuid,
                    MemoryEntry.tenant_id == effective_tenant_id,
                )
            )
            result = await self._db.execute(stmt)
            await self._db.commit()
            return result.rowcount

        if content_filter:
            # Delete memories by content filter with tenant scope
            from domain.memory.models import MemoryStatus

            stmt = (
                delete(MemoryEntry)
                .where(
                    MemoryEntry.account_id == account_id,
                    MemoryEntry.tenant_id == effective_tenant_id,
                    MemoryEntry.content.ilike(f"%{content_filter}%"),
                )
            )
            result = await self._db.execute(stmt)
            await self._db.commit()
            return result.rowcount

        return 0
