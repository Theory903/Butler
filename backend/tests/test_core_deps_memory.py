from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from core import deps


class _Dummy:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class _CapturingMemoryStore:
    last_kwargs = None

    def __init__(self, *, db, redis, embedder, cold_store, graph_repo=None, **kwargs):
        type(self).last_kwargs = {
            "db": db,
            "redis": redis,
            "embedder": embedder,
            "cold_store": cold_store,
            "graph_repo": graph_repo,
            **kwargs,
        }


@pytest.mark.asyncio
async def test_get_memory_service_passes_embedder_to_memory_store(monkeypatch):
    embedder = object()
    runtime = object()
    cold_store = object()
    db = cast(AsyncSession, AsyncMock(spec=AsyncSession))
    redis = cast(Redis, MagicMock(spec=Redis))

    monkeypatch.setattr(deps, "get_ml_runtime", lambda: runtime)
    monkeypatch.setattr(deps.settings, "EMBEDDING_MODEL", "test-model")
    monkeypatch.setattr(deps.settings, "KNOWLEDGE_STORE_BACKEND", "postgres")
    monkeypatch.setattr(deps.settings, "TURBOQUANT_INDEX_PATH", None)
    monkeypatch.setattr(deps.settings, "LONG_CONTEXT_TOKEN_THRESHOLD", 1024)

    monkeypatch.setattr("services.ml.embeddings.EmbeddingService", lambda model: embedder)
    monkeypatch.setattr("services.memory.anchored_summarizer.AnchoredSummarizer", _Dummy)
    monkeypatch.setattr("services.memory.consent_manager.ConsentManager", _Dummy)
    monkeypatch.setattr("services.memory.context_builder.ContextBuilder", _Dummy)
    monkeypatch.setattr("services.memory.episodic_engine.EpisodicMemoryEngine", _Dummy)
    monkeypatch.setattr("services.memory.evolution_engine.MemoryEvolutionEngine", _Dummy)
    monkeypatch.setattr("services.memory.graph_extraction.KnowledgeExtractionEngine", _Dummy)
    monkeypatch.setattr("services.memory.memory_store.ButlerMemoryStore", _CapturingMemoryStore)
    monkeypatch.setattr("services.memory.neo4j_knowledge_repo.Neo4jKnowledgeRepo", _Dummy)
    monkeypatch.setattr("services.memory.postgres_knowledge_repo.PostgresKnowledgeRepo", _Dummy)
    monkeypatch.setattr("services.memory.resolution_engine.EntityResolutionEngine", _Dummy)
    monkeypatch.setattr("services.memory.retrieval.RetrievalFusionEngine", _Dummy)
    monkeypatch.setattr("services.memory.service.MemoryService", _Dummy)
    monkeypatch.setattr(
        "services.memory.turboquant_store.get_cold_store", lambda snapshot_path=None: cold_store
    )
    monkeypatch.setattr("services.memory.understanding_service.UnderstandingService", _Dummy)

    await deps.get_memory_service(db=db, redis=redis)

    assert _CapturingMemoryStore.last_kwargs is not None
    assert _CapturingMemoryStore.last_kwargs["embedder"] is embedder
    assert _CapturingMemoryStore.last_kwargs["db"] is db
    assert _CapturingMemoryStore.last_kwargs["redis"] is redis
    assert _CapturingMemoryStore.last_kwargs["cold_store"] is cold_store
