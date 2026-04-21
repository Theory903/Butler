import asyncio
import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from services.ml.features import FeatureService, SignalScrubber
from services.ml.personalization_engine import (
    PersonalizationEngine, 
    PersonalizationConfig, 
    Candidate
)
from services.memory.retrieval import RetrievalFusionEngine
import fakeredis.aioredis

@pytest.fixture
async def redis():
    return fakeredis.aioredis.FakeRedis()

@pytest.fixture
def graph_repo():
    repo = MagicMock()
    repo.get_graph_context = AsyncMock(return_value={"interests": ["concise", "tech"], "loyalty": 0.9})
    return repo

@pytest.fixture
def feature_service(redis, graph_repo):
    return FeatureService(redis, graph_repo=graph_repo)

@pytest.fixture
def personalization_engine(feature_service):
    config = PersonalizationConfig(
        candidate_limit=10,
        light_ranker_cutoff=5,
        heavy_ranker_cutoff=2
    )
    vs = MagicMock()
    gs = MagicMock()
    return PersonalizationEngine(config, vs, gs, feature_service)

class TestFlight3Personalization:
    
    @pytest.mark.asyncio
    async def test_3_tier_signal_recording(self, feature_service, redis):
        user_id = str(uuid4())
        tool_id = "weather_tool"
        
        await feature_service.record_interaction_outcome(user_id, tool_id, success=True)
        
        val = await redis.hget(f"rio:signals:t2:{user_id}", f"success_rate:{tool_id}")
        assert val is not None
        assert float(val) == 0.76

    @pytest.mark.asyncio
    async def test_privacy_scrubbing_jitter(self, feature_service):
        scrubber = SignalScrubber()
        features = {"user_affinity": 0.8}
        
        scrubbed = scrubber.scrub_features(features)
        assert 0.75 <= scrubbed["user_affinity"] <= 0.85

    @pytest.mark.asyncio
    async def test_hybrid_ranking_logic(self, personalization_engine):
        user_id = str(uuid4())
        context = {"user_id": user_id, "intent": "utility"}
        
        c1_id = uuid4()
        c2_id = uuid4()
        candidates = [
            Candidate(id=c1_id, type="tool", score=0.5, features={"concise": 1.0}),
            Candidate(id=c2_id, type="memory", score=0.9, features={})
        ]
        
        # Mock FeatureService.get_features (called by FeatureHydrator)
        # It should return Dict[UUID, Dict[str, Any]]
        personalization_engine.feature_hydrator.feature_store.get_features = AsyncMock(return_value={
            c1_id: {"agent_success_rate": 0.9, "user_affinity": 0.5},
            c2_id: {"agent_success_rate": 0.7, "user_affinity": 0.5}
        })
        
        # Mock FeatureService.get_online_features (called by LightRanker)
        # It should return FeatureVector
        from domain.ml.contracts import FeatureVector
        personalization_engine.light_ranker.features.get_online_features = AsyncMock(return_value=FeatureVector(
            features={"agent_success_rate": 0.9, "user_affinity": 0.5},
            timestamp=0.0,
            version="1.0"
        ))
        
        ranked = await personalization_engine.rank(
            query_vector=np.zeros(128),
            context=context,
            candidates=candidates
        )
        
        assert len(ranked) > 0
        assert any(r.type == "tool" for r in ranked)

    @pytest.mark.asyncio
    async def test_retrieval_fusion_integration(self, personalization_engine):
        from services.memory.retrieval import ScoredMemory
        
        db = AsyncMock()
        embedder = AsyncMock()
        embedder.embed = AsyncMock(return_value=np.zeros(128).tolist())
        
        repo = MagicMock()
        
        engine = RetrievalFusionEngine(db, embedder, repo, personalization=personalization_engine)
        
        class MockMem:
            def __init__(self, id):
                self.id = id
                self.created_at = None
                self.content = "test content"
                self.metadata = {}
        
        m1 = MockMem(uuid4())
        m2 = MockMem(uuid4())
        
        account_id = str(uuid4())
        
        with patch.object(engine, "_get_candidates", new=AsyncMock(return_value=[m1, m2])):
            # Mock the hydrator call inside PersonalizationEngine which is now called in fusion search
            personalization_engine.feature_hydrator.feature_store.get_features = AsyncMock(return_value={})
            personalization_engine.light_ranker.features.get_online_features = AsyncMock(return_value=MagicMock(features={}))
            
            results = await engine.search(account_id, "hello", limit=2)
            
            assert len(results) == 2
            assert isinstance(results[0], ScoredMemory)
            assert results[0].score > 0.0
