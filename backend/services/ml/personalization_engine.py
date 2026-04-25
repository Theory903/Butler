from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic
from typing import Any, Protocol
from uuid import UUID

import numpy as np
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


# -----------------------------------------------------------------------------
# CONFIGURATION MODELS
# -----------------------------------------------------------------------------


class RankerType(StrEnum):
    LIGHT = "light"
    HEAVY = "heavy"
    RECAP = "recap"


class PersonalizationConfig(BaseModel):
    """Configuration for the personalization engine."""

    model_config = ConfigDict(extra="forbid")

    candidate_limit: int = Field(default=100, ge=1, le=1000)
    light_ranker_cutoff: int = Field(default=20, ge=1, le=100)
    heavy_ranker_cutoff: int = Field(default=5, ge=1, le=20)

    vector_similarity_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    graph_traversal_depth: int = Field(default=2, ge=1, le=5)

    circuit_breaker_failure_threshold: int = Field(default=5, ge=1)
    circuit_breaker_recovery_timeout: int = Field(default=30, ge=1)

    batch_size: int = Field(default=32, ge=1, le=256)
    timeout_ms: int = Field(default=500, ge=100, le=10000)

    recap_max_per_type: int = Field(default=2, ge=1, le=50)
    graph_neighbor_base_score: float = Field(default=0.15, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_cutoffs(self) -> PersonalizationConfig:
        if self.light_ranker_cutoff >= self.candidate_limit:
            raise ValueError("light_ranker_cutoff must be less than candidate_limit")
        if self.heavy_ranker_cutoff >= self.light_ranker_cutoff:
            raise ValueError("heavy_ranker_cutoff must be less than light_ranker_cutoff")
        return self


# -----------------------------------------------------------------------------
# DOMAIN MODELS
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Candidate:
    """Rankable candidate item."""

    id: UUID
    type: str
    score: float = 0.0
    features: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def with_score(self, score: float) -> Candidate:
        return Candidate(
            id=self.id,
            type=self.type,
            score=float(score),
            features=self.features,
            metadata=self.metadata,
        )

    def with_features(self, features: dict[str, Any]) -> Candidate:
        return Candidate(
            id=self.id,
            type=self.type,
            score=self.score,
            features={**self.features, **features},
            metadata=self.metadata,
        )


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    id: UUID
    type: str
    rank: int
    ranker_type: RankerType
    score: float = 0.0
    features: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


# -----------------------------------------------------------------------------
# CIRCUIT BREAKER
# -----------------------------------------------------------------------------


class CircuitBreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerError(Exception):
    """Raised when a request is blocked by the circuit breaker."""


class CircuitBreaker:
    """Simple circuit breaker for rankers."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 30) -> None:
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be greater than 0")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be greater than 0")

        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time: float | None = None

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = CircuitBreakerState.CLOSED
        self.last_failure_time = None

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = monotonic()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning("circuit_breaker_open", extra={"failures": self.failure_count})

    def allow_request(self) -> bool:
        if self.state == CircuitBreakerState.CLOSED:
            return True

        if self.state == CircuitBreakerState.OPEN:
            now = monotonic()
            if (
                self.last_failure_time is not None
                and (now - self.last_failure_time) > self.recovery_timeout
            ):
                self.state = CircuitBreakerState.HALF_OPEN
                logger.info("circuit_breaker_half_open")
                return True
            return False

        return True


# -----------------------------------------------------------------------------
# SERVICE INTERFACES
# -----------------------------------------------------------------------------


class VectorStore(Protocol):
    async def search(
        self,
        query_vector: np.ndarray,
        limit: int,
        threshold: float,
    ) -> list[tuple[UUID, float]]: ...


class GraphStore(Protocol):
    async def get_neighbors(self, node_id: UUID, depth: int) -> set[UUID]: ...


class FeatureStore(Protocol):
    async def get_features(self, entity_ids: list[UUID]) -> dict[UUID, dict[str, Any]]: ...


class OnlineFeatureStore(FeatureStore, Protocol):
    async def get_online_features(
        self,
        entity_id: str,
        feature_names: list[str],
    ) -> Any: ...


# -----------------------------------------------------------------------------
# UTILITIES
# -----------------------------------------------------------------------------


def _clip_score(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


class TemporalDecay:
    """Temporal decay for persisted wall-clock timestamps.

    Expects Unix epoch timestamps, not monotonic timestamps.
    """

    @staticmethod
    def calculate(
        timestamp_epoch_seconds: float,
        base_score: float,
        *,
        now_epoch_seconds: float | None = None,
    ) -> float:
        current = now_epoch_seconds if now_epoch_seconds is not None else time.time()
        age_hours = max(0.0, (current - timestamp_epoch_seconds) / 3600.0)
        decay = 1.0 / math.log10(age_hours + 10.0)
        return float(base_score) * decay


# -----------------------------------------------------------------------------
# CANDIDATE GENERATOR
# -----------------------------------------------------------------------------


class CandidateGenerator:
    """Generates candidates using hybrid vector + graph retrieval."""

    def __init__(
        self,
        vector_store: VectorStore,
        graph_store: GraphStore,
        config: PersonalizationConfig,
    ) -> None:
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.config = config

    @tracer.start_as_current_span("CandidateGenerator.generate")
    async def generate(self, query_vector: np.ndarray, context: dict[str, Any]) -> list[Candidate]:
        """Generate candidate set using hybrid retrieval."""
        del context
        span = trace.get_current_span()

        vector_results = await self.vector_store.search(
            query_vector,
            limit=self.config.candidate_limit,
            threshold=self.config.vector_similarity_threshold,
        )

        vector_score_map: dict[UUID, float] = {
            entity_id: _clip_score(score) for entity_id, score in vector_results
        }

        neighbor_sets = await asyncio.gather(
            *[
                self.graph_store.get_neighbors(
                    entity_id,
                    depth=self.config.graph_traversal_depth,
                )
                for entity_id, _ in vector_results
            ],
            return_exceptions=True,
        )

        graph_candidates: set[UUID] = set()
        for item in neighbor_sets:
            if isinstance(item, Exception):
                logger.warning("graph_expansion_failed", extra={"error": str(item)})
                continue
            graph_candidates.update(item)

        all_ids = set(vector_score_map.keys()) | graph_candidates

        span.set_attribute("candidates.vector_count", len(vector_results))
        span.set_attribute("candidates.graph_count", len(graph_candidates))
        span.set_attribute("candidates.total", len(all_ids))

        candidates: list[Candidate] = []
        for entity_id in all_ids:
            if entity_id in vector_score_map:
                score = vector_score_map[entity_id]
                source = "vector"
            else:
                score = self.config.graph_neighbor_base_score
                source = "graph"

            candidates.append(
                Candidate(
                    id=entity_id,
                    type="entity",
                    score=_clip_score(score),
                    metadata={"retrieval_source": source},
                )
            )

        candidates.sort(key=lambda item: (item.score, str(item.id)), reverse=True)
        return candidates[: self.config.candidate_limit]


# -----------------------------------------------------------------------------
# FEATURE HYDRATOR
# -----------------------------------------------------------------------------


class FeatureHydrator:
    """Hydrates candidates with features from memory and signals."""

    def __init__(self, feature_store: FeatureStore, config: PersonalizationConfig) -> None:
        self.feature_store = feature_store
        self.config = config

    @tracer.start_as_current_span("FeatureHydrator.hydrate")
    async def hydrate(self, candidates: list[Candidate]) -> list[Candidate]:
        """Add features to candidate set in batches."""
        span = trace.get_current_span()

        hydrated: list[Candidate] = []
        batches = [
            candidates[i : i + self.config.batch_size]
            for i in range(0, len(candidates), self.config.batch_size)
        ]

        for batch in batches:
            ids = [candidate.id for candidate in batch]
            features = await self.feature_store.get_features(ids)

            for candidate in batch:
                candidate_features = features.get(candidate.id, {})
                hydrated.append(candidate.with_features(candidate_features))

        span.set_attribute("features.hydrated_count", len(hydrated))
        return hydrated


# -----------------------------------------------------------------------------
# RANKERS
# -----------------------------------------------------------------------------


class LightRanker:
    """Fast heuristic ranker for initial filtering."""

    def __init__(
        self,
        config: PersonalizationConfig,
        feature_service: OnlineFeatureStore | None = None,
    ) -> None:
        self.config = config
        self.features = feature_service
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_breaker_failure_threshold,
            recovery_timeout=config.circuit_breaker_recovery_timeout,
        )

    @tracer.start_as_current_span("LightRanker.rank")
    async def rank(
        self,
        candidates: list[Candidate],
        context: dict[str, Any],
    ) -> list[RankedCandidate]:
        """Hybrid O(N) ranking using lightweight signals."""
        if not self.circuit_breaker.allow_request():
            raise CircuitBreakerError("LightRanker circuit breaker is open")

        try:
            user_id = context.get("user_id")
            user_signals: dict[str, Any] = {}

            if self.features is not None and user_id is not None:
                try:
                    vector = await self.features.get_online_features(
                        str(user_id),
                        ["user_affinity", "agent_success_rate", "affinity:concise"],
                    )
                    user_signals = dict(getattr(vector, "features", {}) or {})
                except Exception as exc:
                    logger.warning("light_ranker_online_features_failed", extra={"error": str(exc)})

            scored: list[tuple[float, Candidate]] = []
            for candidate in candidates:
                score = self._calculate_hybrid_score(candidate, user_signals, context)
                scored.append((score, candidate))

            scored.sort(key=lambda item: (item[0], str(item[1].id)), reverse=True)
            scored = scored[: self.config.light_ranker_cutoff]

            self.circuit_breaker.record_success()

            return [
                RankedCandidate(
                    id=candidate.id,
                    type=candidate.type,
                    score=score,
                    features=candidate.features,
                    metadata=candidate.metadata,
                    rank=index + 1,
                    ranker_type=RankerType.LIGHT,
                )
                for index, (score, candidate) in enumerate(scored)
            ]
        except Exception:
            self.circuit_breaker.record_failure()
            raise

    def _calculate_hybrid_score(
        self,
        candidate: Candidate,
        user_signals: dict[str, Any],
        context: dict[str, Any],
    ) -> float:
        del context

        score = float(candidate.score)

        ts = candidate.metadata.get("timestamp") or candidate.metadata.get("ts")
        ts_float = _safe_float(ts, default=-1.0)
        if ts_float > 0.0:
            score = TemporalDecay.calculate(ts_float, score)

        affinity = _safe_float(user_signals.get("user_affinity"), 0.5)
        success = _safe_float(user_signals.get("agent_success_rate"), 0.7)
        concise_affinity = _safe_float(user_signals.get("affinity:concise"), 0.0)

        if candidate.type == "tool":
            score *= 0.5 + success

        if concise_affinity > 0.5 and candidate.features.get("concise"):
            score *= 1.0 + (0.2 * concise_affinity)

        score *= 0.75 + (0.5 * affinity)
        return _clip_score(score)


class HeavyRanker:
    """Deep semantic ranker for high-precision re-ranking."""

    def __init__(
        self,
        config: PersonalizationConfig,
        feature_service: OnlineFeatureStore | None = None,
    ) -> None:
        self.config = config
        self.features = feature_service
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_breaker_failure_threshold,
            recovery_timeout=config.circuit_breaker_recovery_timeout,
        )

    @tracer.start_as_current_span("HeavyRanker.rank")
    async def rank(
        self,
        candidates: list[Candidate],
        context: dict[str, Any],
    ) -> list[RankedCandidate]:
        """Contextual re-ranking with cross-feature interaction."""
        if not self.circuit_breaker.allow_request():
            raise CircuitBreakerError("HeavyRanker circuit breaker is open")

        try:
            scored: list[tuple[float, Candidate]] = []
            for candidate in candidates:
                score = self._deep_score(candidate, context)
                scored.append((score, candidate))

            scored.sort(key=lambda item: (item[0], str(item[1].id)), reverse=True)
            scored = scored[: self.config.heavy_ranker_cutoff]

            self.circuit_breaker.record_success()

            return [
                RankedCandidate(
                    id=candidate.id,
                    type=candidate.type,
                    score=score,
                    features=candidate.features,
                    metadata=candidate.metadata,
                    rank=index + 1,
                    ranker_type=RankerType.HEAVY,
                )
                for index, (score, candidate) in enumerate(scored)
            ]
        except Exception:
            self.circuit_breaker.record_failure()
            raise

    def _deep_score(self, candidate: Candidate, context: dict[str, Any]) -> float:
        base = float(candidate.score)
        intent = str(context.get("intent", "general"))

        alignment = 0.0
        if intent == "utility" and candidate.type == "tool":
            alignment += 0.4

        depth = _safe_float(candidate.features.get("interaction_depth"), 0.0)
        alignment += depth * 0.1

        novelty = _safe_float(candidate.features.get("novelty"), 0.0)
        alignment += min(0.2, novelty * 0.05)

        return _clip_score(base + alignment)


class RecapRanker:
    """Diversity-aware final ranking."""

    def __init__(self, config: PersonalizationConfig) -> None:
        self.config = config

    @tracer.start_as_current_span("RecapRanker.rank")
    async def rank(
        self,
        candidates: list[Candidate],
        context: dict[str, Any],
    ) -> list[RankedCandidate]:
        """Apply diversity and type balancing without weakening configured caps."""
        del context
        span = trace.get_current_span()

        type_counts: dict[str, int] = {}
        result: list[RankedCandidate] = []

        max_per_type = self.config.recap_max_per_type

        for candidate in sorted(
            candidates, key=lambda item: (item.score, str(item.id)), reverse=True
        ):
            current = type_counts.get(candidate.type, 0)
            if current >= max_per_type:
                continue

            type_counts[candidate.type] = current + 1
            result.append(
                RankedCandidate(
                    id=candidate.id,
                    type=candidate.type,
                    score=candidate.score,
                    features=candidate.features,
                    metadata=candidate.metadata,
                    rank=len(result) + 1,
                    ranker_type=RankerType.RECAP,
                )
            )

        span.set_attribute("ranker.recap.result_count", len(result))
        span.set_attribute("ranker.recap.unique_types", len(type_counts))
        return result


# -----------------------------------------------------------------------------
# ONLINE FEATURE SERVER
# -----------------------------------------------------------------------------


class OnlineFeatureServer:
    """Real-time feature serving with in-memory cache."""

    def __init__(self, feature_store: FeatureStore, config: PersonalizationConfig) -> None:
        self.feature_store = feature_store
        self.config = config
        self._cache: dict[UUID, tuple[float, dict[str, Any]]] = {}
        self._cache_ttl = 60.0

    @tracer.start_as_current_span("OnlineFeatureServer.get_features")
    async def get_features(self, entity_ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
        now = monotonic()

        cached: dict[UUID, dict[str, Any]] = {}
        missing: list[UUID] = []

        for entity_id in entity_ids:
            if entity_id in self._cache:
                ts, features = self._cache[entity_id]
                if now - ts < self._cache_ttl:
                    cached[entity_id] = features
                    continue
            missing.append(entity_id)

        if missing:
            loaded = await self.feature_store.get_features(missing)
            for entity_id, features in loaded.items():
                self._cache[entity_id] = (now, features)
                cached[entity_id] = features

        return cached

    def invalidate_cache(self, entity_id: UUID | None = None) -> None:
        if entity_id is not None:
            self._cache.pop(entity_id, None)
        else:
            self._cache.clear()


# -----------------------------------------------------------------------------
# PERSONALIZATION ENGINE
# -----------------------------------------------------------------------------


class PersonalizationEngine:
    """Full personalization pipeline implementation."""

    def __init__(
        self,
        config: PersonalizationConfig,
        vector_store: VectorStore,
        graph_store: GraphStore,
        feature_store: FeatureStore,
        online_feature_store: OnlineFeatureStore | None = None,
    ) -> None:
        self.config = config

        effective_online_store = online_feature_store or (
            feature_store if hasattr(feature_store, "get_online_features") else None
        )

        self.candidate_generator = CandidateGenerator(vector_store, graph_store, config)
        self.feature_hydrator = FeatureHydrator(feature_store, config)
        self.light_ranker = LightRanker(config, feature_service=effective_online_store)
        self.heavy_ranker = HeavyRanker(config, feature_service=effective_online_store)
        self.recap_ranker = RecapRanker(config)
        self.feature_server = OnlineFeatureServer(feature_store, config)

    @tracer.start_as_current_span("PersonalizationEngine.rank")
    async def rank(
        self,
        query_vector: np.ndarray,
        context: dict[str, Any],
        candidates: list[Candidate] | None = None,
        stream: bool = False,
    ) -> list[RankedCandidate] | AsyncGenerator[RankedCandidate]:
        """Execute full ranking pipeline."""
        span = trace.get_current_span()

        try:
            async with asyncio.timeout(self.config.timeout_ms / 1000.0):
                if candidates is None:
                    candidates = await self.candidate_generator.generate(query_vector, context)

                span.set_attribute("pipeline.candidates", len(candidates))

                if not candidates:
                    span.set_status(Status(StatusCode.OK))
                    return []

                hydrated = await self.feature_hydrator.hydrate(candidates)
                span.set_attribute("pipeline.hydrated", len(hydrated))

                light_ranked = await self.light_ranker.rank(hydrated, context)
                span.set_attribute("pipeline.light_ranked", len(light_ranked))

                heavy_input = [
                    Candidate(
                        id=item.id,
                        type=item.type,
                        score=item.score,
                        features=item.features,
                        metadata=item.metadata,
                    )
                    for item in light_ranked
                ]

                heavy_ranked = await self.heavy_ranker.rank(heavy_input, context)
                span.set_attribute("pipeline.heavy_ranked", len(heavy_ranked))

                recap_input = [
                    Candidate(
                        id=item.id,
                        type=item.type,
                        score=item.score,
                        features=item.features,
                        metadata=item.metadata,
                    )
                    for item in heavy_ranked
                ]

                final = await self.recap_ranker.rank(recap_input, context)
                span.set_attribute("pipeline.final", len(final))
                span.set_status(Status(StatusCode.OK))

                if stream:
                    return self._stream_results(final)

                return final

        except TimeoutError as exc:
            span.set_status(Status(StatusCode.ERROR, "personalization_timeout"))
            logger.exception("personalization_pipeline_timed_out")
            raise RuntimeError("Personalization pipeline timed out") from exc
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            logger.exception("personalization_pipeline_failed")
            raise

    async def _stream_results(
        self,
        candidates: list[RankedCandidate],
    ) -> AsyncGenerator[RankedCandidate]:
        """Stream results one by one with minimal delay."""
        for candidate in candidates:
            yield candidate
            await asyncio.sleep(0)

    async def warmup(self) -> None:
        logger.info("personalization_engine_warmup_complete")


# -----------------------------------------------------------------------------
# FACTORY
# -----------------------------------------------------------------------------


def create_personalization_engine(
    vector_store: VectorStore,
    graph_store: GraphStore,
    feature_store: FeatureStore,
    online_feature_store: OnlineFeatureStore | None = None,
    **kwargs: Any,
) -> PersonalizationEngine:
    """Factory function to create a configured personalization engine."""
    config = PersonalizationConfig(**kwargs)
    return PersonalizationEngine(
        config=config,
        vector_store=vector_store,
        graph_store=graph_store,
        feature_store=feature_store,
        online_feature_store=online_feature_store,
    )
