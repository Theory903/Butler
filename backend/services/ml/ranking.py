from __future__ import annotations

import math
import time

import structlog

from domain.ml.contracts import RankingContract, RerankResult, RetrievalCandidate
from services.ml.features import FeatureService

logger = structlog.get_logger(__name__)


def _clamp_score(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def _coerce_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_candidate_metadata(candidate: RetrievalCandidate) -> dict[str, object]:
    return candidate.metadata if isinstance(candidate.metadata, dict) else {}


def _compute_recency_decay(
    timestamp_value: object,
    *,
    now_wall_clock: float,
    half_life_hours: float = 24.0 * 7,
) -> float:
    """Compute a smooth recency multiplier in the range (0, 1].

    Expects wall-clock timestamps (Unix epoch seconds) in metadata.
    """
    ts = _coerce_float(timestamp_value, default=-1.0)
    if ts <= 0.0:
        return 1.0

    age_seconds = max(0.0, now_wall_clock - ts)
    age_hours = age_seconds / 3600.0

    if half_life_hours <= 0.0:
        return 1.0

    return 0.5 ** (age_hours / half_life_hours)


class LightRanker(RankingContract):
    """Fast behavioral-aware ranker for Butler candidate blending.

    Signals:
    1. Base retrieval score
    2. Recency decay
    3. User affinity / success signals
    4. Explicit metadata overrides
    """

    def __init__(
        self,
        feature_service: FeatureService | None = None,
        *,
        recency_half_life_hours: float = 24.0 * 7,
        affinity_boost_threshold: float = 0.8,
        affinity_boost_multiplier: float = 1.15,
        low_trust_threshold: float = 0.4,
        low_trust_penalty_multiplier: float = 0.9,
        high_affinity_metadata_multiplier: float = 1.2,
    ) -> None:
        self._features = feature_service
        self._recency_half_life_hours = recency_half_life_hours
        self._affinity_boost_threshold = affinity_boost_threshold
        self._affinity_boost_multiplier = affinity_boost_multiplier
        self._low_trust_threshold = low_trust_threshold
        self._low_trust_penalty_multiplier = low_trust_penalty_multiplier
        self._high_affinity_metadata_multiplier = high_affinity_metadata_multiplier

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievalCandidate],
        user_id: str | None = None,
    ) -> list[RerankResult]:
        """Rank candidates based on retrieval score plus lightweight user/context signals."""
        del query

        if not candidates:
            return []

        start_monotonic = time.monotonic()
        now_wall_clock = time.time()

        user_signals: dict[str, float] = {}
        if self._features is not None and user_id:
            try:
                vector = await self._features.get_online_features(
                    user_id,
                    ["user_affinity", "agent_success_rate"],
                )
                user_signals = {key: _coerce_float(value) for key, value in vector.features.items()}
                logger.debug(
                    "light_ranking_signals_fetched",
                    user_id=user_id,
                    signals=user_signals,
                )
            except Exception as exc:
                logger.warning(
                    "light_ranking_signals_failed",
                    user_id=user_id,
                    error=str(exc),
                )

        affinity = user_signals.get("user_affinity", 0.5)
        trust = user_signals.get("agent_success_rate", 0.7)

        scored_results: list[RerankResult] = []

        for idx, candidate in enumerate(candidates):
            metadata = _extract_candidate_metadata(candidate)
            score = _clamp_score(candidate.score)

            timestamp_value = metadata.get("timestamp", metadata.get("ts"))
            recency_multiplier = _compute_recency_decay(
                timestamp_value,
                now_wall_clock=now_wall_clock,
                half_life_hours=self._recency_half_life_hours,
            )
            score *= recency_multiplier

            if affinity > self._affinity_boost_threshold:
                score *= self._affinity_boost_multiplier

            if trust < self._low_trust_threshold:
                score *= self._low_trust_penalty_multiplier

            if metadata.get("affinity") == "high":
                score *= self._high_affinity_metadata_multiplier

            scored_results.append(
                RerankResult(
                    index=idx,
                    score=_clamp_score(score),
                    metadata={
                        **metadata,
                        "ranker": "light",
                        "affinity": affinity,
                        "trust": trust,
                        "recency_multiplier": recency_multiplier,
                    },
                )
            )

        sorted_results = sorted(
            scored_results,
            key=lambda item: item.score,
            reverse=True,
        )

        latency_ms = (time.monotonic() - start_monotonic) * 1000.0
        logger.debug(
            "light_ranking_completed",
            count=len(candidates),
            duration_ms=round(latency_ms, 2),
        )
        return sorted_results


class HeavyRanker(RankingContract):
    """Deeper multi-signal ranker for Butler.

    Signals:
    1. Base retrieval score
    2. Behavioral affinity / trust
    3. Recency decay
    4. Source bias / diversity proxy
    5. Optional interaction-depth signal
    """

    def __init__(
        self,
        feature_service: FeatureService | None = None,
        *,
        recency_decay_strength: float = 0.05,
        ambient_source_penalty: float = 0.95,
        behavioral_boost_cap: float = 0.25,
    ) -> None:
        self._features = feature_service
        self._recency_decay_strength = recency_decay_strength
        self._ambient_source_penalty = ambient_source_penalty
        self._behavioral_boost_cap = behavioral_boost_cap
        logger.info("heavy_ranker_initialized")

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievalCandidate],
        user_id: str | None = None,
    ) -> list[RerankResult]:
        """Execute deeper reranking over candidates."""
        if not candidates:
            return []

        start_monotonic = time.monotonic()
        now_wall_clock = time.time()

        user_signals: dict[str, float] = {}
        if self._features is not None and user_id:
            try:
                vector = await self._features.get_online_features(
                    user_id,
                    [
                        "user_affinity",
                        "agent_trust_score",
                        "recency_bias",
                        "interaction_depth",
                    ],
                )
                user_signals = {key: _coerce_float(value) for key, value in vector.features.items()}
            except Exception as exc:
                logger.warning("heavy_ranking_feature_fetch_failed", error=str(exc))

        affinity = user_signals.get("user_affinity", 0.5)
        trust = user_signals.get("agent_trust_score", 0.7)
        interaction_depth_signal = user_signals.get("interaction_depth", 0.0)

        results: list[RerankResult] = []

        for idx, candidate in enumerate(candidates):
            metadata = _extract_candidate_metadata(candidate)
            score = _clamp_score(candidate.score)

            behavioral_boost = (affinity * 0.4) + (trust * 0.6)
            score *= 1.0 + min(
                self._behavioral_boost_cap, behavioral_boost * self._behavioral_boost_cap
            )

            ts = metadata.get("timestamp", metadata.get("ts"))
            ts_float = _coerce_float(ts, default=-1.0)
            if ts_float > 0.0:
                age_hours = max(0.0, (now_wall_clock - ts_float) / 3600.0)
                decay = 1.0 / (1.0 + (math.sqrt(age_hours) * self._recency_decay_strength))
                score *= decay

            source = str(metadata.get("source", "unknown"))
            if source == "ambient":
                score *= self._ambient_source_penalty

            candidate_depth = _coerce_float(metadata.get("interaction_depth"), default=0.0)
            combined_depth = max(candidate_depth, interaction_depth_signal)
            score += min(0.15, combined_depth * 0.05)

            results.append(
                RerankResult(
                    index=idx,
                    score=_clamp_score(score),
                    metadata={
                        **metadata,
                        "ranker": "heavy",
                        "affinity": affinity,
                        "trust": trust,
                        "interaction_depth_signal": combined_depth,
                    },
                )
            )

        sorted_results = sorted(
            results,
            key=lambda item: item.score,
            reverse=True,
        )

        latency_ms = (time.monotonic() - start_monotonic) * 1000.0
        logger.info(
            "heavy_ranking_completed",
            query_len=len(query),
            candidates=len(candidates),
            latency_ms=round(latency_ms, 2),
        )
        return sorted_results
