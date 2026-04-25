import asyncio
import uuid
from typing import Any

import structlog
from pydantic import BaseModel


# Mocking enough for a standalone test
class BlenderCandidate(BaseModel):
    source: str
    content: str
    score: float = 0.0
    metadata: dict[str, Any] = {}


class BlenderSignal(BaseModel):
    user_id: str
    session_id: str
    query: str
    context: dict[str, Any] = {}


# We need to import the actual classes but mock their deps
from services.ml.features import FeatureService
from services.ml.ranking import LightRanker
from services.orchestrator.blender import ButlerBlender


async def test_blender_federation():

    # 1. Setup Mocks
    class MockMemory:
        async def recall(self, uid, q, limit=10):
            return [
                type(
                    "Memory",
                    (),
                    {
                        "id": uuid.uuid4(),
                        "content": "User lives in SF.",
                        "relevance_score": 0.9,
                        "created_at": None,
                    },
                )
            ]

    class MockTools:
        async def list_tools(self, category=None):
            return [
                type(
                    "Tool",
                    (),
                    {"name": "get_weather", "description": "Fetch weather for a location"},
                )
            ]

    class MockRedis:
        async def hgetall(self, key):
            return {b"user_affinity": b"0.9", b"agent_success_rate": b"0.8"}

    redis = MockRedis()
    features = FeatureService(redis)
    ranker = LightRanker(feature_service=features)

    blender = ButlerBlender(
        memory_service=MockMemory(), tools_service=MockTools(), ranking_provider=ranker
    )

    # 2. Execute Blend
    signal = BlenderSignal(
        user_id="test_user_123", session_id="session_abc", query="What's the weather like at home?"
    )

    candidates = await blender.blend(signal)

    # 3. Validation
    for _c in candidates:
        pass

    assert len(candidates) >= 2, "Blender should have fetched from both memory and tools"
    assert any(c.source == "memory" for c in candidates), "Memory candidate missing"
    assert any(c.source == "tools" for c in candidates), "Tool candidate missing"

    # Check ranking boost (user_affinity was 0.9, so memory should be boosted)
    memory_cand = next(c for c in candidates if c.source == "memory")
    assert memory_cand.score > 0.9, "Memory candidate should have received behavioral boost"


if __name__ == "__main__":
    # Setup structlog for output
    structlog.configure()
    asyncio.run(test_blender_federation())
