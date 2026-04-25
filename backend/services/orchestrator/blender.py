from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import structlog
from pydantic import BaseModel, Field

from domain.memory.contracts import MemoryServiceContract
from domain.ml.contracts import RankingContract, RetrievalCandidate
from domain.search.contracts import ISearchService, SearchEvidencePack, SearchResult
from domain.tools.contracts import ToolsServiceContract

logger = structlog.get_logger(__name__)


class BlenderSignal(BaseModel):
    user_id: str
    session_id: str
    query: str
    context: dict[str, Any] = Field(default_factory=dict)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    environment_tags: list[str] = Field(default_factory=list)


class SignalEnricher:
    """Enrich raw blender signals with temporal and environmental context."""

    @staticmethod
    def enrich(signal: BlenderSignal) -> BlenderSignal:
        now = datetime.now(UTC)

        base_tags = [
            f"hour_{now.hour}",
            f"weekday_{now.weekday()}",
            "weekend" if now.weekday() >= 5 else "weekday",
        ]

        existing_tags = signal.context.get("tags", [])
        if not isinstance(existing_tags, list):
            existing_tags = []

        merged_tags = sorted(
            {
                *[str(tag) for tag in base_tags],
                *[str(tag) for tag in existing_tags if str(tag).strip()],
            }
        )

        return signal.model_copy(
            update={
                "timestamp": now,
                "environment_tags": merged_tags,
            }
        )


class ButlerBlender:
    """Federated candidate generation and ranking with provenance and determinism."""

    def __init__(
        self,
        memory_service: MemoryServiceContract,
        tools_service: ToolsServiceContract,
        ranking_provider: RankingContract,
        answering_engine: ISearchService | None = None,
        health_agent: Any | None = None,
        source_timeout_sec: float = 2.5,
        memory_limit: int = 10,
        tool_limit: int = 5,
        search_limit: int = 5,
        final_limit: int = 12,
    ) -> None:
        if source_timeout_sec <= 0:
            raise ValueError("source_timeout_sec must be greater than 0")
        if memory_limit <= 0:
            raise ValueError("memory_limit must be greater than 0")
        if tool_limit <= 0:
            raise ValueError("tool_limit must be greater than 0")
        if search_limit <= 0:
            raise ValueError("search_limit must be greater than 0")
        if final_limit <= 0:
            raise ValueError("final_limit must be greater than 0")

        self.memory = memory_service
        self.tools = tools_service
        self.ranking = ranking_provider
        self.search = answering_engine
        self.health = health_agent
        self.enricher = SignalEnricher()

        self._source_timeout_sec = source_timeout_sec
        self._memory_limit = memory_limit
        self._tool_limit = tool_limit
        self._search_limit = search_limit
        self._final_limit = final_limit

    async def blend(self, signal: BlenderSignal) -> list[RetrievalCandidate]:
        """Execute the hardened 4-stage blender pipeline."""
        enriched_signal = self.enricher.enrich(signal)

        candidates = await self._generate_candidates(enriched_signal)

        # Deterministic pre-sort before filtering/ranking.
        candidates = sorted(
            candidates,
            key=lambda item: (
                item.source,
                -float(item.score),
                item.content[:80],
                self._stable_candidate_key(item),
            ),
        )

        filtered = self._filter_candidates(candidates)
        ranked = await self._rank_candidates(enriched_signal, filtered)

        return ranked[: self._final_limit]

    async def _generate_candidates(self, signal: BlenderSignal) -> list[RetrievalCandidate]:
        """Fetch candidates from all available sources sequentially.

        Concurrent fan-out via asyncio.gather is disabled to prevent
        'concurrent operations are not permitted' errors on the shared
        SQLAlchemy session.
        """
        all_candidates: list[RetrievalCandidate] = []

        # 1. Memory
        try:
            res = await self._with_timeout(self._fetch_memory_candidates(signal))
            all_candidates.extend(res)
        except Exception as exc:
            logger.error("blender_candidate_gen_failed", source="memory", error=str(exc))

        # 2. Tools
        try:
            res = await self._with_timeout(self._fetch_tool_candidates(signal))
            all_candidates.extend(res)
        except Exception as exc:
            logger.error("blender_candidate_gen_failed", source="tools", error=str(exc))

        # 3. Search (External API, but we keep it sequential for simplicity and safety)
        if self.search is not None:
            try:
                res = await self._with_timeout(self._fetch_search_candidates(signal))
                all_candidates.extend(res)
            except Exception as exc:
                logger.error("blender_candidate_gen_failed", source="search", error=str(exc))

        logger.info(
            "blender_candidates_generated",
            query=signal.query,
            count=len(all_candidates),
        )

        return all_candidates

    async def _with_timeout(self, coro: Any) -> Any:
        return await asyncio.wait_for(coro, timeout=self._source_timeout_sec)

    async def _fetch_memory_candidates(self, signal: BlenderSignal) -> list[RetrievalCandidate]:
        """Fetch memory candidates with provenance."""
        try:
            memories = await self.memory.recall(
                signal.user_id,
                signal.query,
                limit=self._memory_limit,
            )

            candidates: list[RetrievalCandidate] = []
            for memory in memories:
                raw_content = getattr(memory, "content", "")
                if isinstance(raw_content, str):
                    content = raw_content
                else:
                    content = json.dumps(raw_content, ensure_ascii=False, sort_keys=True)

                memory_id = getattr(memory, "id", None)
                memory_type = getattr(memory, "type", "episodic")
                created_at = getattr(memory, "created_at", None)
                relevance_score = float(getattr(memory, "relevance_score", 0.7) or 0.7)

                candidates.append(
                    RetrievalCandidate(
                        source="memory",
                        content=content,
                        score=relevance_score,
                        metadata={
                            "provenance": {
                                "source": "memory",
                                "id": str(memory_id) if memory_id is not None else None,
                                "type": str(memory_type),
                                "trust_score": 0.95,
                                "timestamp": (
                                    created_at.isoformat()
                                    if isinstance(created_at, datetime)
                                    else None
                                ),
                            },
                            "retrieval_stage": "blender_memory",
                        },
                    )
                )

            return candidates

        except Exception as exc:
            logger.error("blender_memory_fetch_failed", error=str(exc))
            return []

    async def _fetch_tool_candidates(self, signal: BlenderSignal) -> list[RetrievalCandidate]:
        """Discover relevant tools using deterministic semantic-ish heuristics."""
        try:
            tools = await self.tools.list_tools()

            query_terms = self._normalized_query_terms(signal.query)
            intent = str(signal.context.get("intent", "")).strip().lower()

            candidates: list[RetrievalCandidate] = []

            for tool in tools:
                name = str(getattr(tool, "name", "") or "")
                description = str(getattr(tool, "description", "") or "")
                tags = [str(tag).strip().lower() for tag in getattr(tool, "tags", [])]

                if not name:
                    continue

                name_l = name.lower()
                desc_l = description.lower()

                score = 0.0

                if intent and intent in name_l:
                    score += 0.45
                if intent and any(intent == tag for tag in tags):
                    score += 0.35

                name_hits = sum(1 for term in query_terms if term in name_l)
                desc_hits = sum(1 for term in query_terms if term in desc_l)
                tag_hits = sum(1 for term in query_terms if term in tags)

                score += min(0.30, name_hits * 0.10)
                score += min(0.25, desc_hits * 0.05)
                score += min(0.20, tag_hits * 0.10)

                if score <= 0:
                    continue

                candidates.append(
                    RetrievalCandidate(
                        source="tools",
                        content=f"Tool: {name} — {description}".strip(),
                        score=float(min(score, 1.0)),
                        metadata={
                            "provenance": {
                                "source": "tools",
                                "tool_name": name,
                                "trust_score": 1.0,
                                "tags": sorted(tag for tag in tags if tag),
                            },
                            "retrieval_stage": "blender_tools",
                        },
                    )
                )

            candidates.sort(
                key=lambda item: (
                    -float(item.score),
                    item.content,
                )
            )
            return candidates[: self._tool_limit]

        except Exception as exc:
            logger.error("blender_tool_fetch_failed", error=str(exc))
            return []

    async def _fetch_search_candidates(self, signal: BlenderSignal) -> list[RetrievalCandidate]:
        """Fetch external knowledge using current search service contracts."""
        if self.search is None:
            return []

        try:
            pack = await self.search.search(
                signal.query,
                mode="auto",
                max_results=self._search_limit,
            )

            if isinstance(pack, SearchEvidencePack):
                results = pack.results
            else:
                # Compatibility fallback if an older implementation leaks a list.
                results = getattr(pack, "results", pack)

            candidates: list[RetrievalCandidate] = []
            for result in results:
                if isinstance(result, SearchResult):
                    url = result.url or ""
                    title = result.title or ""
                    snippet = result.snippet or result.content or ""
                    score = float(result.score or 0.6)
                else:
                    url = str(getattr(result, "url", "") or "")
                    title = str(getattr(result, "title", "") or "")
                    snippet = str(
                        getattr(result, "snippet", "") or getattr(result, "content", "") or ""
                    )
                    score = float(getattr(result, "score", 0.6) or 0.6)

                provider_domain = self._safe_domain(url)

                candidates.append(
                    RetrievalCandidate(
                        source="search",
                        content=snippet[:1500],
                        score=score,
                        metadata={
                            "provenance": {
                                "source": "search",
                                "provider": provider_domain,
                                "url": url,
                                "title": title,
                                "trust_score": 0.7,
                            },
                            "retrieval_stage": "blender_search",
                        },
                    )
                )

            return candidates

        except Exception as exc:
            logger.error("blender_search_fetch_failed", error=str(exc))
            return []

    def _filter_candidates(self, candidates: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
        """Deduplicate federated candidates by stable fingerprint."""
        best_by_fingerprint: dict[str, RetrievalCandidate] = {}

        for candidate in candidates:
            fingerprint = self._fingerprint_candidate(candidate)
            existing = best_by_fingerprint.get(fingerprint)

            if existing is None or float(candidate.score) > float(existing.score):
                best_by_fingerprint[fingerprint] = candidate

        unique = list(best_by_fingerprint.values())
        unique.sort(
            key=lambda item: (
                item.source,
                -float(item.score),
                item.content[:80],
                self._stable_candidate_key(item),
            )
        )
        return unique

    async def _rank_candidates(
        self,
        signal: BlenderSignal,
        candidates: list[RetrievalCandidate],
    ) -> list[RetrievalCandidate]:
        """Rerank candidates and return new normalized candidate objects."""
        if not candidates:
            return []

        reranked = await self.ranking.rerank(
            signal.query,
            candidates,
            user_id=signal.user_id,
        )

        rebuilt: list[RetrievalCandidate] = []
        for rank_item in reranked:
            if rank_item.index < 0 or rank_item.index >= len(candidates):
                continue

            original = candidates[rank_item.index]
            merged_metadata = {
                **dict(original.metadata),
                "ranking": {
                    "score": float(rank_item.score),
                    "metadata": dict(rank_item.metadata),
                },
            }

            rebuilt.append(
                RetrievalCandidate(
                    source=original.source,
                    content=original.content,
                    score=float(rank_item.score),
                    metadata=merged_metadata,
                )
            )

        rebuilt.sort(
            key=lambda item: (
                -float(item.score),
                item.source,
                item.content[:80],
                self._stable_candidate_key(item),
            )
        )
        return rebuilt

    def _normalized_query_terms(self, query: str) -> list[str]:
        parts = {token.strip().lower() for token in query.split() if len(token.strip()) > 2}
        return sorted(parts)

    def _safe_domain(self, raw_url: str) -> str:
        try:
            return urlparse(raw_url).netloc or "unknown"
        except Exception:
            return "unknown"

    def _fingerprint_candidate(self, candidate: RetrievalCandidate) -> str:
        provenance = candidate.metadata.get("provenance", {})
        if not isinstance(provenance, dict):
            provenance = {}

        raw = json.dumps(
            {
                "source": candidate.source,
                "content": candidate.content.strip().lower(),
                "url": provenance.get("url"),
                "tool_name": provenance.get("tool_name"),
                "memory_id": provenance.get("id"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _stable_candidate_key(self, candidate: RetrievalCandidate) -> str:
        return self._fingerprint_candidate(candidate)
