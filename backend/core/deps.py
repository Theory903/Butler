from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from core.circuit_breaker import CircuitBreakerRegistry, get_circuit_breaker_registry
from core.health_agent import ButlerHealthAgent
from core.locks import LockManager
from core.observability import get_metrics
from core.state_sync import GlobalStateSyncer
from domain.orchestrator.runtime_kernel import RuntimeKernel
from infrastructure.cache import get_redis, get_redis_sync
from infrastructure.config import BUTLER_NODE_ID, settings
from infrastructure.database import get_session
from services.cron.cron_service import ButlerCronService
from services.gateway.a2ui_bridge import A2UIBridgeService
from services.gateway.protocol_service import MercuryProtocolService
from services.gateway.rate_limiter import RateLimiter
from services.gateway.transport import HermesTransportEdge
from services.ml.ranking import LightRanker
from services.ml.registry import ModelRegistry
from services.ml.runtime import MLRuntimeManager
from services.orchestrator.blender import ButlerBlender
from services.orchestrator.executor import DurableExecutor
from services.orchestrator.intake import IntakeProcessor
from services.orchestrator.planner import PlanEngine
from services.orchestrator.service import OrchestratorService
from services.realtime.listener import RealtimePubSubListener
from services.realtime.manager import ConnectionManager
from services.realtime.presence import PresenceService
from services.realtime.ws_mux import WebSocketMultiplexer
from services.tools.mcp_bridge import MCPBridgeAdapter
from services.workflow.acp_server import ButlerACPServer

if TYPE_CHECKING:
    from services.auth.jwt import JWKSManager
    from services.gateway.auth_middleware import JWTAuthMiddleware
    from services.memory.service import MemoryService
    from services.ml.features import FeatureService
    from services.ml.personalization_engine import PersonalizationEngine
    from services.ml.smart_router import ButlerSmartRouter
    from services.search.answering_engine import AnsweringEngine
    from services.search.service import SearchService
    from services.security.redaction import RedactionService
    from services.security.safety import ContentGuard
    from services.tools.executor import ToolExecutor


logger = logging.getLogger(__name__)


class DependencyRegistry:
    """Application-lifetime dependency registry.

    This registry owns explicitly shared process-level dependencies.
    Request-scoped resources such as database sessions must never be stored here.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

        self._lock_manager: LockManager | None = None
        self._state_syncer: GlobalStateSyncer | None = None
        self._health_agent: ButlerHealthAgent | None = None
        self._ml_runtime: MLRuntimeManager | None = None
        self._jwks_manager: JWKSManager | None = None
        self._redaction_service: RedactionService | None = None
        self._content_guard: ContentGuard | None = None
        self._cron_service: ButlerCronService | None = None
        self._mcp_bridge: MCPBridgeAdapter | None = None
        self._acp_server: ButlerACPServer | None = None
        self._rate_limiter: RateLimiter | None = None
        self._connection_manager: ConnectionManager | None = None
        self._realtime_listener: RealtimePubSubListener | None = None
        self._ws_mux: WebSocketMultiplexer | None = None
        self._mercury_protocol: MercuryProtocolService | None = None
        self._a2ui_bridge: A2UIBridgeService | None = None
        self._hermes_transport: HermesTransportEdge | None = None

        self._feature_service: FeatureService | None = None
        self._personalization_engine: PersonalizationEngine | None = None

    def get_breakers(self) -> CircuitBreakerRegistry:
        return get_circuit_breaker_registry()

    def get_lock_manager(self) -> LockManager:
        if self._lock_manager is None:
            self._lock_manager = LockManager(get_redis_sync())
        return self._lock_manager

    def get_state_syncer(self) -> GlobalStateSyncer:
        if self._state_syncer is None:
            self._state_syncer = GlobalStateSyncer(get_redis_sync())
        return self._state_syncer

    def get_health_agent(self) -> ButlerHealthAgent:
        if self._health_agent is None:
            self._health_agent = ButlerHealthAgent(
                get_redis_sync(),
                self.get_state_syncer(),
            )
        return self._health_agent

    def get_ml_runtime(self) -> MLRuntimeManager:
        if self._ml_runtime is None:
            registry = ModelRegistry()
            self._ml_runtime = MLRuntimeManager(
                registry=registry,
                breakers=self.get_breakers(),
                health_agent=self.get_health_agent(),
                metrics=get_metrics(),
            )
        return self._ml_runtime

    def get_jwks_manager(self) -> JWKSManager:
        if self._jwks_manager is None:
            from services.auth.jwt import JWKSManager

            self._jwks_manager = JWKSManager()
        return self._jwks_manager

    def get_redaction_service(self) -> RedactionService:
        if self._redaction_service is None:
            from services.security.redaction import RedactionService

            self._redaction_service = RedactionService()
        return self._redaction_service

    def get_content_guard(self) -> ContentGuard:
        if self._content_guard is None:
            from services.security.safety import ContentGuard

            self._content_guard = ContentGuard()
        return self._content_guard

    def get_feature_service(self) -> FeatureService:
        if self._feature_service is None:
            from services.memory.neo4j_knowledge_repo import Neo4jKnowledgeRepo
            from services.ml.features import FeatureService

            self._feature_service = FeatureService(
                redis=get_redis_sync(),
                graph_repo=Neo4jKnowledgeRepo(),
            )
        return self._feature_service

    def get_personalization_engine(self) -> PersonalizationEngine:
        if self._personalization_engine is None:
            from services.ml.personalization_engine import PersonalizationEngine

            self._personalization_engine = PersonalizationEngine(
                feature_store=self.get_feature_service(),
            )
        return self._personalization_engine

    def get_cron_service(self) -> ButlerCronService:
        if self._cron_service is None:
            self._cron_service = ButlerCronService(
                redis_url=settings.REDIS_URL,
                lock_manager=self.get_lock_manager(),
            )
        return self._cron_service

    def get_mcp_bridge(self) -> MCPBridgeAdapter:
        if self._mcp_bridge is None:
            self._mcp_bridge = MCPBridgeAdapter()
        return self._mcp_bridge

    async def get_acp_server(self) -> ButlerACPServer:
        if self._acp_server is not None:
            return self._acp_server

        async with self._lock:
            if self._acp_server is None:
                redis = await get_redis()
                self._acp_server = ButlerACPServer(redis=redis)

        return self._acp_server

    def get_rate_limiter(self) -> RateLimiter:
        if self._rate_limiter is None:
            self._rate_limiter = RateLimiter(
                redis=get_redis_sync(),
                capacity=settings.RATE_LIMIT_REQUESTS,
                refill_rate=(settings.RATE_LIMIT_REQUESTS / settings.RATE_LIMIT_WINDOW_SECONDS),
                window_s=settings.RATE_LIMIT_WINDOW_SECONDS,
                health_agent=self.get_health_agent(),
            )
        return self._rate_limiter

    async def get_connection_manager(self) -> ConnectionManager:
        if self._connection_manager is not None:
            return self._connection_manager

        async with self._lock:
            if self._connection_manager is None:
                redis = await get_redis()
                presence = PresenceService(redis, self.get_state_syncer())
                self._connection_manager = ConnectionManager(
                    redis,
                    presence,
                    self.get_state_syncer(),
                )

        return self._connection_manager

    async def get_realtime_listener(self) -> RealtimePubSubListener:
        if self._realtime_listener is not None:
            return self._realtime_listener

        async with self._lock:
            if self._realtime_listener is None:
                redis = await get_redis()
                manager = await self.get_connection_manager()
                listener = RealtimePubSubListener(redis, manager)
                manager.set_listener(listener)
                self._realtime_listener = listener

        return self._realtime_listener

    def get_ws_mux(self) -> WebSocketMultiplexer:
        if self._ws_mux is None:
            self._ws_mux = WebSocketMultiplexer()
        return self._ws_mux

    def get_mercury_protocol(self) -> MercuryProtocolService:
        if self._mercury_protocol is None:
            self._mercury_protocol = MercuryProtocolService()
        return self._mercury_protocol

    def get_a2ui_bridge(self) -> A2UIBridgeService:
        if self._a2ui_bridge is None:
            self._a2ui_bridge = A2UIBridgeService()
        return self._a2ui_bridge

    async def get_hermes_transport(self) -> HermesTransportEdge:
        if self._hermes_transport is not None:
            return self._hermes_transport

        async with self._lock:
            if self._hermes_transport is None:
                from services.gateway.auth_middleware import JWTAuthMiddleware

                redis = await get_redis()
                auth = JWTAuthMiddleware(
                    jwks=self.get_jwks_manager(),
                    redis=redis,
                )
                self._hermes_transport = HermesTransportEdge(
                    auth_middleware=auth,
                    redis=redis,
                )

        return self._hermes_transport


_registry = DependencyRegistry()


# ---------------------------------------------------------------------------
# Infrastructure dependencies
# ---------------------------------------------------------------------------


async def get_db(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[AsyncSession, None]:
    """Provide a request-scoped SQLAlchemy async session."""
    yield session


async def get_cache() -> Redis:
    """Provide the shared async Redis client."""
    return await get_redis()


# ---------------------------------------------------------------------------
# Reliability dependencies
# ---------------------------------------------------------------------------


def get_breakers() -> CircuitBreakerRegistry:
    """Provide the global circuit breaker registry."""
    return _registry.get_breakers()


def get_lock_manager() -> LockManager:
    """Provide the application lock manager."""
    return _registry.get_lock_manager()


def get_state_syncer() -> GlobalStateSyncer:
    """Provide the application global state syncer."""
    return _registry.get_state_syncer()


def get_health_agent() -> ButlerHealthAgent:
    """Provide the application health agent."""
    return _registry.get_health_agent()


# ---------------------------------------------------------------------------
# ML & intelligence dependencies
# ---------------------------------------------------------------------------


def get_ml_runtime() -> MLRuntimeManager:
    """Provide the application ML runtime manager."""
    return _registry.get_ml_runtime()


async def get_smart_router(
    redis: Redis = Depends(get_cache),
) -> ButlerSmartRouter:
    """Provide the smart model router."""
    from services.ml.smart_router import ButlerSmartRouter

    del redis
    return ButlerSmartRouter(
        runtime=get_ml_runtime(),
        tri_attention_enabled=settings.TRIATTENTION_ENABLED,
    )


def get_feature_service() -> FeatureService:
    """Provide the feature store used for ranking and personalization."""
    return _registry.get_feature_service()


async def get_ranker(
    redis: Redis = Depends(get_cache),
) -> LightRanker:
    """Provide the lightweight ranking engine."""
    del redis
    return LightRanker(feature_service=get_feature_service())


def get_personalization_engine() -> PersonalizationEngine:
    """Provide the personalization engine."""
    return _registry.get_personalization_engine()


async def get_blender(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_cache),
) -> ButlerBlender:
    """Provide the federated intelligence blender."""
    memory = await get_memory_service(db, redis)
    tools = await get_tools_service(db, redis)
    ranker = await get_ranker(redis)

    return ButlerBlender(
        memory_service=memory,
        tools_service=tools,
        ranking_provider=ranker,
        health_agent=get_health_agent(),
    )


# ---------------------------------------------------------------------------
# Security & safety dependencies
# ---------------------------------------------------------------------------


def get_redaction_service() -> RedactionService:
    """Provide the redaction service."""
    return _registry.get_redaction_service()


def get_content_guard() -> ContentGuard:
    """Provide the content guard service."""
    return _registry.get_content_guard()


def get_jwks_manager() -> JWKSManager:
    """Provide the JWKS manager."""
    return _registry.get_jwks_manager()


async def get_auth_middleware(
    redis: Redis = Depends(get_cache),
) -> JWTAuthMiddleware:
    """Provide the JWT authentication middleware dependency."""
    from services.gateway.auth_middleware import JWTAuthMiddleware

    return JWTAuthMiddleware(
        jwks=get_jwks_manager(),
        redis=redis,
    )


# ---------------------------------------------------------------------------
# Memory & search dependencies
# ---------------------------------------------------------------------------


async def get_memory_service(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_cache),
) -> MemoryService:
    """Provide the memory service for a request."""
    from services.memory.anchored_summarizer import AnchoredSummarizer
    from services.memory.consent_manager import ConsentManager
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
    runtime = get_ml_runtime()
    summarizer = AnchoredSummarizer(runtime)

    if settings.KNOWLEDGE_STORE_BACKEND == "neo4j":
        knowledge_repo = Neo4jKnowledgeRepo()
    else:
        knowledge_repo = PostgresKnowledgeRepo(db)

    cold_store = get_cold_store(snapshot_path=settings.TURBOQUANT_INDEX_PATH or None)

    memory_store = ButlerMemoryStore(
        db=db,
        redis=redis,
        cold_store=cold_store,
        graph_repo=knowledge_repo,
    )

    retrieval = RetrievalFusionEngine(db, embedder, knowledge_repo)
    evolution = MemoryEvolutionEngine(db, retrieval, runtime)
    resolution = EntityResolutionEngine(db, knowledge_repo, runtime)
    understanding = UnderstandingService(
        db,
        runtime,
        knowledge_repo=knowledge_repo,
    )
    context_builder = ContextBuilder(
        token_budget=settings.LONG_CONTEXT_TOKEN_THRESHOLD,
    )
    extraction = KnowledgeExtractionEngine(
        embedder=embedder,
        neo4j_repo=knowledge_repo,
        ml_runtime=runtime,
    )
    consent_manager = ConsentManager()

    service = MemoryService(
        db=db,
        redis=redis,
        embedder=embedder,
        retrieval=retrieval,
        evolution=evolution,
        resolution=resolution,
        understanding=understanding,
        context_builder=context_builder,
        knowledge_repo=knowledge_repo,
        extraction=extraction,
        store=memory_store,
        summarizer=summarizer,
        consent_manager=consent_manager,
    )

    episodic = EpisodicMemoryEngine(
        db=db,
        ml_runtime=runtime,
        memory_recorder=service,
    )
    service.episodic = episodic
    return service


async def get_search_service() -> SearchService:
    """Provide the search service."""
    from services.search.extraction import ContentExtractor
    from services.search.service import SearchService

    return SearchService(
        extractor=ContentExtractor(),
        ml_runtime=get_ml_runtime(),
        breakers=get_breakers(),
    )


async def get_answering_engine() -> AnsweringEngine:
    """Provide the answering engine backed by SearxNG."""
    from services.search.adapters.searxng import SearxNGAdapter
    from services.search.answering_engine import AnsweringEngine

    adapter = SearxNGAdapter(base_url=settings.SEARXNG_URL)
    return AnsweringEngine(
        search_adapter=adapter,
        llm=get_ml_runtime(),
        breakers=get_breakers(),
    )


async def get_tools_service(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_cache),
) -> ToolExecutor:
    """Provide the tool executor service."""
    from domain.tools.hermes_compiler import HermesToolCompiler
    from services.tools.executor import ToolExecutor
    from services.tools.verification import ToolVerifier

    compiler = HermesToolCompiler()
    compiled_specs = {spec.name: spec for spec in compiler.compile_all()}

    return ToolExecutor(
        db=db,
        redis=redis,
        verifier=ToolVerifier(),
        compiled_specs=compiled_specs,
        lock_manager=get_lock_manager(),
        breakers=get_breakers(),
        health_agent=get_health_agent(),
        metrics=get_metrics(),
        node_id=BUTLER_NODE_ID,
    )


# ---------------------------------------------------------------------------
# Orchestration dependencies
# ---------------------------------------------------------------------------


async def get_orchestrator_service(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_cache),
) -> OrchestratorService:
    """Provide the fully wired orchestrator service."""
    from pydantic import SecretStr

    from core.base_config import ButlerBaseConfig
    from domain.orchestrator.hermes_agent_backend import (
        HermesAgentBackend as FullHermesAgentBackend,
    )
    from domain.orchestrator.state import TaskStateMachine
    from services.device.environment import EnvironmentService
    from services.ml.intent import IntentClassifier
    from services.orchestrator.backends import ButlerDeterministicExecutor

    runtime = get_ml_runtime()

    environment_service = EnvironmentService(redis)
    intent_classifier = IntentClassifier(runtime=runtime)
    intake = IntakeProcessor(
        intent_classifier=intent_classifier,
        environment_service=environment_service,
    )
    planner = PlanEngine()

    memory = await get_memory_service(db, redis)
    tools = await get_tools_service(db, redis)
    blender = await get_blender(db, redis)
    smart_router = await get_smart_router(redis)
    feature_service = get_feature_service()

    _registry.get_mcp_bridge().register_native_service(tools)

    redaction = get_redaction_service()
    content_guard = get_content_guard()

    deterministic_backend = ButlerDeterministicExecutor(tools)
    agent_registry = getattr(tools, "_specs", {})
    if not agent_registry:
        logger.warning(
            "hermes_backend_registry_empty",
            message=(
                "No compiled tool specs were found. Agentic policy checks "
                "will fail for all Hermes-driven tools."
            ),
        )

    hermes_backend = FullHermesAgentBackend(compiled_specs=agent_registry)

    kernel = RuntimeKernel(
        deterministic_backend=deterministic_backend,
        hermes_backend=hermes_backend,
    )

    approval_service = await get_acp_server()

    executor = DurableExecutor(
        db=db,
        redis=redis,
        kernel=kernel,
        memory_service=memory,
        tools_service=tools,
        state_machine=TaskStateMachine,
        approval_service=approval_service,
        blender=blender,
        smart_router=smart_router,
        feature_service=feature_service,
        redaction_service=redaction,
        safety_service=safety,
        lock_manager=get_lock_manager(),
    )

    kernel.bind_workflow_backend(executor)

    memory_store = getattr(memory, "_store", None)
    cold_store = getattr(memory_store, "_cold", None) if memory_store else None

    orchestrator_config = ButlerBaseConfig(
        SERVICE_NAME="orchestrator",
        BUTLER_INTERNAL_KEY=(
            settings.BUTLER_INTERNAL_KEY
            if isinstance(settings.BUTLER_INTERNAL_KEY, SecretStr)
            else SecretStr(settings.BUTLER_INTERNAL_KEY)
        ),
    )
    return OrchestratorService(
        db=db,
        redis=redis,
        intake_proc=intake,
        planner=planner,
        executor=executor,
        kernel=kernel,
        blender=blender,
        memory_store=memory_store,
        cold_store=cold_store,
        memory_service=memory,
        tools_service=tools,
        answering_engine=None,
        smart_router=smart_router,
        feature_service=feature_service,
        redaction_service=redaction,
        content_guard=safety,
        config=orchestrator_config,
    )


async def get_cron_service(
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
) -> ButlerCronService:
    """Provide the cron service and bind orchestrator once."""
    service = _registry.get_cron_service()
    if service._orchestrator is None:
        service._orchestrator = orchestrator
    return service


async def get_acp_server() -> ButlerACPServer:
    """Provide the ACP server."""
    return await _registry.get_acp_server()


async def get_mcp_bridge() -> MCPBridgeAdapter:
    """Provide the MCP bridge."""
    return _registry.get_mcp_bridge()


def get_rate_limiter() -> RateLimiter:
    """Provide the application rate limiter."""
    return _registry.get_rate_limiter()


# ---------------------------------------------------------------------------
# Realtime & distributed scaling dependencies
# ---------------------------------------------------------------------------


async def get_connection_manager() -> ConnectionManager:
    """Provide the distributed realtime connection manager."""
    return await _registry.get_connection_manager()


async def get_realtime_listener() -> RealtimePubSubListener:
    """Provide the realtime pub/sub listener."""
    return await _registry.get_realtime_listener()


async def get_hermes_transport() -> HermesTransportEdge:
    """Provide the Hermes transport edge."""
    return await _registry.get_hermes_transport()


async def get_ws_mux() -> WebSocketMultiplexer:
    """Provide the WebSocket multiplexer."""
    return _registry.get_ws_mux()


async def get_mercury_service() -> MercuryProtocolService:
    """Provide the Mercury protocol service."""
    return _registry.get_mercury_protocol()


async def get_a2ui_bridge() -> A2UIBridgeService:
    """Provide the A2UI bridge service."""
    return _registry.get_a2ui_bridge()


def get_request_id(request: Request) -> str:
    """Extract the request identifier from request state."""
    return getattr(request.state, "request_id", "unknown")
