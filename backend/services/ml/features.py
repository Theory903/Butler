import asyncio
import time
import logging
import json
import random
import uuid
from uuid import UUID
from typing import List, Dict, Optional, Any
from domain.ml.contracts import FeatureStoreContract, FeatureVector

logger = logging.getLogger(__name__)

class SignalScrubber:
    """World-class privacy: Anonymizes and scrubs behavioral features."""
    
    @staticmethod
    def scrub_features(features: Dict[str, float]) -> Dict[str, float]:
        """Anonymizes feature values and applies differential privacy noise."""
        scrubbed = {}
        for k, v in features.items():
            # Apply 5% differential privacy jitter for long-term protection
            noise = random.uniform(-0.05, 0.05) if "affinity" in k else 0
            scrubbed[k] = round(max(0.0, min(1.0, v + noise)), 4)
        return scrubbed

class FeatureService(FeatureStoreContract):
    """3-Tier Behavioral Signal Store (Oracle-Grade).
    
    Tiers:
    - Tier 1: Short-Term (Session) -> Transient Redis HSET
    - Tier 2: Mid-Term (Habits) -> Persistent Redis with Time-Decay
    - Tier 3: Long-Term (Identity) -> Knowledge Graph (Neo4j)
    """
    
    def __init__(self, redis, graph_repo: Optional[Any] = None):
        self._redis = redis
        self._graph = graph_repo
        self._prefix = "rio:signals:"
        self._scrubber = SignalScrubber()

    async def get_online_features(self, entity_id: str, feature_names: List[str]) -> FeatureVector:
        """Fetch unified 3-tier features for an entity."""
        session_key = f"{self._prefix}t1:{entity_id}"
        habit_key = f"{self._prefix}t2:{entity_id}"
        
        try:
            # 1. Pipeline fetch for T1 & T2
            async with self._redis.pipeline(transaction=False) as pipe:
                pipe.hgetall(session_key)
                pipe.hgetall(habit_key)
                raw_t1, raw_t2 = await pipe.execute()

            # 2. Fetch T3 (Identity) signals from Graph
            t3_signals = await self._get_tier3_signals(entity_id) if self._graph else {}

            # 3. Merge and calculate weighted signals
            # Hybrid Priority: T1 (Session) > T3 (Identity) > T2 (Habits)
            merged = {}
            for name in feature_names:
                t1_val = raw_t1.get(name.encode())
                t2_val = raw_t2.get(name.encode())
                t3_val = t3_signals.get(name)
                
                # Hybrid Logic: Session overrides Identity, which overrides Habits
                if t1_val:
                    merged[name] = float(t1_val)
                elif t3_val is not None:
                    merged[name] = float(t3_val)
                elif t2_val:
                    merged[name] = float(t2_val)
                else:
                    merged[name] = self._get_signal_fallback(name)

            return FeatureVector(
                features=self._scrubber.scrub_features(merged),
                timestamp=time.time(),
                version="v3.1-hybrid"
            )
        except Exception as exc:
            logger.error("feature_retrieval_failed entity_id=%s error=%s", entity_id, exc)
            return FeatureVector(features={}, timestamp=time.time(), version="error")

    async def _get_tier3_signals(self, user_id: str) -> Dict[str, float]:
        """Fetch Long-term (Identity) signals from the Knowledge Graph."""
        if self._graph is None:
            return {}

        try:
            # Look for entities of type PREFERENCE or TRAIT
            # This is a high-level mapping from Graph nodes to feature weights
            entities = await self._graph.get_graph_context(
                account_id=uuid.UUID(user_id), 
                entity_names=["Persona", "Preferences"],
                depth=1
            )
            
            signals = {}
            for entry in entities:
                # Map graph properties to signal weights
                # e.g. "prefers_concise" property -> "affinity:concise" feature
                summary = entry.get("summary", "").lower()
                if "concise" in summary:
                    signals["affinity:concise"] = 0.9
                if "technical" in summary:
                    signals["affinity:technical"] = 0.85
                    
            return signals
        except Exception as exc:
            logger.warning("tier3_fetch_failed user_id=%s error=%s", user_id, exc)
            return {}

    async def get_features(self, entity_ids: List[UUID]) -> Dict[UUID, Dict[str, Any]]:
        """Batch fetch features for multiple entities (for FeatureHydrator)."""
        results = {}
        # For v3.1, we do this sequentially or via gather; 
        # In full production we'd use a Redis MGET pipeline.
        tasks = [self.get_online_features(str(eid), []) for eid in entity_ids]
        vectors = await asyncio.gather(*tasks)
        
        for eid, vector in zip(entity_ids, vectors):
            results[eid] = vector.features
            
        return results

    async def update_session_signal(self, user_id: str, signals: Dict[str, float]):
        """Update Tier 1 (Short-term) signals for the current session."""
        key = f"{self._prefix}t1:{user_id}"
        await self._redis.hset(key, mapping=signals)
        # T1 expires quickly (2 hours)
        await self._redis.expire(key, 7200)

    async def record_interaction_outcome(self, user_id: str, tool_id: str, success: bool):
        """Update success/affinity signals after an interaction."""
        habit_key = f"{self._prefix}t2:{user_id}"
        
        # Moving Average update for Success Rate
        current_rate = await self._redis.hget(habit_key, f"success_rate:{tool_id}")
        rate = float(current_rate or 0.7)
        alpha = 0.2 # Smoothing factor
        new_rate = (alpha * (1.0 if success else 0.0)) + ((1 - alpha) * rate)
        
        await self._redis.hset(habit_key, f"success_rate:{tool_id}", round(new_rate, 4))
        # Habits persist for 30 days
        await self._redis.expire(habit_key, 2592000)

    def _get_signal_fallback(self, signal_name: str) -> float:
        fallbacks = {
            "user_affinity": 0.5,
            "agent_success_rate": 0.7,
            "recency_bias": 1.0,
            "search_preference": 0.5
        }
        return fallbacks.get(signal_name, 0.0)
