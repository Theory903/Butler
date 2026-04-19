from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import structlog
from domain.ml.contracts import RankingContract, RerankResult
from services.ml.features import FeatureService
from services.ml.registry import ModelRegistry

logger = structlog.get_logger(__name__)

class LightRanker(RankingContract):
    """
    T2/T3 Candidate Ranker for the Butler Blender.
    
    Implements behavioral-aware ranking:
    1. Relevance (from retrieval scores)
    2. Recency (penalize old memories)
    3. User Signal weight (boost items user interacted with recently)
    """

    def __init__(self, registry: Optional[ModelRegistry] = None, feature_service: Optional[FeatureService] = None):
        self._registry = registry or ModelRegistry()
        self._features = feature_service

    async def rerank(self, query: str, candidates: List[Any], user_id: Optional[str] = None) -> List[RerankResult]:
        """
        Rank candidates based on query relevance and metadata.
        Expected candidates: List[BlenderCandidate] (or compatible objects).
        """
        results = []
        start_time = time.monotonic()
        
        # 1. Fetch user interest vectors if user_id is provided
        user_signals = {}
        if self._features and user_id:
            vector = await self._features.get_online_features(user_id, ["user_affinity", "agent_success_rate"])
            user_signals = vector.features
            logger.debug("ranking_signals_fetched", user_id=user_id, signals=user_signals)
        
        for idx, candidate in enumerate(candidates):
            # Base score from the retriever
            score = getattr(candidate, "score", 0.5)
            
            # Recency boost (if timestamp exists in metadata)
            metadata = getattr(candidate, "metadata", {})
            ts = metadata.get("ts")
            if ts:
                # Basic recency decay (placeholder: 10% boost for fresh items)
                score *= 1.1 
            
            # Behavioral boost: Affinity Signal
            affinity = user_signals.get("user_affinity", 0.5)
            if affinity > 0.8:
                score *= 1.15
                
            # Behavioral boost: Success Signal (Trust)
            trust = user_signals.get("agent_success_rate", 0.7)
            if trust < 0.4:
                # Penalize uncertain candidates if session trust is low
                score *= 0.9
                
            # Manual boost override
            if metadata.get("affinity") == "high":
                score *= 1.2
                
            results.append(RerankResult(
                index=idx,
                score=min(score, 1.0),
                metadata=metadata
            ))
            
        # Select top-K
        sorted_results = sorted(results, key=lambda x: x.score, reverse=True)
        
        latency = (time.monotonic() - start_time) * 1000
        logger.debug("ranking_completed", count=len(candidates), duration_ms=latency)
        
        return sorted_results

    def select_tier(self, intent_label: str, confidence: float) -> int:
        """Heuristic to select optimal ML tier for the request."""
        # TODO: Move this to a dedicated Router service in Phase 3
        if intent_label in ["clarification", "casual"]:
            return 2  # Local Qwen3 (T2)
        if confidence > 0.9 and intent_label in ["instruction"]:
            return 2  # Local is enough
        return 3 # Cloud Frontier (T3)

class HeavyRanker(RankingContract):
    """
    T3 Deep Ranker for Butler v3.0 (Oracle-Grade).
    
    Implements a multi-objective scoring architecture inspired by 'the-algorithm':
    1. Semantic Relevance (Vector)
    2. Behavioral Affinity (Signal Store)
    3. Trust & Success Rate (Signal Store)
    4. Graph Distance (Knowledge Base)
    5. Recency Decay (Linear/Poly)
    """

    def __init__(self, registry: Optional[ModelRegistry] = None, feature_service: Optional[FeatureService] = None):
        self._registry = registry or ModelRegistry()
        self._features = feature_service
        logger.info("heavy_ranker_initialized")

    async def rerank(self, query: str, candidates: List[Any], user_id: Optional[str] = None) -> List[RerankResult]:
        """
        Execute deep ranking over candidates.
        """
        if not candidates:
            return []

        start_time = time.monotonic()
        results = []

        # 1. Enrichment: Fetch Unified User Action (UUA) features
        user_signals = {}
        if self._features and user_id:
            try:
                vector = await self._features.get_online_features(
                    user_id, 
                    ["user_affinity", "agent_trust_score", "recency_bias", "interaction_depth"]
                )
                user_signals = vector.features
            except Exception as e:
                logger.warning("ranking_feature_fetch_failed", error=str(e))

        # 2. Deep Scoring Loop
        for idx, candidate in enumerate(candidates):
            # A. Base Semantic Score (from retrieval)
            score = float(getattr(candidate, "score", 0.5))
            
            # B. Metadata extraction
            metadata = getattr(candidate, "metadata", {})
            
            # C. Behavioral Signals (Multiplier)
            affinity = user_signals.get("user_affinity", 0.5)
            trust = user_signals.get("agent_trust_score", 0.7)
            
            # Weighted Behavioral Boost
            # Success signal is more important for utility tools; affinity for casual chat.
            behavioral_boost = (affinity * 0.4) + (trust * 0.6)
            score *= (1.0 + (behavioral_boost * 0.25)) # Max 25% boost from behavior

            # D. Recency Decay
            ts = metadata.get("timestamp") or metadata.get("ts")
            if ts:
                age_hours = (time.time() - float(ts)) / 3600
                # Poly decay: score / (1 + age_hours^0.5)
                decay = 1.0 / (1.0 + (max(0, age_hours) ** 0.5) * 0.05)
                score *= decay

            # E. Diversity Bias (penalty for consecutive identical sources)
            source = metadata.get("source", "unknown")
            # Logic for diversity would usually look at previous results, 
            # here we just apply a multiplier if it's from a "noisy" source
            if source == "ambient":
                score *= 0.95

            results.append(RerankResult(
                index=idx,
                score=min(max(score, 0.0), 1.0),
                metadata=metadata
            ))

        # 3. Final Sort
        sorted_results = sorted(results, key=lambda x: x.score, reverse=True)
        
        latency = (time.monotonic() - start_time) * 1000
        logger.info("heavy_ranking_completed",
                    query_len=len(query),
                    candidates=len(candidates),
                    latency_ms=latency)

        return sorted_results
