import math
import uuid
from dataclasses import dataclass
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.memory.models import ExplicitDislike, ExplicitPreference, MemoryEntry
from domain.ml.contracts import EmbeddingContract
from services.memory.knowledge_repo_contract import KnowledgeRepoContract


def sanitize_and_normalize_embedding(vec: list[float]) -> list[float]:
    """OpenCLAW pattern: clean NaN/Inf values and L2-normalize.

    This prevents pgvector serialization issues and ensures consistent
    similarity search results.
    """
    if not vec:
        return []
    # Clean NaN/Inf
    sanitized = [v if (v is not None and math.isfinite(v)) else 0.0 for v in vec]
    # L2 normalize
    magnitude = math.sqrt(sum(v * v for v in sanitized))
    if magnitude < 1e-10:
        return sanitized
    return [v / magnitude for v in sanitized]


@dataclass
class ScoredMemory:
    memory: MemoryEntry
    score: float
    signals: dict[str, float]  # Breakdown for debugging


class RetrievalFusionEngine:
    """Butler's Oracle-Grade Retrieval Fusion Engine."""

    def __init__(
        self,
        db: AsyncSession,
        embedder: EmbeddingContract,
        knowledge_repo: KnowledgeRepoContract,
        personalization: Any | None = None,
    ):
        self._db = db
        self._embedder = embedder
        self._knowledge_repo = knowledge_repo
        self._personalization = personalization

    async def search(
        self,
        account_id: str,
        query: str,
        memory_types: list[str] | None = None,
        limit: int = 20,
        tenant_id: str | None = None,
    ) -> list[ScoredMemory]:
        """Enhanced retrieval with semantic reranking and temporal decay.

        Improvements:
        - Temporal decay for older memories
        - Semantic reranking using embedding similarity
        - Access count boosting
        - Importance weighting
        - Tenant-scoped filtering (Phase 3: memory isolation)

        Args:
            tenant_id: Tenant scope for multi-tenant isolation. When provided,
                results are filtered to the tenant scope in addition to account_id.
        """
        # Safe UUID parsing - prevents recall failures on invalid account_id
        try:
            acc_id = uuid.UUID(account_id)
            effective_tenant_id = uuid.UUID(tenant_id) if tenant_id else acc_id
        except (ValueError, TypeError):
            # Return empty if account_id is invalid - common cause of "returns 0 results"
            return []

        # Pass both UUID and string for flexible query matching
        acc_id_str = str(acc_id)

        # 1. Broad Retrieval (Candidates) - tenant-scoped
        candidate_pool = await self._get_candidates(
            acc_id, acc_id_str, effective_tenant_id, query, limit * 3
        )

        if not candidate_pool:
            return []

        # 2. Apply temporal decay and access boosting
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        boosted_candidates = []

        for mem in candidate_pool:
            base_score = 0.5  # Base score for all candidates

            # Temporal decay: newer memories get higher scores
            if mem.created_at:
                days_old = (now - mem.created_at).days
                # Exponential decay: 0.98^days (slower decay than evolution engine)
                decay_factor = 0.98 ** min(days_old, 60)  # Cap at 60 days
                base_score *= decay_factor

            # Access count boosting: frequently accessed memories get higher scores
            if mem.access_count > 0:
                access_boost = min(mem.access_count * 0.05, 0.3)  # Cap at 0.3
                base_score += access_boost

            # Importance weighting
            if mem.importance:
                importance_boost = mem.importance * 0.2
                base_score += importance_boost

            boosted_candidates.append((mem, base_score))

        # Sort by boosted scores
        boosted_candidates.sort(key=lambda x: x[1], reverse=True)
        top_candidates = [mem for mem, score in boosted_candidates[: limit * 2]]

        # 3. Personalization Ranker (The Blender)
        # If personalization is available, run the 5-stage pipeline
        if self._personalization:
            query_vector = await self._embedder.embed(query)
            context = {"user_id": account_id, "query": query}

            # Map candidates to PersonalizationEngine.Candidate format
            from services.ml.personalization_engine import Candidate as MLPCandidate

            ml_candidates = [
                MLPCandidate(
                    id=m.id,
                    type="memory",
                    score=score,  # Use boosted score as initial bias
                    metadata={"ts": m.created_at.timestamp() if m.created_at else None},
                )
                for m, score in boosted_candidates[: limit * 2]
            ]

            ranked = await self._personalization.rank(
                query_vector=np.array(query_vector), context=context, candidates=ml_candidates
            )

            # Map back to ScoredMemory
            memory_map = {m.id: m for m in top_candidates}
            return [
                ScoredMemory(memory=memory_map[r.id], score=r.score, signals=r.features)
                for r in ranked[:limit]
                if r.id in memory_map
            ]

        # 4. Fallback: Semantic reranking without personalization
        if top_candidates:
            query_vector = await self._embedder.embed(query)

            # Compute semantic similarity for each candidate

            scored_results = []

            for mem in top_candidates:
                if mem.embedding:
                    # Cosine similarity
                    mem_vec = np.array(mem.embedding)
                    query_vec = np.array(query_vector)

                    # Ensure vectors are normalized
                    mem_norm = np.linalg.norm(mem_vec)
                    query_norm = np.linalg.norm(query_vec)

                    if mem_norm > 0 and query_norm > 0:
                        similarity = np.dot(mem_vec, query_vec) / (mem_norm * query_norm)
                        semantic_score = float(similarity)
                    else:
                        semantic_score = 0.0
                else:
                    semantic_score = 0.0

                # Combine boosted score with semantic similarity
                # Weight: 60% boosted, 40% semantic
                base_score = next(score for m, score in boosted_candidates if m.id == mem.id)
                final_score = 0.6 * base_score + 0.4 * semantic_score

                scored_results.append(
                    ScoredMemory(
                        memory=mem,
                        score=final_score,
                        signals={
                            "temporal_decay": base_score,
                            "semantic_similarity": semantic_score,
                            "access_count": mem.access_count,
                            "importance": mem.importance,
                        },
                    )
                )

            # Sort by final score
            scored_results.sort(key=lambda x: x.score, reverse=True)
            return scored_results[:limit]

        return []

    async def _calculate_fusion_score(
        self,
        memory: MemoryEntry,
        query: str,
        query_embedding: list[float],
        preferences: list[ExplicitPreference],
        dislikes: list[ExplicitDislike],
    ) -> dict:
        """Weighted score calculation from docs/memory.md section 5.1."""
        signals = {"semantic": 0.0, "keyword": 0.0, "graph": 0.0, "preference": 0.0, "dislike": 0.0}

        # Semantic Score (Cosine similarity)
        if memory.embedding is not None:
            # Simple dot product as approximation for normalized vectors
            signals["semantic"] = sum(
                a * b for a, b in zip(query_embedding, memory.embedding, strict=False)
            )

        # Keyword Score (Basic overlap for now)
        if query.lower() in str(memory.content).lower():
            signals["keyword"] = 1.0

        # Preference Match (Boost if memory aligns with preferences)
        for pref in preferences:
            if pref.key.lower() in str(memory.content).lower():
                signals["preference"] = max(signals["preference"], pref.confidence)

        # Dislike Match (Penalty if memory contains disliked items)
        for dislike in dislikes:
            if dislike.key.lower() in str(memory.content).lower():
                signals["dislike"] = dislike.confidence

        # Combine using weights
        # formula: (semantic * 0.4) + (keyword * 0.2) + (graph * 0.2) + (preference * 0.2) - (dislike * 0.5)
        total = (
            (signals["semantic"] * 0.4)
            + (signals["keyword"] * 0.2)
            + (signals["graph"] * 0.2)
            + (signals["preference"] * 0.2)
            - (signals["dislike"] * 0.5)
        )

        return {"total": total, "signals": signals}

    async def _get_candidates(
        self,
        account_id: uuid.UUID,
        account_id_str: str,
        tenant_id: uuid.UUID,
        query: str,
        limit: int,
    ) -> list[MemoryEntry]:
        """Oracle-Grade retrieval with flexible account_id matching and tenant isolation.

        Phase 3: Memory Isolation - Enforce tenant_id filtering in addition to
        account_id filtering to prevent cross-tenant data leakage.
        """
        from sqlalchemy import or_

        from domain.memory.models import (
            KnowledgeEdge,
            KnowledgeEntity,
            MemoryEntityLink,
            MemoryStatus,
        )

        # Primary scan with flexible account_id matching AND tenant_id filtering
        stmt = (
            select(MemoryEntry)
            .where(
                or_(
                    MemoryEntry.account_id == account_id,
                    MemoryEntry.account_id == account_id_str,
                ),
                MemoryEntry.tenant_id == tenant_id,  # Phase 3: tenant isolation
                MemoryEntry.status == MemoryStatus.ACTIVE,
            )
            .limit(limit)
        )
        res = await self._db.execute(stmt)
        candidates = list(res.scalars().all())
        existing_ids: set[uuid.UUID] = {m.id for m in candidates}

        # ── Step 2: 2-hop graph expansion ─────────────────────────────────────
        try:
            query_tokens = {t.lower() for t in query.split() if len(t) > 3}
            if not query_tokens:
                return candidates

            # 2a. Find seed entities whose names overlap with query tokens
            entity_stmt = select(KnowledgeEntity.id).where(
                KnowledgeEntity.account_id == account_id,
                KnowledgeEntity.status == MemoryStatus.ACTIVE,
            )
            entity_res = await self._db.execute(entity_stmt)
            all_entity_ids: list[uuid.UUID] = [row[0] for row in entity_res]

            # Filter in-process: name keyword overlap
            # (Avoids a LIKE-per-token query; acceptable for typical entity counts)
            seed_entity_name_stmt = select(KnowledgeEntity.id, KnowledgeEntity.name).where(
                KnowledgeEntity.id.in_(all_entity_ids)
            )
            seed_res = await self._db.execute(seed_entity_name_stmt)
            seed_ids: set[uuid.UUID] = {
                row[0] for row in seed_res if any(tok in row[1].lower() for tok in query_tokens)
            }

            if not seed_ids:
                return candidates

            # 2b. 1-hop KnowledgeEdge traversal (source → target and target → source)
            edge_stmt = select(KnowledgeEdge.target_id, KnowledgeEdge.source_id).where(
                KnowledgeEdge.account_id == account_id,
                KnowledgeEdge.source_id.in_(seed_ids) | KnowledgeEdge.target_id.in_(seed_ids),
            )
            edge_res = await self._db.execute(edge_stmt)
            neighbour_ids: set[uuid.UUID] = set()
            for target_id, source_id in edge_res:
                neighbour_ids.add(target_id)
                neighbour_ids.add(source_id)
            neighbour_ids.update(seed_ids)  # include seeds themselves

            # 2c. Resolve memory IDs via MemoryEntityLink join table
            link_stmt = select(MemoryEntityLink.memory_id).where(
                MemoryEntityLink.entity_id.in_(neighbour_ids)
            )
            link_res = await self._db.execute(link_stmt)
            linked_memory_ids: set[uuid.UUID] = {
                row[0] for row in link_res if row[0] not in existing_ids
            }

            if not linked_memory_ids:
                return candidates

            # 2d. Fetch the linked MemoryEntry rows (cap at half the primary limit)
            expansion_limit = max(1, limit // 2)
            graph_stmt = (
                select(MemoryEntry)
                .where(
                    MemoryEntry.id.in_(linked_memory_ids),
                    MemoryEntry.account_id == account_id,
                    MemoryEntry.status == MemoryStatus.ACTIVE,
                )
                .limit(expansion_limit)
            )
            graph_res = await self._db.execute(graph_stmt)
            graph_memories = list(graph_res.scalars().all())

            candidates.extend(graph_memories)

        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(f"memory.retrieval.graph_expansion_failed: {exc}")

        return candidates

    async def _get_active_preferences(self, account_id: uuid.UUID) -> list[ExplicitPreference]:
        stmt = select(ExplicitPreference).where(ExplicitPreference.account_id == account_id)
        res = await self._db.execute(stmt)
        return list(res.scalars().all())

    async def _get_active_dislikes(self, account_id: uuid.UUID) -> list[ExplicitDislike]:
        stmt = select(ExplicitDislike).where(ExplicitDislike.account_id == account_id)
        res = await self._db.execute(stmt)
        return list(res.scalars().all())
