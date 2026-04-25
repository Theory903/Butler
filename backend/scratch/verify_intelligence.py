import asyncio
from unittest.mock import AsyncMock, MagicMock

import structlog

from services.ml import MLService
from services.ml.mixer import CandidateMixer, SignalManager
from services.ml.ranking import HeavyRanker

# Setup logging
structlog.configure(processors=[structlog.processors.JSONRenderer()])
log = structlog.get_logger()


async def verify_intelligence_pipeline():
    log.info("starting_intelligence_verification")

    # 1. Mock Dependencies
    mock_memory = MagicMock()
    mock_knowledge = MagicMock()
    mock_ambient = MagicMock()
    mock_features = AsyncMock()

    # Mock Features: Unified User Action (UUA) signal vector
    mock_feature_vector = MagicMock()
    mock_feature_vector.features = {
        "user_affinity": 0.85,
        "agent_trust_score": 0.9,
        "recency_bias": 1.2,
        "interaction_depth": 3.0,
    }
    # Fix: return_value for AsyncMock
    mock_features.get_online_features.return_value = mock_feature_vector

    # 2. Initialize Components
    mixer = CandidateMixer(
        memory_svc=mock_memory, knowledge_svc=mock_knowledge, ambient_svc=mock_ambient
    )
    signals = SignalManager(feature_svc=mock_features)
    ranker = HeavyRanker(feature_service=mock_features)

    ml_svc = MLService(
        classifier=MagicMock(),
        embedder=MagicMock(),
        registry=MagicMock(),
        runtime=MagicMock(),
        ranking=ranker,
        mixer=mixer,
        signals=signals,
        features=mock_features,
    )

    log.info("components_initialized")

    # 3. Test Full Pipeline: Mix -> Enrich -> Rank
    query = "How do I optimize my garden?"
    user_id = "user_123_high_affinity"

    log.info("executing_mix_and_rank", query=query, user_id=user_id)

    results = await ml_svc.mix_and_rank(query, user_id, limit=5)

    log.info("pipeline_completed", result_count=len(results))

    for i, res in enumerate(results):
        log.info(
            f"rank_{i + 1}",
            score=f"{res.score:.4f}",
            source=res.metadata.get("source"),
            id=res.metadata.get("id"),
        )

    # 4. Assertions (Basic)
    assert len(results) > 0, "Should return candidates"
    assert results[0].score >= results[-1].score, "Should be sorted by score"
    assert "signals" in results[0].metadata, "Should contain enriched signals"

    log.info("verification_successful")


if __name__ == "__main__":
    asyncio.run(verify_intelligence_pipeline())
