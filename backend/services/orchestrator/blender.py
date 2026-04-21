"""ButlerBlender — Phase 8b Hardened.

The 'Cr-Mixer' of Butler. Orchestrates federated intelligence retrieval and ranking.
Aligned with Oracle-Grade reliability:
- Signal enrichment (contextual features).
- Source provenance tracking.
- Federated deduplication.
- Semantic tool discovery (v2.0 logic).
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import structlog
from pydantic import BaseModel, Field

from domain.ml.contracts import RankingContract, RetrievalCandidate
from domain.memory.contracts import MemoryServiceContract
from domain.tools.contracts import ToolsServiceContract
from domain.search.contracts import ISearchService

logger = structlog.get_logger(__name__)


class BlenderSignal(BaseModel):
    user_id: str
    session_id: str
    query: str
    context: Dict[str, Any] = Field(default_factory=dict)
    
    # Enriched fields
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    environment_tags: List[str] = Field(default_factory=list)


class SignalEnricher:
    """Enriches raw signals with temporal and environmental context."""
    
    @staticmethod
    def enrich(signal: BlenderSignal) -> BlenderSignal:
        now = datetime.now(UTC)
        signal.timestamp = now
        
        # Add basic temporal tags
        tags = [
            f"hour_{now.hour}",
            f"weekday_{now.weekday()}",
            "weekend" if now.weekday() >= 5 else "weekday"
        ]
        
        # Merge tags from existing context if any
        existing_tags = signal.context.get("tags", [])
        # Rule #170: Deterministic sort for prompt stability
        signal.environment_tags = sorted(list(set(tags + existing_tags)))
        
        return signal


class ButlerBlender:
    """Orchestrates federated candidate generation and ranking with full provenance."""

    def __init__(
        self,
        memory_service: MemoryServiceContract,
        tools_service: ToolsServiceContract,
        ranking_provider: RankingContract,
        answering_engine: Optional[ISearchService] = None,
        health_agent: Optional[Any] = None,
    ) -> None:
        self.memory = memory_service
        self.tools = tools_service
        self.ranking = ranking_provider
        self.search = answering_engine
        self.health = health_agent
        self.enricher = SignalEnricher()

    async def blend(self, signal: BlenderSignal) -> List[RetrievalCandidate]:
        """Execute the hardened 4-stage processing pipeline."""
        # 1. Signal enrichment
        enriched_signal = self.enricher.enrich(signal)
        
        # 2. Parallel candidate generation
        candidates = await self._generate_candidates(enriched_signal)
        
        # Rule #170: Pre-sort candidates by source and trust_score to ensure 
        # that even if ranking has ties, the order is bit-identical for the cache.
        candidates.sort(key=lambda x: (x.source, -x.score, x.content[:50]))

        # 3. Federated deduplication + safety filter
        filtered = self._filter_candidates(candidates)
        
        # 4. Light ranking
        ranked = await self._rank_candidates(enriched_signal, filtered)
        return ranked

    async def _generate_candidates(self, signal: BlenderSignal) -> List[RetrievalCandidate]:
        """Fan-out to all sources in parallel."""
        # asyncio.gather preserves order of results based on tasks order
        tasks = [
            self._fetch_memory_candidates(signal),
            self._fetch_tool_candidates(signal),
        ]
        if self.search:
            tasks.append(self._fetch_search_candidates(signal))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_candidates: List[RetrievalCandidate] = []
        for res in results:
            if isinstance(res, list):
                all_candidates.extend(res)
            elif isinstance(res, Exception):
                logger.error("blender_candidate_gen_failed", error=str(res))

        return all_candidates

    # ── Source Fetching with Provenance ───────────────────────────────────────

    async def _fetch_memory_candidates(self, signal: BlenderSignal) -> List[RetrievalCandidate]:
        """Fetch ranked memories from MemoryService with provenance."""
        try:
            memories = await self.memory.recall(signal.user_id, signal.query, limit=10)
            return [
                RetrievalCandidate(
                    source="memory",
                    content=m.content if isinstance(m.content, str) else json.dumps(m.content),
                    score=getattr(m, "relevance_score", 0.7),
                    metadata={
                        "provenance": {
                            "source": "memory",
                            "id": str(m.id),
                            "type": getattr(m, "type", "episodic"),
                            "trust_score": 0.95,
                            "timestamp": m.created_at.isoformat() if m.created_at else None,
                        },
                        "retrieval_stage": "blender_memory",
                    },
                )
                for m in memories
            ]
        except Exception as exc:
            logger.error("blender_memory_fetch_failed", error=str(exc))
            return []

    async def _fetch_tool_candidates(self, signal: BlenderSignal) -> List[RetrievalCandidate]:
        """Discover relevant tools using keywords and intent tags."""
        try:
            tools = await self.tools.list_tools()
            # Rule #170: Deterministic keyword parts
            query_parts = sorted(list(set(signal.query.lower().split())))
            intent = signal.context.get("intent", "").lower()
            
            candidates = []
            for t in tools:
                # Better heuristic: match on name, description, and intent tags
                relevancy = 0.0
                if intent and intent in t.name.lower(): relevancy += 0.5
                if any(word in t.description.lower() for word in query_parts if len(word) > 3): relevancy += 0.4
                
                if relevancy > 0:
                    candidates.append(
                        RetrievalCandidate(
                            source="tools",
                            content=f"Tool: {t.name} — {t.description}",
                            score=relevancy,
                            metadata={
                                "provenance": {
                                    "source": "tools",
                                    "tool_name": t.name,
                                    "trust_score": 1.0,
                                    "tags": sorted(getattr(t, "tags", [])),
                                },
                                "retrieval_stage": "blender_tools",
                            },
                        )
                    )
            
            # Sort by relevancy and return top 5
            candidates.sort(key=lambda x: (-x.score, x.content))
            return candidates[:5]
        except Exception as exc:
            logger.error("blender_tool_fetch_failed", error=str(exc))
            return []

    async def _fetch_search_candidates(self, signal: BlenderSignal) -> List[RetrievalCandidate]:
        """Fetch external knowledge with full source provenance."""
        if not self.search:
            return []

        try:
            results = await self.search.search(signal.query, limit=5)
            candidates = []
            for r in results:
                raw_url = getattr(r, "url", "") or ""
                try:
                    provider_domain = urlparse(raw_url).netloc or "unknown"
                except Exception:
                    provider_domain = "unknown"

                snippet = getattr(r, "snippet", "") or getattr(r, "content", "") or ""
                
                candidates.append(
                    RetrievalCandidate(
                        source="search",
                        content=snippet[:1500],
                        score=float(getattr(r, "score", 0.6)),
                        metadata={
                            "provenance": {
                                "source": "search",
                                "provider": provider_domain,
                                "url": raw_url,
                                "trust_score": 0.7,
                                "title": getattr(r, "title", ""),
                            },
                            "retrieval_stage": "blender_search",
                        },
                    )
                )
            return candidates
        except Exception as exc:
            logger.error("blender_search_fetch_failed", error=str(exc))
            return []

    def _filter_candidates(self, candidates: List[RetrievalCandidate]) -> List[RetrievalCandidate]:
        """Federated deduplication by content fingerprint."""
        seen: set[str] = set()
        unique: List[RetrievalCandidate] = []
        for c in candidates:
            # Rule #170: Stable fingerprint
            fingerprint = c.content[:200].strip().lower()
            if fingerprint not in seen:
                unique.append(c)
                seen.add(fingerprint)
        return unique

    async def _rank_candidates(
        self, signal: BlenderSignal, candidates: List[RetrievalCandidate]
    ) -> List[RetrievalCandidate]:
        """Rank and return the final candidate set via RankingContract."""
        if not candidates:
            return []

        reranked = await self.ranking.rerank(signal.query, candidates, user_id=signal.user_id)
        
        final: List[RetrievalCandidate] = []
        for r in reranked:
            if r.index < len(candidates):
                cand = candidates[r.index]
                cand.score = r.score
                final.append(cand)

        # Ensure final return is sorted by score DESC, then content as tie-break
        final.sort(key=lambda x: (-x.score, x.content))
        return final
