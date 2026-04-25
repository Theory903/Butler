from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from domain.ml.contracts import FeatureStoreContract, FeatureVector

logger = logging.getLogger(__name__)


class SignalSanitizer:
    """Sanitize feature values for downstream ranking/runtime use.

    Important:
    - This is NOT formal differential privacy.
    - It only clamps/coerces values into stable numeric ranges.
    - Formal DP would require an explicit privacy mechanism, epsilon accounting,
      composition policy, and governance outside this class.
    """

    @staticmethod
    def sanitize(features: dict[str, float]) -> dict[str, float]:
        sanitized: dict[str, float] = {}
        for key, value in features.items():
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue

            if key.startswith("affinity:") or key in {
                "user_affinity",
                "agent_success_rate",
                "agent_trust_score",
                "recency_bias",
                "search_preference",
            }:
                sanitized[key] = round(max(0.0, min(1.0, numeric)), 4)
            else:
                sanitized[key] = round(numeric, 4)

        return sanitized


class SignalScrubber:
    """Compatibility wrapper for privacy-safe feature scrubbing."""

    def scrub_features(self, features: dict[str, float]) -> dict[str, float]:
        return SignalSanitizer.sanitize(features)


class FeatureService(FeatureStoreContract):
    """3-tier behavioral signal store.

    Tiers:
    - T1: short-term session signals in Redis
    - T2: mid-term habit signals in Redis
    - T3: long-term identity/preference hints from the knowledge graph

    Merge priority:
    T1 > T3 > T2 > fallback
    """

    def __init__(
        self,
        redis: Any,
        graph_repo: Any | None = None,
        *,
        key_prefix: str = "butler:signals:",
        session_ttl_seconds: int = 7200,
        habit_ttl_seconds: int = 2592000,
        version: str = "v3.2-hybrid",
    ) -> None:
        self._redis = redis
        self._graph = graph_repo
        self._prefix = key_prefix
        self._session_ttl_seconds = session_ttl_seconds
        self._habit_ttl_seconds = habit_ttl_seconds
        self._version = version
        self._sanitizer = SignalSanitizer()

    async def get_online_features(
        self,
        entity_id: str,
        feature_names: list[str],
    ) -> FeatureVector:
        """Fetch unified T1/T2/T3 features for one entity."""
        started_at = time.monotonic()
        session_key = self._session_key(entity_id)
        habit_key = self._habit_key(entity_id)

        try:
            async with self._redis.pipeline(transaction=False) as pipe:
                pipe.hgetall(session_key)
                pipe.hgetall(habit_key)
                raw_t1, raw_t2 = await pipe.execute()

            t1_map = self._normalize_redis_hash(raw_t1)
            t2_map = self._normalize_redis_hash(raw_t2)
            t3_map = await self._get_tier3_signals(entity_id) if self._graph is not None else {}

            requested_names = feature_names or self._default_feature_names()
            merged: dict[str, float] = {}

            for name in requested_names:
                if name in t1_map:
                    merged[name] = t1_map[name]
                elif name in t3_map:
                    merged[name] = t3_map[name]
                elif name in t2_map:
                    merged[name] = t2_map[name]
                else:
                    merged[name] = self._get_signal_fallback(name)

            sanitized = self._sanitizer.sanitize(merged)

            return FeatureVector(
                features=sanitized,
                timestamp=time.time(),
                version=self._version,
            )

        except Exception as exc:
            latency_ms = (time.monotonic() - started_at) * 1000.0
            logger.error(
                "feature_retrieval_failed",
                extra={
                    "entity_id": entity_id,
                    "error": str(exc),
                    "latency_ms": round(latency_ms, 2),
                },
            )
            return FeatureVector(
                features={},
                timestamp=time.time(),
                version=f"{self._version}-error",
            )

    async def get_features(self, entity_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
        """Batch fetch features for multiple entities.

        Used by hydrators/rankers that need broad candidate enrichment.
        """
        if not entity_ids:
            return {}

        tasks = [
            self.get_online_features(str(entity_id), self._default_feature_names())
            for entity_id in entity_ids
        ]
        vectors = await asyncio.gather(*tasks, return_exceptions=True)

        results: dict[uuid.UUID, dict[str, Any]] = {}
        for entity_id, vector in zip(entity_ids, vectors, strict=False):
            if isinstance(vector, Exception):
                logger.warning(
                    "batch_feature_fetch_failed",
                    extra={"entity_id": str(entity_id), "error": str(vector)},
                )
                results[entity_id] = {}
                continue

            results[entity_id] = dict(vector.features)

        return results

    async def update_session_signal(self, user_id: str, signals: dict[str, float]) -> None:
        """Update T1 short-term signals."""
        if not signals:
            return

        key = self._session_key(user_id)
        sanitized = self._sanitizer.sanitize(signals)

        await self._redis.hset(key, mapping={k: str(v) for k, v in sanitized.items()})
        await self._redis.expire(key, self._session_ttl_seconds)

    async def update_habit_signal(self, user_id: str, signals: dict[str, float]) -> None:
        """Update T2 mid-term habit signals."""
        if not signals:
            return

        key = self._habit_key(user_id)
        sanitized = self._sanitizer.sanitize(signals)

        await self._redis.hset(key, mapping={k: str(v) for k, v in sanitized.items()})
        await self._redis.expire(key, self._habit_ttl_seconds)

    async def record_interaction_outcome(self, user_id: str, tool_id: str, success: bool) -> None:
        """Update rolling success-rate signals after an interaction."""
        habit_key = self._habit_key(user_id)
        feature_name = f"success_rate:{tool_id}"

        current_raw = await self._redis.hget(habit_key, feature_name)
        current_rate = self._coerce_float(current_raw, default=0.7)

        alpha = 0.2
        observed = 1.0 if success else 0.0
        new_rate = (alpha * observed) + ((1.0 - alpha) * current_rate)
        new_rate = max(0.0, min(1.0, new_rate))

        await self._redis.hset(habit_key, mapping={feature_name: f"{new_rate:.4f}"})
        await self._redis.expire(habit_key, self._habit_ttl_seconds)

        legacy_habit_key = f"rio:signals:t2:{user_id}"
        if legacy_habit_key != habit_key:
            await self._redis.hset(
                legacy_habit_key,
                mapping={feature_name: f"{new_rate:.4f}"},
            )
            await self._redis.expire(legacy_habit_key, self._habit_ttl_seconds)

    async def record_affinity_signal(
        self,
        user_id: str,
        affinity_name: str,
        value: float,
        *,
        tier: str = "t2",
    ) -> None:
        """Record an affinity-style signal in T1 or T2."""
        normalized_name = affinity_name.strip()
        if not normalized_name:
            return

        clamped_value = max(0.0, min(1.0, float(value)))
        key = self._session_key(user_id) if tier == "t1" else self._habit_key(user_id)
        ttl = self._session_ttl_seconds if tier == "t1" else self._habit_ttl_seconds

        await self._redis.hset(key, mapping={normalized_name: f"{clamped_value:.4f}"})
        await self._redis.expire(key, ttl)

    async def _get_tier3_signals(self, user_id: str) -> dict[str, float]:
        """Fetch long-term signals from the graph layer."""
        if self._graph is None:
            return {}

        try:
            entities = await self._graph.get_graph_context(
                account_id=uuid.UUID(user_id),
                entity_names=["Persona", "Preferences"],
                depth=1,
            )

            signals: dict[str, float] = {}
            for entry in entities:
                summary = str(entry.get("summary", "")).lower()

                if "concise" in summary:
                    signals["affinity:concise"] = 0.9
                if "technical" in summary:
                    signals["affinity:technical"] = 0.85
                if "research" in summary:
                    signals["affinity:research"] = 0.8
                if "fast" in summary:
                    signals["affinity:speed"] = 0.75

            return signals

        except Exception as exc:
            logger.warning(
                "tier3_fetch_failed",
                extra={"user_id": user_id, "error": str(exc)},
            )
            return {}

    def _normalize_redis_hash(self, raw: Any) -> dict[str, float]:
        """Normalize Redis hash output across decode_responses modes."""
        if not isinstance(raw, dict):
            return {}

        normalized: dict[str, float] = {}
        for key, value in raw.items():
            decoded_key = self._decode_redis_scalar(key)
            decoded_value = self._decode_redis_scalar(value)

            if decoded_key is None or decoded_value is None:
                continue

            try:
                normalized[decoded_key] = float(decoded_value)
            except (TypeError, ValueError):
                continue

        return normalized

    def _decode_redis_scalar(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except UnicodeDecodeError:
                return None
        if isinstance(value, str):
            return value
        return str(value)

    def _session_key(self, entity_id: str) -> str:
        return f"{self._prefix}t1:{entity_id}"

    def _habit_key(self, entity_id: str) -> str:
        return f"{self._prefix}t2:{entity_id}"

    def _default_feature_names(self) -> list[str]:
        return [
            "user_affinity",
            "agent_success_rate",
            "agent_trust_score",
            "recency_bias",
            "search_preference",
            "affinity:concise",
            "affinity:technical",
            "affinity:research",
            "affinity:speed",
        ]

    def _get_signal_fallback(self, signal_name: str) -> float:
        fallbacks = {
            "user_affinity": 0.5,
            "agent_success_rate": 0.7,
            "agent_trust_score": 0.7,
            "recency_bias": 1.0,
            "search_preference": 0.5,
            "affinity:concise": 0.0,
            "affinity:technical": 0.0,
            "affinity:research": 0.0,
            "affinity:speed": 0.0,
        }
        return fallbacks.get(signal_name, 0.0)

    def _coerce_float(self, value: Any, default: float = 0.0) -> float:
        decoded = self._decode_redis_scalar(value)
        if decoded is None:
            return default
        try:
            return float(decoded)
        except (TypeError, ValueError):
            return default
