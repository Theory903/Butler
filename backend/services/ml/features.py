import time
import logging
from typing import List, Dict
from domain.ml.contracts import FeatureStoreContract, FeatureVector

logger = logging.getLogger(__name__)

class FeatureService(FeatureStoreContract):
    """Production Feature Store drawing from Twitter's User Signal Service.
    
    Manages:
    - Trajectory Signals: Historical agent interaction patterns.
    - Interest Vectors: Periodic user embedding signals.
    - Real-time Context: In-session transient features.
    """
    
    def __init__(self, redis):
        self._redis = redis
        self._prefix = "rio:signals:"

    async def get_online_features(self, entity_id: str, feature_names: List[str]) -> FeatureVector:
        """Fetch rich ML signals for an entity (user/device)."""
        key = f"{self._prefix}{entity_id}"
        
        try:
            raw_features = await self._redis.hgetall(key)
            
            features = {}
            for name in feature_names:
                val = raw_features.get(name.encode())
                if val:
                    features[name] = float(val)
                else:
                    # Signal Fallback Ladder
                    features[name] = self._get_signal_fallback(name)
                    
            return FeatureVector(
                features=features,
                timestamp=time.time(),
                version="v3.0-rio"
            )
        except Exception as exc:
            logger.error(f"signal_fetch_failed: {str(exc)}", entity_id=entity_id)
            return FeatureVector(features={}, timestamp=time.time(), version="error")

    async def update_trajectory_signal(self, user_id: str, success_rate: float):
        """Update the trust/success signal for a user based on agent history."""
        key = f"{self._prefix}{user_id}"
        await self._redis.hset(key, "agent_success_rate", success_rate)

    async def batch_update_interest_vectors(self, signals: Dict[str, Dict[str, float]]):
        """Perform a batch update of pre-computed user interest vectors."""
        for eid, features in signals.items():
            key = f"{self._prefix}{eid}"
            await self._redis.hset(key, mapping=features)

    def _get_signal_fallback(self, signal_name: str) -> float:
        """Standard fallbacks for missing signals to ensure ranking stability."""
        fallbacks = {
            "user_affinity": 0.5,
            "agent_success_rate": 0.7,
            "recency_bias": 1.0
        }
        return fallbacks.get(signal_name, 0.0)
