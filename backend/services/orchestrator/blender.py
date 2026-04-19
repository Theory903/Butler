"""ButlerBlender — v3.1 production.

Changes from v3.0:
  - _fetch_search_candidates(): wired to ISearchService with source provenance
  - Signal enrichment TODO resolved: context passed through as-is (FeatureService Phase 3)

Search candidate provenance fields:
  source       = "search"
  provider     = domain/hostname of result
  snippet      = raw content
  title        = page title (if available)
  url          = source URL
  raw_score    = score from search provider
  retrieval_stage = "blender_search"

Blender rules (unchanged):
  1. Signal extraction (context passthrough — FeatureService in Phase 3)
  2. Parallel candidate generation (memory + tools + search)
  3. Deduplication filter
  4. Light ranking via RankingContract
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from pydantic import BaseModel
from urllib.parse import urlparse

import structlog
from domain.ml.contracts import ReasoningContract, ReasoningRequest, RankingContract, RetrievalCandidate
from domain.memory.contracts import MemoryServiceContract
from domain.tools.contracts import ToolsServiceContract

logger = structlog.get_logger(__name__)


class BlenderSignal(BaseModel):
    user_id: str
    session_id: str
    query: str
    context: dict[str, Any] = {}


class ButlerBlender:
    """The 'Cr-Mixer' of Butler (v3.1).

    Orchestrates federated intelligence retrieval and ranking.
    Sources: Memory (vector+graph) | Tools (capability discovery) | Search (web/RAG)
    """

    def __init__(
        self,
        memory_service: MemoryServiceContract,
        tools_service: ToolsServiceContract,
        ranking_provider: RankingContract,
        answering_engine: Any = None,  # ISearchService-compatible
    ) -> None:
        self.memory = memory_service
        self.tools = tools_service
        self.ranking = ranking_provider
        self.search = answering_engine

    async def blend(self, signal: BlenderSignal) -> list[RetrievalCandidate]:
        """Execute the 4-stage processing pipeline."""
        # 1. Signal extraction (context passed through — FeatureService enrichment in Phase 3)
        # 2. Parallel candidate generation
        candidates = await self._generate_candidates(signal)
        # 3. Deduplication + safety filter
        filtered = self._filter_candidates(candidates)
        # 4. Light ranking
        ranked = await self._rank_candidates(signal, filtered)
        return ranked

    async def _generate_candidates(self, signal: BlenderSignal) -> list[RetrievalCandidate]:
        """Fan-out to all sources in parallel."""
        tasks = [
            self._fetch_memory_candidates(signal),
            self._fetch_tool_candidates(signal),
        ]
        if self.search:
            tasks.append(self._fetch_search_candidates(signal))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_candidates: list[RetrievalCandidate] = []
        for res in results:
            if isinstance(res, list):
                all_candidates.extend(res)
            elif isinstance(res, Exception):
                logger.error("blender.candidate_gen_failed", error=str(res))

        return all_candidates

    async def _fetch_memory_candidates(self, signal: BlenderSignal) -> list[RetrievalCandidate]:
        """Fetch ranked memories from MemoryService."""
        try:
            memories = await self.memory.recall(signal.user_id, signal.query, limit=10)
            return [
                RetrievalCandidate(
                    source="memory",
                    content=m.content if isinstance(m.content, str) else json.dumps(m.content),
                    score=getattr(m, "relevance_score", 0.7),
                    metadata={
                        "memory_id": str(m.id),
                        "ts": m.created_at.isoformat() if m.created_at else None,
                        "retrieval_stage": "blender_memory",
                    },
                )
                for m in memories
            ]
        except Exception as exc:
            logger.error("blender.memory_fetch_failed", error=str(exc))
            return []

    async def _fetch_tool_candidates(self, signal: BlenderSignal) -> list[RetrievalCandidate]:
        """Discover relevant tools for the intent."""
        try:
            tools = await self.tools.list_tools()
            query_lower = signal.query.lower()
            candidates = []
            for t in tools:
                if any(word in t.description.lower() for word in query_lower.split() if len(word) > 3):
                    candidates.append(
                        RetrievalCandidate(
                            source="tools",
                            content=f"Tool: {t.name} — {t.description}",
                            score=0.9,
                            metadata={
                                "tool_name": t.name,
                                "retrieval_stage": "blender_tools",
                            },
                        )
                    )
            return candidates[:5]
        except Exception as exc:
            logger.error("blender.tool_fetch_failed", error=str(exc))
            return []

    async def _fetch_search_candidates(self, signal: BlenderSignal) -> list[RetrievalCandidate]:
        """Fetch external knowledge candidates from SearchService.

        Each candidate carries full source provenance so the blender
        does not become a soup machine.
        """
        if not self.search:
            return []

        try:
            # ISearchService.search(query, limit) contract
            results = await self.search.search(signal.query, limit=5)
            candidates = []
            for r in results:
                # Normalise provider domain for provenance
                raw_url = getattr(r, "url", "") or ""
                try:
                    provider_domain = urlparse(raw_url).netloc or "unknown"
                except Exception:
                    provider_domain = "unknown"

                snippet = getattr(r, "snippet", "") or getattr(r, "content", "") or ""
                title = getattr(r, "title", "")
                raw_score = getattr(r, "score", 0.6)

                candidates.append(
                    RetrievalCandidate(
                        source="search",
                        content=snippet[:1500],          # trim before ranking
                        score=float(raw_score),
                        metadata={
                            "provider": provider_domain,
                            "title": title,
                            "url": raw_url,
                            "raw_score": raw_score,
                            "retrieval_stage": "blender_search",
                        },
                    )
                )
            logger.debug("blender.search_candidates", count=len(candidates))
            return candidates
        except Exception as exc:
            logger.error("blender.search_fetch_failed", error=str(exc))
            return []

    def _filter_candidates(self, candidates: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
        """Deduplicate by content fingerprint."""
        seen: set[str] = set()
        unique: list[RetrievalCandidate] = []
        for c in candidates:
            # Fingerprint on first 200 chars to handle minor whitespace diffs
            fingerprint = c.content[:200].strip().lower()
            if fingerprint not in seen:
                unique.append(c)
                seen.add(fingerprint)
        return unique

    async def _rank_candidates(
        self, signal: BlenderSignal, candidates: list[RetrievalCandidate]
    ) -> list[RetrievalCandidate]:
        """Rank and return the final candidate set via RankingContract."""
        if not candidates:
            return []

        reranked = await self.ranking.rerank(signal.query, candidates, user_id=signal.user_id)

        final: list[RetrievalCandidate] = []
        for r in reranked:
            if r.index < len(candidates):
                cand = candidates[r.index]
                cand.score = r.score
                final.append(cand)

        return final
