import json
import logging
import uuid

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
from domain.ml.contracts import EmbeddingContract
from services.memory.anchored_summarizer import AnchoredSummarizer
from services.memory.context_builder import ContextBuilder
from services.memory.evolution_engine import MemoryEvolutionEngine
from services.memory.graph_extraction import KnowledgeExtractionEngine
from services.memory.knowledge_repo_contract import KnowledgeRepoContract
from services.memory.resolution_engine import EntityResolutionEngine
from services.memory.retrieval import RetrievalFusionEngine
from services.memory.understanding_service import UnderstandingService

logger = logging.getLogger(__name__)

class MemoryService(MemoryServiceContract):
    """Butler's Orchestrated Memory Service (Oracle-Grade).

    Depends only on domain contracts — no concrete service imports.
    Episodic engine is optional at construction (set via .episodic = engine
    after building the circular dependency in deps.py).
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
        store: IMemoryWriteStore,           # was ButlerMemoryStore
        summarizer: AnchoredSummarizer,     # Context compression engine
        episodic: IMemoryRecorder | None = None,  # optional — attached post-construction
        consent_manager: 'ConsentManager' = None, # Privacy/Scrubbing Boundary
    ):
        self._db = db
        self._redis = redis
        self._embedder = embedder
        self._retrieval = retrieval
        self._evolution = evolution
        self._resolution = resolution
        self._episodic = episodic          # may be None until .episodic = set
        self._understanding = understanding
        self._context_builder = context_builder
        self._knowledge_repo = knowledge_repo
        self._extraction = extraction
        self._store = store
        self._summarizer = summarizer
        self._consent = consent_manager

    @property
    def episodic(self) -> IMemoryRecorder | None:
        return self._episodic

    @episodic.setter
    def episodic(self, engine: IMemoryRecorder) -> None:
        """Attach EpisodicMemoryEngine after construction (circular dep resolution)."""
        self._episodic = engine

    async def store(self, account_id: str, memory_type: str, content: dict, **kwargs) -> MemoryEntry:
        """Store memory with evolution logic (reconciliation)."""
        text_repr = json.dumps(content) if isinstance(content, dict) else str(content)

        # 1. Fact Reconciliation
        decision = await self._evolution.reconcile(account_id, text_repr)

        if decision.action == MemoryAction.CONTRADICT:
            logger.warning(f"Memory contradiction detected for {account_id}: {decision.reason}")
            # Still store it but flag as conflicting in metadata
            kwargs.setdefault("metadata", {})["conflicts_with"] = decision.target_memory_id

        # 2. Unified Dispatcher Write (Multi-tier)
        from domain.memory.write_policy import MemoryWriteRequest

        write_req = MemoryWriteRequest(
            memory_type=memory_type,
            content=content,
            account_id=account_id,
            session_id=kwargs.get("session_id"),
            importance=kwargs.get("importance", 0.5),
            metadata={
                **kwargs,
                "supersedes": str(decision.target_memory_id) if decision.action == MemoryAction.SUPERSEDE else None,
                "action_reason": decision.reason,
                "reconciliation": decision.model_dump()
            }
        )

        result = await self._store.write(write_req)
        await self._db.commit()

        # 3. Return the STRUCT record for immediate API feedback
        if result.entry_id:
            from sqlalchemy import select
            stmt = select(MemoryEntry).where(MemoryEntry.id == uuid.UUID(result.entry_id))
            res = await self._db.execute(stmt)
            return res.scalar_one()

        return None

    async def recall(self, account_id: str, query: str, memory_types: list = None, limit: int = 10) -> list[MemoryEntry]:
        scored_memories = await self._retrieval.search(account_id, query, memory_types, limit)
        return [sm.memory for sm in scored_memories]

    async def store_turn(self, account_id: str, session_id: str, role: str, content: str, **kwargs) -> ConversationTurn:
        """Store conversation turn and trigger understanding analysis."""
        turn = ConversationTurn(
            account_id=uuid.UUID(account_id),
            session_id=session_id,
            role=role,
            content=content,
            turn_index=kwargs.get("turn_index", 0),
            intent=kwargs.get("intent"),
            tool_calls=kwargs.get("tool_calls"),
            metadata_col=kwargs.get("metadata", {}),
        )
        self._db.add(turn)

        # Trigger background understanding (non-blocking in a real system, here sequential for Phase 11)
        await self._understanding.analyze_turn(account_id, role, content)

        await self._db.commit()
        return turn

    async def compress_session(self, account_id: str, session_id: str) -> str:
        """Trigger anchored iterative summarization for a long session history."""
        # 1. Fetch current history (all turns)
        history = await self.get_session_history(account_id, session_id, limit=100)
        if not history:
            return ""

        # 2. Fetch existing summary from Redis
        raw_session = await self._redis.get(f"butler:session:{session_id}")
        existing_summary = None
        if raw_session:
            existing_summary = json.loads(raw_session).get("running_summary")

        # 3. Generate or merge
        turn_dicts = [{"role": t.role, "content": t.content} for t in history]

        if not existing_summary:
            # First compression: summarize everything
            new_summary = await self._summarizer.generate_initial_summary(turn_dicts)
        else:
            # Subsequent compression: only merge the LATEST turns (e.g. last 10)
            # Actually, standard strategy is to merge the turns that are about to be archived.
            # For simplicity in this implementation, we merge the turns that haven't been 'summarized' yet.
            # In Phase 11, we pass the full tail.
            new_summary = await self._summarizer.merge_summary(existing_summary, turn_dicts[-10:])

        # 4. Update Redis
        if new_summary:
            # We use a shortcut to update session data in Redis
            raw = await self._redis.get(f"butler:session:{session_id}")
            if raw:
                data = json.loads(raw)
                data["running_summary"] = new_summary
                _SESSION_TTL_S = 86400 * 7 # 7 days
                await self._redis.setex(f"butler:session:{session_id}", _SESSION_TTL_S, json.dumps(data))
                logger.info("session_compressed", session_id=session_id)

        return new_summary

    async def get_session_history(self, account_id: str, session_id: str, limit: int = 50) -> list[ConversationTurn]:
        stmt = select(ConversationTurn).where(
            ConversationTurn.account_id == uuid.UUID(account_id),
            ConversationTurn.session_id == session_id
        ).order_by(ConversationTurn.turn_index.asc()).limit(limit)

        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def build_context(self, account_id: str, query: str, session_id: str) -> ContextPack:
        """Assembles the high-fidelity context pack for the Orchestrator."""
        acc_id = uuid.UUID(account_id)

        # 1. Broad Retrieval
        scored_mems = await self._retrieval.search(account_id, query)

        # 2. History (Recent turns)
        history = await self.get_session_history(account_id, session_id, limit=20)

        # 3. Session Summary (Anchor) — Rule #170 deterministic retrieval
        raw_session = await self._redis.get(f"butler:session:{session_id}")
        summary_anchor = None
        if raw_session:
            summary_anchor = json.loads(raw_session).get("running_summary")

        # 4. Preferences & Dislikes
        stmt_pref = select(ExplicitPreference).where(ExplicitPreference.account_id == acc_id)
        res_pref = await self._db.execute(stmt_pref)
        preferences = list(res_pref.scalars().all())

        # 5. Constraints
        stmt_con = select(UserConstraint).where(UserConstraint.account_id == acc_id, UserConstraint.active)
        res_con = await self._db.execute(stmt_con)
        constraints = list(res_con.scalars().all())

        # 6. Entity Resolving
        resolved_entity = await self._resolution.resolve(account_id, query)
        entities = [resolved_entity] if resolved_entity else []

        return self._context_builder.assemble(
            history=history,
            memories=scored_mems,
            preferences=preferences,
            entities=entities,
            constraints=constraints,
            summary_anchor=summary_anchor
        )

    async def update_entity(self, account_id: str, entity_name: str, facts: dict) -> MemoryEntry:
        # High-level entity update
        await self._knowledge_repo.upsert_entity(uuid.UUID(account_id), "ORG", entity_name, metadata=facts)
        return await self.store(account_id, "entity", {"name": entity_name, "facts": facts}, tags=["entity"])

    async def set_preference(self, account_id: str, key: str, value: str, confidence: float) -> MemoryEntry:
        # This now routes through store to trigger evolution if needed
        return await self.store(account_id, "preference", {"key": key, "value": value}, confidence=confidence)

    async def add_relationship(self, account_id: str, source_name: str, target_name: str, relation: str):
        """Link two entities in the social graph."""
        acc_id = uuid.UUID(account_id)

        # 1. Resolve source and target
        source = await self._resolution.resolve(account_id, source_name)
        target = await self._resolution.resolve(account_id, target_name)

        if not source or not target:
            logger.warning(f"Failed to resolve {source_name} or {target_name} for relative link.")
            return

        # 2. Upsert edge
        await self._knowledge_repo.upsert_edge(acc_id, source.id, target.id, relation)
        logger.info(f"Created relationship: {source.name} --{relation}--> {target.name}")

    async def end_session(self, account_id: str, session_id: str):
        """End a session, capture episode, and trigger graph distillation."""
        episode = None

        # 1. Capture Episode — only if episodic engine is attached
        if self._episodic is not None:
            episode = await self._episodic.capture_episode(account_id, session_id)
        else:
            logger.warning("end_session called but no episodic engine attached", extra={"account_id": account_id})
            return episode

        # 2. Trigger graph extraction from the full session log
        history = await self.get_session_history(account_id, session_id)
        full_text = "\n".join([f"{t.role}: {t.content}" for t in history])

        acc_uuid = uuid.UUID(account_id)

        # 3. Apply Consent & Scrubbing Boundary before neo4j structural logic
        if self._consent:
            if not self._consent.can_commit_to_graph(acc_uuid):
                logger.info(f"Graph commit denied by ConsentManager policy for {account_id}")
                return episode
            full_text = await self._consent.scrub_episodic_stream(acc_uuid, full_text)

        await self._extraction.extract_and_store(
            account_id=account_id,
            text=full_text,
            source_id=episode.id,
            source_type="episode"
        )

        return episode
