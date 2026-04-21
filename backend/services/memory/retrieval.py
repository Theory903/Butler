import uuid
import math
import numpy as np
from dataclasses import dataclass
from typing import Any, List, Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from domain.memory.models import MemoryEntry, ExplicitPreference, ExplicitDislike
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
    signals: Dict[str, float]  # Breakdown for debugging

class RetrievalFusionEngine:
    """Butler's Oracle-Grade Retrieval Fusion Engine."""

    def __init__(
        self, 
        db: AsyncSession, 
        embedder: EmbeddingContract,
        knowledge_repo: KnowledgeRepoContract,
        personalization: Optional[Any] = None
    ):
        self._db = db
        self._embedder = embedder
        self._knowledge_repo = knowledge_repo
        self._personalization = personalization

    async def search(
        self, 
        account_id: str, 
        query: str, 
        memory_types: Optional[List[str]] = None, 
        limit: int = 20
    ) -> List[ScoredMemory]:
        # Safe UUID parsing - prevents recall failures on invalid account_id
        try:
            acc_id = uuid.UUID(account_id)
        except (ValueError, TypeError):
            # Return empty if account_id is invalid - common cause of "returns 0 results"
            return []
        
        # Pass both UUID and string for flexible query matching
        acc_id_str = str(acc_id)
        
        # 1. Broad Retrieval (Candidates)
        candidate_pool = await self._get_candidates(acc_id, acc_id_str, query, limit * 3)
        
        # 2. Personalization Ranker (The Blender)
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
                    score=0.5, # Initial bias
                    metadata={"ts": m.created_at.timestamp() if m.created_at else None}
                ) for m in candidate_pool
            ]
            
            ranked = await self._personalization.rank(
                query_vector=np.array(query_vector),
                context=context,
                candidates=ml_candidates
            )
            
            # Map back to ScoredMemory
            memory_map = {m.id: m for m in candidate_pool}
            return [
                ScoredMemory(
                    memory=memory_map[r.id],
                    score=r.score,
                    signals=r.features
                )
                for r in ranked if r.id in memory_map
            ][:limit]
        
        # 3. Fallback: Extract Signals for Query
        query_embedding = await self._embedder.embed(query)
        preferences = await self._get_active_preferences(acc_id)
        dislikes = await self._get_active_dislikes(acc_id)
        
        scored_results = []
        for mem in candidate_pool:
            score_data = await self._calculate_fusion_score(
                mem, query, query_embedding, preferences, dislikes
            )
            scored_results.append(ScoredMemory(
                memory=mem,
                score=score_data["total"],
                signals=score_data["signals"]
            ))

        scored_results.sort(key=lambda x: x.score, reverse=True)
        return scored_results[:limit]

    async def _calculate_fusion_score(
        self, 
        memory: MemoryEntry, 
        query: str, 
        query_embedding: List[float],
        preferences: List[ExplicitPreference],
        dislikes: List[ExplicitDislike]
    ) -> Dict:
        """Weighted score calculation from docs/memory.md section 5.1."""
        signals = {
            "semantic": 0.0,
            "keyword": 0.0,
            "graph": 0.0,
            "preference": 0.0,
            "dislike": 0.0
        }

        # Semantic Score (Cosine similarity)
        if memory.embedding is not None:
            # Simple dot product as approximation for normalized vectors
            signals["semantic"] = sum(a * b for a, b in zip(query_embedding, memory.embedding))

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
            (signals["semantic"] * 0.4) +
            (signals["keyword"] * 0.2) +
            (signals["graph"] * 0.2) +
            (signals["preference"] * 0.2) -
            (signals["dislike"] * 0.5)
        )

        return {"total": total, "signals": signals}

    async def _get_candidates(
        self, 
        account_id: uuid.UUID, 
        account_id_str: str,
        query: str, 
        limit: int
    ) -> List[MemoryEntry]:
        """Oracle-Grade retrieval with flexible account_id matching."""
        from domain.memory.models import (
            MemoryStatus,
            KnowledgeEntity,
            KnowledgeEdge,
            MemoryEntityLink,
        )
        from sqlalchemy import or_

        # Primary scan with flexible account_id matching - fixes "0 results" bug
        stmt = select(MemoryEntry).where(
            or_(
                MemoryEntry.account_id == account_id,
                MemoryEntry.account_id == account_id_str,
            ),
            MemoryEntry.status == MemoryStatus.ACTIVE,
        ).limit(limit)
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
                row[0]
                for row in seed_res
                if any(tok in row[1].lower() for tok in query_tokens)
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
            neighbour_ids.update(seed_ids)   # include seeds themselves

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
            graph_stmt = select(MemoryEntry).where(
                MemoryEntry.id.in_(linked_memory_ids),
                MemoryEntry.account_id == account_id,
                MemoryEntry.status == MemoryStatus.ACTIVE,
            ).limit(expansion_limit)
            graph_res = await self._db.execute(graph_stmt)
            graph_memories = list(graph_res.scalars().all())

            candidates.extend(graph_memories)

        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                f"memory.retrieval.graph_expansion_failed: {exc}"
            )

        return candidates


    async def _get_active_preferences(self, account_id: uuid.UUID) -> List[ExplicitPreference]:
        stmt = select(ExplicitPreference).where(ExplicitPreference.account_id == account_id)
        res = await self._db.execute(stmt)
        return list(res.scalars().all())

    async def _get_active_dislikes(self, account_id: uuid.UUID) -> List[ExplicitDislike]:
        stmt = select(ExplicitDislike).where(ExplicitDislike.account_id == account_id)
        res = await self._db.execute(stmt)
        return list(res.scalars().all())
