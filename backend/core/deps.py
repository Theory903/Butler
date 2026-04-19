from __future__ import annotations

import functools
import logging
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from domain.orchestrator.runtime_kernel import RuntimeKernel
from infrastructure.cache import get_redis
from infrastructure.config import settings
from infrastructure.database import get_session
from services.ml.ranking import LightRanker
from services.ml.registry import ModelRegistry

# Service Imports (concrete wiring lives HERE, not in service files)
from services.ml.runtime import MLRuntimeManager
from services.orchestrator.blender import ButlerBlender
from services.orchestrator.executor import DurableExecutor
from services.orchestrator.intake import IntakeProcessor
from services.orchestrator.planner import PlanEngine
from services.orchestrator.service import OrchestratorService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Infrastructure dependencies
# ---------------------------------------------------------------------------

async def get_db(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[AsyncSession, None]:
    """Inject async SQLAlchemy session."""
    yield session

async def get_cache() -> Redis:
    """Inject Redis client."""
    return await get_redis()

# ---------------------------------------------------------------------------
# ML & Intelligence Dependencies
# ---------------------------------------------------------------------------

@functools.lru_cache
def get_ml_runtime() -> MLRuntimeManager:
    """Singleton ML Runtime Manager (implements IReasoningRuntime)."""
    registry = ModelRegistry()
    return MLRuntimeManager(registry)

async def get_smart_router(redis: Redis = Depends(get_cache)) -> Any:
    """Inject Tier-based Smart Router."""
    from services.ml.smart_router import ButlerSmartRouter
    runtime = get_ml_runtime()
    return ButlerSmartRouter(runtime=runtime, tri_attention_enabled=settings.TRIATTENTION_ENABLED)


@functools.lru_cache
def get_feature_service(redis: Redis) -> Any:
    """Feature Store for user signals."""
    from services.ml.features import FeatureService
    return FeatureService(redis)

async def get_ranker(redis: Redis = Depends(get_cache)) -> LightRanker:
    """Heuristic Ranker with behavioral signal integration."""
    features = get_feature_service(redis)
    return LightRanker(feature_service=features)

async def get_blender(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_cache)
) -> ButlerBlender:
    """Federated Intelligence Blender (Cr-Mixer)."""
    memory = await get_memory_service(db, redis)
    tools = await get_tools_service(db, redis)
    ranker = await get_ranker(redis)

    return ButlerBlender(
        memory_service=memory,
        tools_service=tools,
        ranking_provider=ranker
    )

# ---------------------------------------------------------------------------
# Security & Safety Dependencies
# ---------------------------------------------------------------------------

@functools.lru_cache
def get_redaction_service() -> Any:
    """Concrete RedactionService (implements IRedactionService)."""
    from services.security.redaction import RedactionService
    return RedactionService()

@functools.lru_cache
def get_content_guard() -> Any:
    """Concrete ContentGuard (implements IContentGuard)."""
    from services.security.safety import ContentGuard
    return ContentGuard()

@functools.lru_cache
def get_jwks_manager() -> Any:
    """Singleton JWKSManager (implements IJWKSVerifier)."""
    from services.auth.jwt import JWKSManager
    return JWKSManager()

async def get_auth_middleware(redis: Redis = Depends(get_cache)) -> Any:
    """Wired JWTAuthMiddleware with IJWKSVerifier."""
    from services.gateway.auth_middleware import JWTAuthMiddleware
    return JWTAuthMiddleware(jwks=get_jwks_manager(), redis=redis)

# ---------------------------------------------------------------------------
# Memory & Search Dependencies
# ---------------------------------------------------------------------------

async def get_memory_service(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_cache)
) -> Any:
    from services.memory.anchored_summarizer import AnchoredSummarizer
    from services.memory.context_builder import ContextBuilder
    from services.memory.episodic_engine import EpisodicMemoryEngine
    from services.memory.evolution_engine import MemoryEvolutionEngine
    from services.memory.graph_extraction import KnowledgeExtractionEngine
    from services.memory.memory_store import ButlerMemoryStore
    from services.memory.neo4j_knowledge_repo import Neo4jKnowledgeRepo
    from services.memory.postgres_knowledge_repo import PostgresKnowledgeRepo
    from services.memory.resolution_engine import EntityResolutionEngine
    from services.memory.retrieval import RetrievalFusionEngine
    from services.memory.service import MemoryService
    from services.memory.turboquant_store import get_cold_store
    from services.memory.understanding_service import UnderstandingService
    from services.ml.embeddings import EmbeddingService

    embedder = EmbeddingService(settings.EMBEDDING_MODEL)
    ml_runtime = get_ml_runtime()
    summarizer = AnchoredSummarizer(ml_runtime)

    # Knowledge repo: concrete impl selected by config; both satisfy KnowledgeRepoContract
    if settings.KNOWLEDGE_STORE_BACKEND == "neo4j":
        knowledge_repo = Neo4jKnowledgeRepo()
    else:
        knowledge_repo = PostgresKnowledgeRepo(db)

    cold_store = get_cold_store(
        snapshot_path=settings.TURBOQUANT_INDEX_PATH or None
    )

    # Wire concrete cold store and graph repo into ButlerMemoryStore
    memory_store = ButlerMemoryStore(
        db=db,
        redis=redis,
        cold_store=cold_store,          # IColdStore implementation
        graph_repo=knowledge_repo,       # KnowledgeRepoContract implementation
    )

    retrieval = RetrievalFusionEngine(db, embedder, knowledge_repo)
    evolution = MemoryEvolutionEngine(db, retrieval, ml_runtime)
    resolution = EntityResolutionEngine(db, knowledge_repo, ml_runtime)
    understanding = UnderstandingService(db, ml_runtime, knowledge_repo=knowledge_repo)
    context_builder = ContextBuilder(token_budget=settings.LONG_CONTEXT_TOKEN_THRESHOLD)
    extraction = KnowledgeExtractionEngine(
        embedder=embedder,
        neo4j_repo=knowledge_repo,
        ml_runtime=ml_runtime,
    )

    # Build MemoryService first so it can be passed as IMemoryRecorder to EpisodicMemoryEngine
    svc = MemoryService(
        db=db, redis=redis, embedder=embedder, retrieval=retrieval,
        evolution=evolution, resolution=resolution,
        understanding=understanding, context_builder=context_builder,
        knowledge_repo=knowledge_repo, extraction=extraction,
        store=memory_store, summarizer=summarizer
    )

    # EpisodicMemoryEngine receives ml_runtime (IReasoningRuntime) +
    # memory_recorder (IMemoryRecorder) injected — no monkey-patch
    episodic = EpisodicMemoryEngine(
        db=db,
        ml_runtime=ml_runtime,
        memory_recorder=svc,             # MemoryService satisfies IMemoryRecorder
    )
    svc.episodic = episodic              # attach for MemoryService.capture_episode()
    return svc

async def get_search_service() -> Any:
    """SearchService wired with ML runtime."""
    from services.search.extraction import ContentExtractor
    from services.search.service import SearchService
    extractor = ContentExtractor()
    return SearchService(extractor=extractor, ml_runtime=get_ml_runtime())

async def get_answering_engine() -> Any:
    """AnsweringEngine wired with SearxNGAdapter (ISearchAdapter implementation)."""
    from services.search.adapters.searxng import SearxNGAdapter
    from services.search.answering_engine import AnsweringEngine
    adapter = SearxNGAdapter(base_url=settings.SEARXNG_URL)
    return AnsweringEngine(search_adapter=adapter, llm_runtime=get_ml_runtime())

async def get_tools_service(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_cache)
) -> Any:
    """ToolExecutor wired with ToolVerifier (IToolVerifier implementation)."""
    from services.tools.executor import ToolExecutor
    from services.tools.verification import ToolVerifier
    verifier = ToolVerifier()
    return ToolExecutor(db, redis, verifier)

# ---------------------------------------------------------------------------
# Orchestration Dependencies
# ---------------------------------------------------------------------------

async def get_orchestrator_service(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_cache),
) -> OrchestratorService:
    runtime = get_ml_runtime()

    from services.device.environment import EnvironmentService
    env_service = EnvironmentService(redis)

    intake = IntakeProcessor(runtime, environment_service=env_service)
    planner = PlanEngine()

    memory = await get_memory_service(db, redis)
    tools = await get_tools_service(db, redis)
    blender = await get_blender(db, redis)
    smart_router = await get_smart_router(redis)
    redaction = get_redaction_service()   # IRedactionService
    safety = get_content_guard()          # IContentGuard

    executor = DurableExecutor(db, redis, runtime, memory, tools)
    kernel = RuntimeKernel()

    # Resolve concrete memory store and cold store via the already-wired svc
    memory_store = getattr(memory, "_store", None)   # ButlerMemoryStore (IMemoryWriteStore)
    cold_store = getattr(memory_store, "_cold", None) if memory_store else None  # IColdStore

    return OrchestratorService(
        db=db,
        redis=redis,
        intake_proc=intake,
        planner=planner,
        executor=executor,
        kernel=kernel,
        blender=blender,
        memory_store=memory_store,        # IMemoryWriteStore
        cold_store=cold_store,            # IColdStore
        memory_service=memory,            # MemoryService for context compression
        tools_service=tools,
        answering_engine=await get_answering_engine(),  # ISearchService via AnsweringEngine
        smart_router=smart_router,
        redaction_service=redaction,      # IRedactionService
        content_guard=safety              # IContentGuard
    )


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")
