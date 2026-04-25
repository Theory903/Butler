from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import structlog

from core.observability import get_tracer
from domain.ml.contracts import RetrievalCandidate

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SourcePlan:
    name: str
    limit: int
    weight: float


class CandidateMixer:
    """Federated candidate mixer for Butler retrieval.

    Sources:
    - memory: vector / episodic retrieval
    - knowledge: graph / relationship retrieval
    - ambient: realtime context
    """

    def __init__(
        self,
        memory_svc: Any | None = None,
        knowledge_svc: Any | None = None,
        ambient_svc: Any | None = None,
        health_agent: Any | None = None,
        source_timeout_sec: float = 2.5,
    ) -> None:
        if source_timeout_sec <= 0:
            raise ValueError("source_timeout_sec must be greater than 0")

        self._memory = memory_svc
        self._knowledge = knowledge_svc
        self._ambient = ambient_svc
        self._health_agent = health_agent
        self._tracer = get_tracer()
        self._source_timeout_sec = source_timeout_sec

        logger.info(
            "candidate_mixer_initialized",
            sources={
                "memory": bool(memory_svc),
                "knowledge": bool(knowledge_svc),
                "ambient": bool(ambient_svc),
            },
            adaptive=bool(health_agent),
            source_timeout_sec=source_timeout_sec,
        )

    async def mix(self, query: str, limit: int = 100) -> list[RetrievalCandidate]:
        """Fetch and unify candidates from all active sources."""
        if limit <= 0:
            return []

        effective_limit, skip_heavy = self._apply_load_shedding(limit, query)
        if effective_limit <= 0:
            return []

        logger.debug("mixing_started", query=query, limit=effective_limit)

        with self._tracer.span(
            "butler.ml.mix",
            attrs={"query": query, "limit": effective_limit},
        ):
            start_time = time.monotonic()

            plans = self._build_source_plans(effective_limit, skip_heavy)
            if not plans:
                logger.warning("mixer_no_active_sources")
                return []

            source_results = await self._fetch_all_sources(query=query, plans=plans)
            all_candidates = self._merge_weighted_candidates(source_results, plans)
            unique_candidates = self._deduplicate(all_candidates)
            final_candidates = self._apply_diversity(unique_candidates, effective_limit)

            latency_ms = (time.monotonic() - start_time) * 1000
            logger.info(
                "mixing_completed",
                query=query,
                count=len(final_candidates),
                latency_ms=round(latency_ms, 2),
                sources=[plan.name for plan in plans],
            )
            return final_candidates

    def _apply_load_shedding(self, limit: int, query: str) -> tuple[int, bool]:
        effective_limit = limit
        skip_heavy = False

        if self._health_agent is None:
            return effective_limit, skip_heavy

        status = getattr(self._health_agent, "status", None)

        if status == "UNHEALTHY":
            logger.warning("mixer_load_shedding_critical", query=query, status=status)
            return 0, True

        if status == "DEGRADED":
            effective_limit = max(5, limit // 4)
            skip_heavy = True
            logger.info(
                "mixer_load_shedding_active",
                query=query,
                status=status,
                original_limit=limit,
                effective_limit=effective_limit,
            )

        return effective_limit, skip_heavy

    def _build_source_plans(self, effective_limit: int, skip_heavy: bool) -> list[SourcePlan]:
        plans: list[SourcePlan] = []

        if self._memory is not None:
            plans.append(
                SourcePlan(
                    name="memory",
                    limit=max(1, effective_limit // 2),
                    weight=1.0,
                )
            )

        if self._knowledge is not None and not skip_heavy:
            plans.append(
                SourcePlan(
                    name="knowledge",
                    limit=max(1, effective_limit // 2),
                    weight=0.8,
                )
            )

        if self._ambient is not None:
            plans.append(
                SourcePlan(
                    name="ambient",
                    limit=max(1, effective_limit // 4),
                    weight=0.6,
                )
            )

        return plans

    async def _fetch_all_sources(
        self,
        *,
        query: str,
        plans: list[SourcePlan],
    ) -> dict[str, list[RetrievalCandidate]]:
        async def _run(plan: SourcePlan) -> tuple[str, list[RetrievalCandidate]]:
            candidates = await asyncio.wait_for(
                self._fetch_from_source(plan.name, query, plan.limit),
                timeout=self._source_timeout_sec,
            )
            return plan.name, candidates

        tasks = [_run(plan) for plan in plans]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        merged: dict[str, list[RetrievalCandidate]] = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error("mixer_source_failed", error=str(result))
                continue
            source_name, candidates = result
            merged[source_name] = candidates

        return merged

    async def _fetch_from_source(
        self,
        source_name: str,
        query: str,
        limit: int,
    ) -> list[RetrievalCandidate]:
        if source_name == "memory":
            return await self._fetch_from_memory(query, limit)
        if source_name == "knowledge":
            return await self._fetch_from_knowledge(query, limit)
        if source_name == "ambient":
            return await self._fetch_from_ambient(query, limit)
        raise ValueError(f"Unknown source: {source_name}")

    def _merge_weighted_candidates(
        self,
        source_results: dict[str, list[RetrievalCandidate]],
        plans: list[SourcePlan],
    ) -> list[RetrievalCandidate]:
        weight_map = {plan.name: plan.weight for plan in plans}
        all_candidates: list[RetrievalCandidate] = []

        for source_name, candidates in source_results.items():
            weight = weight_map.get(source_name, 1.0)
            for candidate in candidates:
                metadata = dict(candidate.metadata)
                metadata["source"] = source_name
                metadata["base_score"] = float(candidate.score)
                metadata["weighted_by"] = weight

                all_candidates.append(
                    RetrievalCandidate(
                        source=candidate.source,
                        content=candidate.content,
                        score=float(candidate.score) * weight,
                        metadata=metadata,
                    )
                )

        return all_candidates

    def _deduplicate(self, candidates: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
        best_by_id: dict[str, RetrievalCandidate] = {}

        for candidate in candidates:
            cid = self._candidate_id(candidate)
            existing = best_by_id.get(cid)
            if existing is None or candidate.score > existing.score:
                best_by_id[cid] = candidate

        return sorted(best_by_id.values(), key=lambda item: item.score, reverse=True)

    def _apply_diversity(
        self,
        candidates: list[RetrievalCandidate],
        limit: int,
    ) -> list[RetrievalCandidate]:
        if len(candidates) <= limit:
            return candidates

        grouped: dict[str, list[RetrievalCandidate]] = defaultdict(list)
        for candidate in candidates:
            grouped[str(candidate.metadata.get("source", "unknown"))].append(candidate)

        ordered_sources = sorted(
            grouped.keys(),
            key=lambda source: grouped[source][0].score if grouped[source] else 0.0,
            reverse=True,
        )

        diversified: list[RetrievalCandidate] = []
        while len(diversified) < limit:
            progressed = False
            for source in ordered_sources:
                if grouped[source]:
                    diversified.append(grouped[source].pop(0))
                    progressed = True
                    if len(diversified) >= limit:
                        break
            if not progressed:
                break

        return diversified

    def _candidate_id(self, candidate: RetrievalCandidate) -> str:
        raw_id = candidate.metadata.get("id")
        if raw_id:
            return str(raw_id)
        return f"{candidate.source}:{hash(candidate.content)}"

    async def _fetch_from_memory(self, query: str, limit: int) -> list[RetrievalCandidate]:
        """Fetch from memory service.

        Replace the fallback demo block with the real implementation when wired.
        """
        if self._memory is None:
            return []

        if hasattr(self._memory, "search"):
            result = await self._memory.search(query=query, limit=limit)
            if isinstance(result, list):
                return result

        return [
            RetrievalCandidate(
                source="memory",
                content=f"Memory result {i} for {query}",
                score=max(0.0, 0.9 - (i * 0.05)),
                metadata={"id": f"mem_{i}"},
            )
            for i in range(min(limit, 3))
        ]

    async def _fetch_from_knowledge(self, query: str, limit: int) -> list[RetrievalCandidate]:
        """Fetch from knowledge service."""
        if self._knowledge is None:
            return []

        if hasattr(self._knowledge, "search"):
            result = await self._knowledge.search(query=query, limit=limit)
            if isinstance(result, list):
                return result

        return [
            RetrievalCandidate(
                source="knowledge",
                content=f"Knowledge result {i} for {query}",
                score=max(0.0, 0.85 - (i * 0.1)),
                metadata={"id": f"kg_{i}"},
            )
            for i in range(min(limit, 2))
        ]

    async def _fetch_from_ambient(self, query: str, limit: int) -> list[RetrievalCandidate]:
        """Fetch from ambient service."""
        if self._ambient is None:
            return []

        if hasattr(self._ambient, "search"):
            result = await self._ambient.search(query=query, limit=limit)
            if isinstance(result, list):
                return result

        return [
            RetrievalCandidate(
                source="ambient",
                content=f"Ambient state {i} for {query}",
                score=0.95,
                metadata={"id": f"amb_{i}"},
            )
            for i in range(min(limit, 1))
        ]


class SignalManager:
    """Inject unified user-action signals into candidates for downstream ranking."""

    def __init__(self, feature_svc: Any | None) -> None:
        self._features = feature_svc
        logger.info("signal_manager_initialized", enabled=bool(feature_svc))

    async def enrich_candidates(
        self,
        entity_id: str,
        candidates: list[RetrievalCandidate],
    ) -> list[RetrievalCandidate]:
        if not self._features or not candidates:
            return candidates

        try:
            user_signals = await self._features.get_online_features(
                entity_id,
                ["user_affinity", "recency_bias", "interaction_depth"],
            )
            signals_dict = dict(getattr(user_signals, "features", {}) or {})
        except Exception as exc:
            logger.warning("signal_enrichment_failed", error=str(exc))
            signals_dict = {}

        enriched: list[RetrievalCandidate] = []
        for candidate in candidates:
            metadata = dict(candidate.metadata)
            metadata["signals"] = {
                "uua_affinity": float(signals_dict.get("user_affinity", 0.5)),
                "recency_bias": float(signals_dict.get("recency_bias", 1.0)),
                "interaction_depth": float(signals_dict.get("interaction_depth", 1.0)),
            }

            enriched.append(
                RetrievalCandidate(
                    source=candidate.source,
                    content=candidate.content,
                    score=candidate.score,
                    metadata=metadata,
                )
            )

        return enriched
