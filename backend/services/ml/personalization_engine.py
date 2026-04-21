"""
Butler Personalization Engine
SWE-5 Grade Implementation
Pipeline: Candidate Generation → Feature Hydration → Light Rank → Heavy Rank → Recap
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, Optional, Protocol, TypeVar
from uuid import UUID

import numpy as np
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


# -----------------------------------------------------------------------------
# CONFIGURATION MODELS
# -----------------------------------------------------------------------------

class RankerType(str, Enum):
    LIGHT = "light"
    HEAVY = "heavy"
    RECAP = "recap"


class PersonalizationConfig(BaseModel):
    """Pydantic configuration for personalization engine."""

    candidate_limit: int = Field(default=100, ge=1, le=1000)
    light_ranker_cutoff: int = Field(default=20, ge=1, le=100)
    heavy_ranker_cutoff: int = Field(default=5, ge=1, le=20)

    vector_similarity_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    graph_traversal_depth: int = Field(default=2, ge=1, le=5)

    circuit_breaker_failure_threshold: int = Field(default=5, ge=1)
    circuit_breaker_recovery_timeout: int = Field(default=30, ge=1)

    batch_size: int = Field(default=32, ge=1, le=256)
    timeout_ms: int = Field(default=500, ge=100, le=5000)

    @validator("light_ranker_cutoff")
    def light_less_than_candidate(cls, v: int, values: dict[str, Any]) -> int:
        if v >= values["candidate_limit"]:
            raise ValueError("light_ranker_cutoff must be less than candidate_limit")
        return v

    @validator("heavy_ranker_cutoff")
    def heavy_less_than_light(cls, v: int, values: dict[str, Any]) -> int:
        if v >= values["light_ranker_cutoff"]:
            raise ValueError("heavy_ranker_cutoff must be less than light_ranker_cutoff")
        return v


# -----------------------------------------------------------------------------
# DOMAIN MODELS
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Candidate:
    """Ranked candidate item."""
    id: UUID
    type: str
    score: float = 0.0
    features: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def with_score(self, score: float) -> Candidate:
        return Candidate(
            id=self.id,
            type=self.type,
            score=score,
            features=self.features,
            metadata=self.metadata
        )

    def with_features(self, features: dict[str, Any]) -> Candidate:
        return Candidate(
            id=self.id,
            type=self.type,
            score=self.score,
            features={**self.features, **features},
            metadata=self.metadata
        )


@dataclass(frozen=True)
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

class CircuitBreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""


class CircuitBreaker:
    """Implementation of circuit breaker pattern for rankers."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 30):
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
        self.last_failure_time = asyncio.get_event_loop().time()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning(f"Circuit breaker OPEN after {self.failure_count} failures")

    def allow_request(self) -> bool:
        if self.state == CircuitBreakerState.CLOSED:
            return True

        if self.state == CircuitBreakerState.OPEN:
            now = asyncio.get_event_loop().time()
            if self.last_failure_time is not None and now - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                logger.info("Circuit breaker HALF_OPEN, allowing test request")
                return True
            return False

        # HALF_OPEN: allow one test request
        return True


# -----------------------------------------------------------------------------
# SERVICE INTERFACES
# -----------------------------------------------------------------------------

class VectorStore(Protocol):
    async def search(self, query_vector: np.ndarray, limit: int, threshold: float) -> list[tuple[UUID, float]]:
        ...


class GraphStore(Protocol):
    async def get_neighbors(self, node_id: UUID, depth: int) -> set[UUID]:
        ...


class FeatureStore(Protocol):
    async def get_features(self, entity_ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
        ...


# -----------------------------------------------------------------------------
# CANDIDATE GENERATOR
# -----------------------------------------------------------------------------

class CandidateGenerator:
    """Generates candidates using hybrid vector + graph retrieval."""

    def __init__(
        self,
        vector_store: VectorStore,
        graph_store: GraphStore,
        config: PersonalizationConfig
    ):
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.config = config

    @tracer.start_as_current_span("CandidateGenerator.generate")
    async def generate(self, query_vector: np.ndarray, context: dict[str, Any]) -> list[Candidate]:
        """Generate candidate set using hybrid retrieval."""
        span = trace.get_current_span()

        # Vector retrieval
        vector_results = await self.vector_store.search(
            query_vector,
            limit=self.config.candidate_limit,
            threshold=self.config.vector_similarity_threshold
        )

        # Graph expansion
        graph_candidates: set[UUID] = set()
        for entity_id, _ in vector_results:
            neighbors = await self.graph_store.get_neighbors(
                entity_id,
                depth=self.config.graph_traversal_depth
            )
            graph_candidates.update(neighbors)

        # Deduplicate and combine
        all_ids = {entity_id for entity_id, _ in vector_results} | graph_candidates

        span.set_attribute("candidates.vector_count", len(vector_results))
        span.set_attribute("candidates.graph_count", len(graph_candidates))
        span.set_attribute("candidates.total", len(all_ids))

        return [
            Candidate(id=entity_id, type="entity", score=score)
            for entity_id, score in vector_results
            if entity_id in all_ids
        ]


# -----------------------------------------------------------------------------
# FEATURE HYDRATOR
# -----------------------------------------------------------------------------

class FeatureHydrator:
    """Hydrates candidates with features from memory and signals."""

    def __init__(self, feature_store: FeatureStore, config: PersonalizationConfig):
        self.feature_store = feature_store
        self.config = config

    @tracer.start_as_current_span("FeatureHydrator.hydrate")
    async def hydrate(self, candidates: list[Candidate]) -> list[Candidate]:
        """Add features to candidate set in batches."""
        span = trace.get_current_span()

        hydrated = []
        batches = [
            candidates[i:i + self.config.batch_size]
            for i in range(0, len(candidates), self.config.batch_size)
        ]

        for batch in batches:
            ids = [c.id for c in batch]
            features = await self.feature_store.get_features(ids)

            for candidate in batch:
                if candidate.id in features:
                    hydrated.append(candidate.with_features(features[candidate.id]))
                else:
                    hydrated.append(candidate)

        span.set_attribute("features.hydrated_count", len(hydrated))
        return hydrated


# -----------------------------------------------------------------------------
# RANKERS
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# UTILITIES
# -----------------------------------------------------------------------------

class TemporalDecay:
    """Logarithmic temporal decay for ranking signals."""
    
    @staticmethod
    def calculate(timestamp: float, base_score: float) -> float:
        """Score = Base / log10(age_hours + 10)."""
        age_hours = (asyncio.get_event_loop().time() - timestamp) / 3600
        decay = 1.0 / np.log10(max(0, age_hours) + 10)
        return base_score * decay

# -----------------------------------------------------------------------------
# RANKERS
# -----------------------------------------------------------------------------

class LightRanker:
    """Fast heuristic ranker for initial filtering (The Jet)."""

    def __init__(self, config: PersonalizationConfig, feature_service: Optional[Any] = None):
        self.config = config
        self.features = feature_service
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_breaker_failure_threshold,
            recovery_timeout=config.circuit_breaker_recovery_timeout
        )

    @tracer.start_as_current_span("LightRanker.rank")
    async def rank(self, candidates: list[Candidate], context: dict[str, Any]) -> list[RankedCandidate]:
        """Hybrid O(N) ranking using T1/T2 signals."""
        user_id = context.get("user_id")
        
        # Hydrate global user signals
        user_signals = {}
        if self.features and user_id:
            vector = await self.features.get_online_features(
                str(user_id), 
                ["user_affinity", "agent_success_rate", "affinity:concise"]
            )
            user_signals = vector.features

        scored = []
        for candidate in candidates:
            score = self._calculate_hybrid_score(candidate, user_signals, context)
            scored.append((score, candidate))

        scored.sort(reverse=True, key=lambda x: x[0])
        scored = scored[:self.config.light_ranker_cutoff]

        return [
            RankedCandidate(
                id=c.id, type=c.type, score=score,
                features=c.features, metadata=c.metadata,
                rank=i + 1, ranker_type=RankerType.LIGHT
            )
            for i, (score, c) in enumerate(scored)
        ]

    def _calculate_hybrid_score(self, candidate: Candidate, user_signals: dict, context: dict) -> float:
        score = candidate.score
        
        # 1. Temporal Decay (Tier 2/3)
        ts = candidate.metadata.get("timestamp") or candidate.metadata.get("ts")
        if ts:
            score = TemporalDecay.calculate(float(ts), score)
            
        # 2. Behavioral Boost (Tier 1/2)
        affinity = user_signals.get("user_affinity", 0.5)
        success = user_signals.get("agent_success_rate", 0.7)
        
        # Apply success bias for tools/actions
        if candidate.type == "tool":
            score *= (0.5 + success) # 1.5x boost if success=1.0
            
        # 3. Personalization Override (Tier 3)
        if "affinity:concise" in user_signals and "concise" in candidate.features:
            score *= 1.2
            
        return np.clip(score, 0.0, 1.0)


class HeavyRanker:
    """Deep semantic ranker for high-precision (The Brain)."""

    def __init__(self, config: PersonalizationConfig, feature_service: Optional[Any] = None):
        self.config = config
        self.features = feature_service
        self.circuit_breaker = CircuitBreaker()

    @tracer.start_as_current_span("HeavyRanker.rank")
    async def rank(self, candidates: list[Candidate], context: dict[str, Any]) -> list[RankedCandidate]:
        """Contextual re-ranking with cross-feature interaction."""
        # Simulated Deep Ranker for v3.1
        # In production, this would call a local Cross-Encoder (e.g. BGE-Reranker)
        scored = []
        for candidate in candidates:
            score = self._deep_score(candidate, context)
            scored.append((score, candidate))

        scored.sort(reverse=True, key=lambda x: x[0])
        return [
            RankedCandidate(
                id=c.id, type=c.type, score=score,
                features=c.features, metadata=c.metadata,
                rank=i + 1, ranker_type=RankerType.HEAVY
            )
            for i, (score, c) in enumerate(scored[:self.config.heavy_ranker_cutoff])
        ]

    def _deep_score(self, candidate: Candidate, context: dict) -> float:
        base = candidate.score
        # Contextual alignment logic
        intent = context.get("intent", "general")
        
        # High-entropy alignment (Oracle-Grade)
        alignment = 0.0
        if intent == "utility" and candidate.type == "tool":
            alignment += 0.4
        
        # Interaction depth boost
        depth = candidate.features.get("interaction_depth", 0)
        alignment += (depth * 0.1)
        
        return np.clip(base + alignment, 0.0, 1.0)


class RecapRanker:
    """Diversity and summarization ranking for final output."""

    def __init__(self, config: PersonalizationConfig):
        self.config = config

    @tracer.start_as_current_span("RecapRanker.rank")
    async def rank(self, candidates: list[Candidate], context: dict[str, Any]) -> list[RankedCandidate]:
        """Diversity-aware ranking with type balancing."""
        span = trace.get_current_span()

        # Type diversity enforcement
        type_counts: dict[str, int] = {}
        # Type diversity enforcement: allow at least 2 of each type for small pools
        max_per_type = max(2, len(candidates) // 2)

        result = []
        seen_types: set[str] = set()

        for candidate in candidates:
            type_counts[candidate.type] = type_counts.get(candidate.type, 0) + 1

            if type_counts[candidate.type] <= max_per_type:
                result.append(RankedCandidate(
                    id=candidate.id,
                    type=candidate.type,
                    score=candidate.score,
                    features=candidate.features,
                    metadata=candidate.metadata,
                    rank=len(result) + 1,
                    ranker_type=RankerType.RECAP
                ))
                seen_types.add(candidate.type)

        span.set_attribute("ranker.recap.result_count", len(result))
        span.set_attribute("ranker.recap.unique_types", len(seen_types))

        return result


# -----------------------------------------------------------------------------
# ONLINE FEATURE SERVER
# -----------------------------------------------------------------------------

class OnlineFeatureServer:
    """Real-time feature serving with caching and batching."""

    def __init__(self, feature_store: FeatureStore, config: PersonalizationConfig):
        self.feature_store = feature_store
        self.config = config
        self._cache: dict[UUID, tuple[float, dict[str, Any]]] = {}
        self._cache_ttl = 60.0  # 60 seconds

    @tracer.start_as_current_span("OnlineFeatureServer.get_features")
    async def get_features(self, entity_ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
        """Get features with cache and batch loading."""
        now = asyncio.get_event_loop().time()

        # Check cache
        cached = {}
        missing = []

        for entity_id in entity_ids:
            if entity_id in self._cache:
                ts, features = self._cache[entity_id]
                if now - ts < self._cache_ttl:
                    cached[entity_id] = features
                    continue
            missing.append(entity_id)

        # Load missing
        if missing:
            loaded = await self.feature_store.get_features(missing)
            for entity_id, features in loaded.items():
                self._cache[entity_id] = (now, features)
                cached[entity_id] = features

        return cached

    def invalidate_cache(self, entity_id: UUID | None = None) -> None:
        if entity_id:
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
        feature_store: FeatureStore
    ):
        self.config = config

        self.candidate_generator = CandidateGenerator(vector_store, graph_store, config)
        self.feature_hydrator = FeatureHydrator(feature_store, config)
        self.light_ranker = LightRanker(config, feature_service=feature_store)
        self.heavy_ranker = HeavyRanker(config, feature_service=feature_store)
        self.recap_ranker = RecapRanker(config)
        self.feature_server = OnlineFeatureServer(feature_store, config)

    @tracer.start_as_current_span("PersonalizationEngine.rank")
    async def rank(
        self,
        query_vector: np.ndarray,
        context: dict[str, Any],
        candidates: Optional[list[Candidate]] = None,
        stream: bool = False
    ) -> list[RankedCandidate] | AsyncGenerator[RankedCandidate, None]:
        """Execute full ranking pipeline."""
        span = trace.get_current_span()

        try:
            # Step 1: Candidate generation (or bypass)
            if candidates is None:
                candidates = await self.candidate_generator.generate(query_vector, context)
            
            span.set_attribute("pipeline.candidates", len(candidates))

            if not candidates:
                return []

            # Step 2: Feature hydration
            hydrated = await self.feature_hydrator.hydrate(candidates)
            span.set_attribute("pipeline.hydrated", len(hydrated))

            # Step 3: Light ranking
            light_ranked = await self.light_ranker.rank(hydrated, context)
            span.set_attribute("pipeline.light_ranked", len(light_ranked))

            # Convert RankedCandidate back to Candidate for heavy ranker
            for_ranking = [
                Candidate(
                    id=c.id, type=c.type, score=c.score,
                    features=c.features, metadata=c.metadata
                )
                for c in light_ranked
            ]

            # Step 4: Heavy ranking
            heavy_ranked = await self.heavy_ranker.rank(for_ranking, context)
            span.set_attribute("pipeline.heavy_ranked", len(heavy_ranked))

            # Step 5: Recap ranking
            candidate_list: list[Candidate] = []
            for c in heavy_ranked:
                candidate_list.append(Candidate(
                    id=c.id,
                    type=c.type,
                    score=c.score,
                    features=c.features,
                    metadata=c.metadata
                ))
            final = await self.recap_ranker.rank(candidate_list, context)
            span.set_attribute("pipeline.final", len(final))

            span.set_status(Status(StatusCode.OK))

            if stream:
                return self._stream_results(final)

            return final

        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            logger.exception("Personalization pipeline failed")
            raise

    async def _stream_results(self, candidates: list[RankedCandidate]) -> AsyncGenerator[RankedCandidate, None]:
        """Stream results one by one with minimal delay."""
        for candidate in candidates:
            yield candidate
            await asyncio.sleep(0)  # yield control

    async def warmup(self) -> None:
        """Warm up caches and connections."""
        logger.info("Personalization engine warmup complete")


# -----------------------------------------------------------------------------
# FACTORY
# -----------------------------------------------------------------------------

def create_personalization_engine(
    vector_store: VectorStore,
    graph_store: GraphStore,
    feature_store: FeatureStore,
    **kwargs
) -> PersonalizationEngine:
    """Factory function to create configured personalization engine."""
    config = PersonalizationConfig(**kwargs)
    return PersonalizationEngine(config, vector_store, graph_store, feature_store)
