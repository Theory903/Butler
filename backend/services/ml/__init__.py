from .intent import IntentClassifier
from .embeddings import EmbeddingService
from .registry import ModelRegistry
from .runtime import MLRuntimeManager
from .mixer import CandidateMixer, SignalManager
from .admin import MLAdmin, HealthProbe
from .ranking import LightRanker, HeavyRanker

class MLService:
    """Butler Intelligence Platform (v3.0 RIO) Facade.
    
    Orchestrates Retrieval, Inference, and Orchestration signals.
    """
    def __init__(
        self, 
        classifier: IntentClassifier, 
        embedder: EmbeddingService, 
        registry: ModelRegistry, 
        runtime: MLRuntimeManager,
        ranking: LightRanker | HeavyRanker = None,
        features=None,
        mixer: CandidateMixer = None,
        signals: SignalManager = None,
        admin: MLAdmin = None
    ):
        self._classifier = classifier
        self._embedder = embedder
        self._registry = registry
        self._runtime = runtime
        self._ranking = ranking
        self._features = features
        self._mixer = mixer
        self._signals = signals
        self._admin = admin
        
        if self._classifier:
            self._classifier._runtime = self._runtime

    async def classify_intent(self, text: str):
        return await self._classifier.classify(text)

    async def embed(self, text: str):
        return await self._embedder.embed(text)

    async def mix_and_rank(self, query: str, entity_id: str, limit: int = 10):
        """Unified Twitter-style pipeline: Mix -> Enrich -> Rank."""
        if not self._mixer:
            return []
            
        # 1. Candidate Retrieval Mixer
        candidates = await self._mixer.mix(query, limit * 5)
        
        # 2. enrichment (Signals)
        if self._signals:
            candidates = await self._signals.enrich_candidates(entity_id, candidates)
            
        # 3. Heavy Ranking
        if self._ranking:
            return await self._ranking.rerank(query, candidates, user_id=entity_id)
            
        return candidates[:limit]

    async def rerank(self, query: str, candidates: list, user_id: str = None):
        if not self._ranking:
            return [{"index": i, "score": 0.0} for i, c in enumerate(candidates)]
        return await self._ranking.rerank(query, candidates, user_id=user_id)

    async def get_features(self, entity_id: str, feature_names: list):
        if not self._features:
            return None
        return await self._features.get_online_features(entity_id, feature_names)

    def get_admin_stats(self):
        return self._admin.get_stats() if self._admin else {}

    def set_admin_flag(self, name, value):
        if self._admin:
            self._admin.set_flag(name, value)

    def list_models(self):
        return self._registry.list_models()

__all__ = [
    "IntentClassifier",
    "EmbeddingService",
    "ModelRegistry",
    "MLRuntimeManager",
    "MLService",
    "CandidateMixer",
    "SignalManager",
    "MLAdmin",
    "LightRanker",
    "HeavyRanker"
]
