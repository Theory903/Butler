"""Butler application dependencies.

This module provides the dependency injection graph for FastAPI routes.
Hardened to prevent per-request instantiation of heavy ML, orchestration,
and tool compilation objects.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from fastapi import Depends, Request
from pydantic import SecretStr
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from core.base_config import ButlerBaseConfig
from core.circuit_breaker import CircuitBreakerRegistry, get_circuit_breaker_registry
from core.health_agent import ButlerHealthAgent
from core.locks import LockManager
from core.observability import get_metrics
from core.state_sync import GlobalStateSyncer
from domain.ml.contracts import ReasoningTier
from domain.tools.hermes_compiler import ButlerToolSpec
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
from services.tenant import (
    CredentialBroker,
    EntitlementPolicy,
    TenantAuditService,
    TenantContext,
    TenantCryptoService,
    TenantIsolationService,
    TenantMeteringService,
    TenantNamespace,
    TenantQuotaService,
    TenantResolver,
    get_default_policy,
)
from services.tools.mcp_bridge import MCPBridgeAdapter
from services.workflow.acp_server import ButlerACPServer

if TYPE_CHECKING:
    from services.auth.jwt import JWKSManager
    from services.gateway.auth_middleware import JWTAuthMiddleware
    from services.memory.service import MemoryService
    from services.ml.features import FeatureService
    from services.ml.personalization_engine import PersonalizationEngine
    from services.ml.smart_router import ButlerSmartRouter
    from services.search.adapters.searxng import SearxNGAdapter
    from services.search.answering_engine import AnsweringEngine
    from services.search.extraction import ContentExtractor
    from services.search.service import SearchService
    from services.security.egress_policy import EgressPolicy
    from services.security.redaction import RedactionService
    from services.security.safety import ContentGuard
    from services.tools.executor import ToolExecutor
    from services.workspace.cleanup_worker import CleanupWorker
    from services.workspace.workspace_manager import WorkspaceManager

import structlog

logger = structlog.get_logger(__name__)


class DependencyRegistry:
    """Application-lifetime dependency registry.

    Owns process-wide shared dependencies only.
    Request-scoped objects like AsyncSession must never be cached here.
    """

    def __init__(self) -> None:
        import threading
        self._lock = asyncio.Lock()
        self._thread_lock = threading.Lock()

        # Core infrastructure
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
        self._content_extractor: ContentExtractor | None = None
        self._searxng_adapter: SearxNGAdapter | None = None
        self._search_service: SearchService | None = None
        self._answering_engine: AnsweringEngine | None = None

        # Tenant security services
        self._tenant_resolver: TenantResolver | None = None
        self._credential_broker: CredentialBroker | None = None
        self._tenant_crypto_service: TenantCryptoService | None = None

        # Phase 5: Sandbox and browser security
        self._workspace_manager: WorkspaceManager | None = None
        self._egress_policy: EgressPolicy | None = None
        self._cleanup_worker: CleanupWorker | None = None

        # Phase 5: Operation router
        self._operation_router: Any | None = None

        # Heavy AI/ML Singletons (Extracted from per-request generation)
        self._embedding_service: Any | None = None
        self._compiled_tool_specs: dict[str, ButlerToolSpec] | None = None
        self._intent_classifier: Any | None = None
        self._plan_engine: Any | None = None

        # LangGraph integration components
        self._otel: Any | None = None
        self._model_monitoring: Any | None = None
        self._ab_testing: Any | None = None
        self._gateway_hardening: Any | None = None
        self._integrations_catalog: Any | None = None
        self._audit_logger: Any | None = None
        self._pii_detector: Any | None = None
        self._pii_redactor: Any | None = None
        self._memory_tier_reconciliation: Any | None = None
        self._turboquant_backend: Any | None = None
        self._auth_hardening: Any | None = None
        self._langchain_provider_registry: Any | None = None

        # Openclaw port integration components
        self._skills_compiler: Any | None = None
        self._skills_registry: Any | None = None
        self._channel_registry: Any | None = None
        self._memory_host_sdk: Any | None = None

    # ---------------------------------------------------------------------------
    # Heavy Component Singletons
    # ---------------------------------------------------------------------------

    def get_embedding_service(self) -> Any:
        if self._embedding_service is None:
            with self._thread_lock:
                if self._embedding_service is None:
                    from services.ml.embeddings import EmbeddingService
                    self._embedding_service = EmbeddingService(settings.EMBEDDING_MODEL)
        return self._embedding_service

    def get_compiled_tool_specs(self) -> dict[str, ButlerToolSpec]:
        if self._compiled_tool_specs is None:
            with self._thread_lock:
                if self._compiled_tool_specs is None:
                    from domain.tools.hermes_compiler import HermesToolCompiler
                    compiler = HermesToolCompiler()
                    self._compiled_tool_specs = {spec.name: spec for spec in compiler.compile_all()}
        return self._compiled_tool_specs

    def get_intent_classifier(self) -> Any:
        if self._intent_classifier is None:
            with self._thread_lock:
                if self._intent_classifier is None:
                    from services.ml.intent import IntentClassifier
                    self._intent_classifier = IntentClassifier(runtime=self.get_ml_runtime())
        return self._intent_classifier

    def get_plan_engine(self) -> Any:
        if self._plan_engine is None:
            with self._thread_lock:
                if self._plan_engine is None:
                    from services.orchestrator.planner import LLMPlannerBackend, PlanEngine
                    planner_backend = LLMPlannerBackend(runtime=self.get_ml_runtime())
                    self._plan_engine = PlanEngine(planner_backend=planner_backend)
        return self._plan_engine

    # ---------------------------------------------------------------------------
    # Standard Infrastructure
    # ---------------------------------------------------------------------------

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
            from services.ml.provider_health import MLProviderHealthTracker

            self._ml_runtime = MLRuntimeManager(
                registry=ModelRegistry(),
                breakers=self.get_breakers(),
                health_tracker=MLProviderHealthTracker(),
                metrics=get_metrics(),
                max_concurrency=settings.MAX_CONCURRENCY,
                operation_router=self.get_operation_router(),
            )
        return self._ml_runtime

    def get_operation_router(self) -> Any:
        if self._operation_router is None:
            from domain.orchestration.router import AdmissionController, OperationRouter

            admission_controller = AdmissionController(enable_rate_limiting=True)
            self._operation_router = OperationRouter(admission_controller=admission_controller)
        return self._operation_router

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
                refill_rate=settings.RATE_LIMIT_REQUESTS / settings.RATE_LIMIT_WINDOW_SECONDS,
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

        redis = await get_redis()
        if self._connection_manager is None:
            presence = PresenceService(redis, self.get_state_syncer())
            self._connection_manager = ConnectionManager(
                redis,
                presence,
                self.get_state_syncer(),
            )
        manager = self._connection_manager
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

    def get_content_extractor(self) -> ContentExtractor:
        if self._content_extractor is None:
            from services.search.extraction import ContentExtractor

            self._content_extractor = ContentExtractor()
        return self._content_extractor

    def get_searxng_adapter(self) -> SearxNGAdapter:
        if self._searxng_adapter is None:
            from services.search.adapters.searxng import SearxNGAdapter

            self._searxng_adapter = SearxNGAdapter(base_url=settings.SEARXNG_URL)
        return self._searxng_adapter

    def get_search_service(self) -> SearchService:
        if self._search_service is None:
            from services.search.service import SearchService

            self._search_service = SearchService(
                extractor=self.get_content_extractor(),
                ml_runtime=self.get_ml_runtime(),
                breakers=self.get_breakers(),
            )
        return self._search_service

    def get_answering_engine(self) -> AnsweringEngine:
        if self._answering_engine is None:
            from services.search.answering_engine import AnsweringEngine

            self._answering_engine = AnsweringEngine(
                search_adapter=self.get_searxng_adapter(),
                llm=self.get_ml_runtime(),
                breakers=self.get_breakers(),
            )
        return self._answering_engine

    def get_tenant_resolver(self) -> TenantResolver:
        if self._tenant_resolver is None:
            self._tenant_resolver = TenantResolver()
        return self._tenant_resolver

    def get_credential_broker(self) -> CredentialBroker:
        if self._credential_broker is None:
            self._credential_broker = CredentialBroker()
        return self._credential_broker

    def get_tenant_crypto_service(self) -> TenantCryptoService:
        if self._tenant_crypto_service is None:
            self._tenant_crypto_service = TenantCryptoService()
        return self._tenant_crypto_service

    def get_workspace_manager(self) -> WorkspaceManager:
        if self._workspace_manager is None:
            from services.workspace.workspace_manager import WorkspaceManager

            self._workspace_manager = WorkspaceManager()
        return self._workspace_manager

    def get_egress_policy(self) -> EgressPolicy:
        if self._egress_policy is None:
            from services.security.egress_policy import EgressPolicy

            self._egress_policy = EgressPolicy.get_default()
        return self._egress_policy

    def get_cleanup_worker(self) -> CleanupWorker:
        if self._cleanup_worker is None:
            from services.workspace.cleanup_worker import CleanupWorker

            self._cleanup_worker = CleanupWorker(
                workspace_manager=self.get_workspace_manager(),
            )
        return self._cleanup_worker

    def get_tool_specs(self) -> list[ButlerToolSpec]:
        """Get compiled ButlerToolSpec list for LangGraph backend."""
        # Now safely fetching from cache instead of recompiling
        return list(self.get_compiled_tool_specs().values())

    def get_checkpoint_config(self) -> dict[str, Any] | None:
        """Get LangGraph checkpoint configuration."""
        try:
            from infrastructure.config import settings

            return {
                "connection_string": settings.DATABASE_URL,
            }
        except Exception:
            return None


_registry = DependencyRegistry()


# ---------------------------------------------------------------------------
# Tenant context dependencies
# ---------------------------------------------------------------------------


async def get_tenant_context(
    request: Request,
    tenant_resolver: TenantResolver = Depends(lambda: _registry.get_tenant_resolver()),
) -> TenantContext:
    """
    Provide TenantContext from validated JWT/session.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise ValueError("Tenant context not available - authentication required")

    from services.tenant.context import IsolationLevel

    return TenantContext(
        tenant_id=tenant_id,
        account_id=tenant_id,
        user_id=getattr(request.state, "user_id", "system"),
        plan=getattr(request.state, "plan", "free"),
        region=settings.ENVIRONMENT,
        isolation_level=IsolationLevel.SHARED,
        request_id=getattr(request.state, "request_id", ""),
        session_id=getattr(request.state, "session_id", ""),
        actor_type=getattr(request.state, "actor_type", "user"),
        scopes=frozenset(getattr(request.state, "scopes", ["read"])),
        metadata={},
        tenant_slug=getattr(request.state, "tenant_slug", None),
        org_id=getattr(request.state, "org_id", None),
    )


# ---------------------------------------------------------------------------
# Infrastructure dependencies
# ---------------------------------------------------------------------------


async def get_db(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[AsyncSession]:
    """Provide a request-scoped SQLAlchemy async session."""
    yield session


async def get_cache() -> Redis:
    """Provide the shared async Redis client."""
    return await get_redis()


# ---------------------------------------------------------------------------
# Reliability dependencies
# ---------------------------------------------------------------------------


def get_breakers() -> CircuitBreakerRegistry:
    return _registry.get_breakers()


def get_lock_manager() -> LockManager:
    return _registry.get_lock_manager()


def get_state_syncer() -> GlobalStateSyncer:
    return _registry.get_state_syncer()


def get_health_agent() -> ButlerHealthAgent:
    return _registry.get_health_agent()


# ---------------------------------------------------------------------------
# ML & intelligence dependencies
# ---------------------------------------------------------------------------


def get_ml_runtime() -> MLRuntimeManager:
    return _registry.get_ml_runtime()


async def get_smart_router(
    redis: Redis = Depends(get_cache),
) -> ButlerSmartRouter:
    from services.ml.smart_router import ButlerSmartRouter

    del redis
    return ButlerSmartRouter(
        runtime=get_ml_runtime(),
        tri_attention_enabled=settings.TRIATTENTION_ENABLED,
    )


def get_feature_service() -> FeatureService:
    return _registry.get_feature_service()


def get_personalization_engine() -> PersonalizationEngine:
    return _registry.get_personalization_engine()


async def get_ranker(
    redis: Redis = Depends(get_cache),
) -> LightRanker:
    del redis
    return LightRanker(feature_service=get_feature_service())


async def get_blender(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_cache),
) -> ButlerBlender:
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
    return _registry.get_redaction_service()


def get_content_guard() -> ContentGuard:
    return _registry.get_content_guard()


def get_jwks_manager() -> JWKSManager:
    return _registry.get_jwks_manager()


async def get_auth_middleware(
    redis: Redis = Depends(get_cache),
) -> JWTAuthMiddleware:
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

    # Pulling heavy objects from Registry to avoid O(N) per-request bottleneck
    embedder = _registry.get_embedding_service()
    runtime = get_ml_runtime()
    summarizer = AnchoredSummarizer(runtime)

    if settings.KNOWLEDGE_STORE_BACKEND == "neo4j":
        knowledge_repo = Neo4jKnowledgeRepo()
    else:
        knowledge_repo = PostgresKnowledgeRepo(db)

    cold_store = get_cold_store(snapshot_path=settings.TURBOQUANT_INDEX_PATH or None)
    consent_manager = ConsentManager()

    memory_store = ButlerMemoryStore(
        db=db,
        redis=redis,
        embedder=embedder,
        cold_store=cold_store,
        graph_repo=knowledge_repo,
        consent_manager=consent_manager,
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

    operation_router = _registry.get_operation_router()

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
        operation_router=operation_router,
    )

    episodic = EpisodicMemoryEngine(
        db=db,
        ml_runtime=runtime,
        memory_recorder=service,
    )
    service.episodic = episodic
    return service


async def get_search_service() -> SearchService:
    return _registry.get_search_service()


async def get_answering_engine() -> AnsweringEngine:
    return _registry.get_answering_engine()


async def get_tools_service(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_cache),
) -> ToolExecutor:
    from services.tools.executor import ToolExecutor
    from services.tools.verification import ToolVerifier

    # Using pre-compiled singleton from Registry
    compiled_specs = _registry.get_compiled_tool_specs()

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

_langgraph_checkpointer: object | None = None

async def get_langgraph_checkpointer() -> object | None:
    global _langgraph_checkpointer
    if _langgraph_checkpointer is not None:
        return _langgraph_checkpointer

    try:
        from infrastructure.database import engine
        from services.orchestrator.checkpointer import build_postgres_checkpointer

        _langgraph_checkpointer = build_postgres_checkpointer(engine)
        logger.info("langgraph_checkpointer_initialized")
        return _langgraph_checkpointer
    except Exception:
        logger.debug("langgraph_checkpointer_unavailable")
        return None


_langchain_model_factory: object | None = None

def get_langchain_model_factory():
    global _langchain_model_factory
    if _langchain_model_factory is not None:
        return _langchain_model_factory

    try:
        from backend.langchain.models import ChatModelFactory

        _langchain_model_factory = ChatModelFactory()
        logger.info("langchain_model_factory_initialized")
        return _langchain_model_factory
    except Exception:
        logger.debug("langchain_model_factory_unavailable")
        return None


_butler_tool_adapter_registry: object | None = None

def get_butler_tool_adapter_registry():
    global _butler_tool_adapter_registry
    if _butler_tool_adapter_registry is not None:
        return _butler_tool_adapter_registry

    try:
        from backend.langchain.tools import ToolRegistry

        _butler_tool_adapter_registry = ToolRegistry()
        logger.info("butler_tool_adapter_registry_initialized")
        return _butler_tool_adapter_registry
    except Exception:
        logger.debug("butler_tool_adapter_registry_unavailable")
        return None


_butler_memory_adapter: object | None = None

def get_butler_memory_adapter():
    global _butler_memory_adapter
    if _butler_memory_adapter is not None:
        return _butler_memory_adapter

    try:
        from backend.langchain.memory import ButlerMemoryAdapter
        _butler_memory_adapter = ButlerMemoryAdapter
        logger.info("butler_memory_adapter_initialized")
        return _butler_memory_adapter
    except Exception:
        logger.debug("butler_memory_adapter_unavailable")
        return None


_butler_search_retriever: object | None = None

def get_butler_search_retriever():
    global _butler_search_retriever
    if _butler_search_retriever is not None:
        return _butler_search_retriever

    try:
        from backend.langchain.retrievers import ButlerSearchRetriever
        _butler_search_retriever = ButlerSearchRetriever
        logger.info("butler_search_retriever_initialized")
        return _butler_search_retriever
    except Exception:
        logger.debug("butler_search_retriever_unavailable")
        return None


_butler_evaluator: object | None = None

def get_butler_evaluator():
    global _butler_evaluator
    if _butler_evaluator is not None:
        return _butler_evaluator

    try:
        from backend.langchain.evaluator import ButlerEvaluator

        _butler_evaluator = ButlerEvaluator()
        logger.info("butler_evaluator_initialized")
        return _butler_evaluator
    except Exception:
        logger.debug("butler_evaluator_unavailable")
        return None


async def get_orchestrator_service(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_cache),
) -> OrchestratorService:
    from domain.orchestrator.runtime_kernel import RuntimeKernel
    from domain.orchestrator.state import TaskStateMachine
    from services.device.environment import EnvironmentService
    from services.orchestrator.backends import (
        ButlerDeterministicExecutor,
        create_agent_backend,
    )

    runtime = get_ml_runtime()
    environment_service = EnvironmentService(redis)
    
    # Use global Singletons for stateless ML layers
    intent_classifier = _registry.get_intent_classifier()
    planner = _registry.get_plan_engine()

    intake = IntakeProcessor(
        intent_classifier=intent_classifier,
        environment_service=environment_service,
    )

    memory = await get_memory_service(db, redis)
    tools = await get_tools_service(db, redis)
    blender = await get_blender(db, redis)
    smart_router = await get_smart_router(redis)
    feature_service = get_feature_service()

    _registry.get_mcp_bridge().register_native_service(tools)

    redaction = get_redaction_service()
    content_guard = get_content_guard()

    deterministic_backend = ButlerDeterministicExecutor(tools)

    tool_specs = _registry.get_tool_specs()
    # Filter out blocked tools before validation
    tool_specs = [spec for spec in tool_specs if not (hasattr(spec, "blocked") and spec.blocked)]
    checkpoint_config = _registry.get_checkpoint_config()

    from langchain.butler_direct_tools import get_time_tool
    from langchain.butler_web_tools import web_search_tool

    _direct_implementations: dict = {
        "web_search": web_search_tool,
        "get_time": get_time_tool,
    }

    from domain.tools.hermes_compiler import RiskTier

    def _validate_l0_l1_tools_have_implementations(
        tool_specs: list,
        direct_implementations: dict,
    ) -> None:
        for spec in tool_specs:
            if hasattr(spec, "risk_tier") and spec.risk_tier in (RiskTier.L0, RiskTier.L1):
                tool_name = (
                    spec.name
                    if hasattr(spec, "name")
                    else getattr(spec, "canonical_name", str(spec))
                )
                if tool_name not in direct_implementations:
                    raise RuntimeError(
                        f"L0/L1 tool '{tool_name}' is exposed but has no direct implementation."
                    )

    from domain.tools.registry import get_tool_registry

    tool_registry = get_tool_registry()
    registry_errors = tool_registry.validate_invariants()
    if registry_errors:
        logger.error("tool_registry_invariant_check_failed")
        raise RuntimeError(f"Tool registry invariant check failed: {registry_errors}")

    _validate_l0_l1_tools_have_implementations(tool_specs, _direct_implementations)

    agent_backend = create_agent_backend(
        ml_runtime=runtime,
        tools_service=tools,
        tool_specs=tool_specs,
        tool_executor=tools,
        direct_implementations=_direct_implementations,
        checkpoint_config=checkpoint_config,
        default_tier=ReasoningTier.T2,
        stream_chunk_size=64,
    )

    kernel = RuntimeKernel(
        deterministic_backend=deterministic_backend,
        hermes_backend=agent_backend,
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
        safety_service=content_guard,
        lock_manager=get_lock_manager(),
        model=settings.DEFAULT_MODEL,
    )

    if hasattr(kernel, "bind_workflow_backend"):
        kernel.bind_workflow_backend(executor)
    else:
        kernel._workflow = executor  # noqa: SLF001

    memory_store = getattr(memory, "_store", None)
    cold_store = getattr(memory_store, "_cold", None) if memory_store else None

    internal_key = settings.BUTLER_INTERNAL_KEY
    orchestrator_config = ButlerBaseConfig(
        SERVICE_NAME="orchestrator",
        ENVIRONMENT=settings.ENVIRONMENT,
        PORT=settings.PORT,
        LOG_LEVEL=settings.LOG_LEVEL,
        MAX_CONCURRENCY=settings.MAX_CONCURRENCY,
        BUTLER_INTERNAL_KEY=(
            internal_key if isinstance(internal_key, SecretStr) else SecretStr(str(internal_key))
        ),
    )

    return OrchestratorService(
        db=db,
        redis=redis,
        intake_proc=intake,
        planner=planner,
        executor=executor,
        blender=blender,
        memory_store=memory_store,
        cold_store=cold_store,
        memory_service=memory,
        tools_service=tools,
        answering_engine=None,
        smart_router=smart_router,
        feature_service=feature_service,
        redaction_service=redaction,
        content_guard=content_guard,
        config=orchestrator_config,
        checkpointer=await get_langgraph_checkpointer(),
    )


async def get_cron_service(
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
) -> ButlerCronService:
    service = _registry.get_cron_service()
    if getattr(service, "_orchestrator", None) is None:
        service._orchestrator = orchestrator  # noqa: SLF001
    return service


async def get_acp_server() -> ButlerACPServer:
    return await _registry.get_acp_server()


async def get_mcp_bridge() -> MCPBridgeAdapter:
    return _registry.get_mcp_bridge()


# ---------------------------------------------------------------------------
# Realtime & distributed scaling dependencies
# ---------------------------------------------------------------------------


async def get_connection_manager() -> ConnectionManager:
    return await _registry.get_connection_manager()


async def get_realtime_listener() -> RealtimePubSubListener:
    return await _registry.get_realtime_listener()


async def get_hermes_transport() -> HermesTransportEdge:
    return await _registry.get_hermes_transport()


async def get_ws_mux() -> WebSocketMultiplexer:
    return _registry.get_ws_mux()


async def get_mercury_service() -> MercuryProtocolService:
    return _registry.get_mercury_protocol()


async def get_a2ui_bridge() -> A2UIBridgeService:
    return _registry.get_a2ui_bridge()


def get_rate_limiter() -> RateLimiter:
    return _registry.get_rate_limiter()


# ---------------------------------------------------------------------------
# Tenant security dependencies
# ---------------------------------------------------------------------------


def get_tenant_resolver() -> TenantResolver:
    return _registry.get_tenant_resolver()


def get_credential_broker() -> CredentialBroker:
    return _registry.get_credential_broker()


def get_tenant_crypto_service() -> TenantCryptoService:
    return _registry.get_tenant_crypto_service()


def get_workspace_manager() -> WorkspaceManager:
    return _registry.get_workspace_manager()


def get_egress_policy() -> EgressPolicy:
    return _registry.get_egress_policy()


def get_cleanup_worker() -> CleanupWorker:
    return _registry.get_cleanup_worker()


def get_tenant_namespace(tenant_id: str) -> TenantNamespace:
    return TenantNamespace(tenant_id=tenant_id)


def get_entitlement_policy(plan: str = "free") -> EntitlementPolicy:
    return get_default_policy(plan)


def get_tenant_quota_service(plan: str = "free") -> TenantQuotaService:
    return TenantQuotaService(plan=plan)


def get_tenant_metering_service() -> TenantMeteringService:
    return TenantMeteringService()


def get_tenant_audit_service() -> TenantAuditService:
    return TenantAuditService()


def get_tenant_isolation_service(
    level: str = "shared",
) -> TenantIsolationService:
    return TenantIsolationService(level=level)


# ---------------------------------------------------------------------------
# LangGraph integration dependencies
# ---------------------------------------------------------------------------


def get_otel() -> Any:
    if _registry._otel is None:
        from observability.otel import ButlerOpenTelemetry

        _registry._otel = ButlerOpenTelemetry(
            service_name="butler-backend",
            otlp_endpoint=settings.OTEL_ENDPOINT if hasattr(settings, "OTEL_ENDPOINT") else None,
        )
        _registry._otel.initialize()
    return _registry._otel


def get_model_monitoring() -> Any:
    if _registry._model_monitoring is None:
        from observability.model_monitoring import ButlerModelMonitoring

        _registry._model_monitoring = ButlerModelMonitoring(port=9090)
        _registry._model_monitoring.initialize()
    return _registry._model_monitoring


def get_ab_testing() -> Any:
    if _registry._ab_testing is None:
        from observability.ab_testing import ButlerABTesting

        _registry._ab_testing = ButlerABTesting()
    return _registry._ab_testing


def get_gateway_hardening() -> Any:
    if _registry._gateway_hardening is None:
        from api.gateway.hardening import GatewayHardening

        _registry._gateway_hardening = GatewayHardening(redis_client=get_redis_sync())
        _registry._gateway_hardening.configure_slowapi()
        _registry._gateway_hardening.configure_default_headers()
    return _registry._gateway_hardening


def get_integrations_catalog() -> Any:
    if _registry._integrations_catalog is None:
        from deployment.integrations_catalog import IntegrationsCatalog, load_default_integrations

        _registry._integrations_catalog = IntegrationsCatalog()
        load_default_integrations(_registry._integrations_catalog)
    return _registry._integrations_catalog


def get_audit_logger() -> Any:
    if _registry._audit_logger is None:
        from compliance.audit import AuditLogger

        _registry._audit_logger = AuditLogger()
    return _registry._audit_logger


def get_pii_detector() -> Any:
    if _registry._pii_detector is None:
        from compliance.pii import PIIDetector

        _registry._pii_detector = PIIDetector()
    return _registry._pii_detector


def get_pii_redactor() -> Any:
    if _registry._pii_redactor is None:
        from compliance.pii import PIIRedactor

        _registry._pii_redactor = PIIRedactor()
    return _registry._pii_redactor


def get_memory_tier_reconciliation() -> Any:
    if _registry._memory_tier_reconciliation is None:
        from services.memory.tier_reconciliation import MemoryTierReconciliation

        _registry._memory_tier_reconciliation = MemoryTierReconciliation(
            redis=get_redis_sync(),
            db=None, 
            turboquant=get_turboquant_backend(),
        )
    return _registry._memory_tier_reconciliation


def get_turboquant_backend() -> Any:
    if _registry._turboquant_backend is None:
        from services.ml.providers.turboquant import TurboQuantBackend

        _registry._turboquant_backend = TurboQuantBackend(config={"compression_level": 3})
    return _registry._turboquant_backend


def get_auth_hardening() -> Any:
    if _registry._auth_hardening is None:
        from services.auth.hardening import AuthHardeningService

        _registry._auth_hardening = AuthHardeningService()
    return _registry._auth_hardening


def get_langchain_provider_registry() -> Any:
    if _registry._langchain_provider_registry is None:
        from langchain.providers import ProviderRegistry

        _registry._langchain_provider_registry = ProviderRegistry()
    return _registry._langchain_provider_registry


def get_skills_compiler() -> Any:
    if _registry._skills_compiler is None:
        from langchain.skills import ButlerSkillCompiler

        _registry._skills_compiler = ButlerSkillCompiler()
    return _registry._skills_compiler


def get_skills_registry() -> Any:
    if _registry._skills_registry is None:
        from langchain.skills import ButlerSkillRegistry

        _registry._skills_registry = ButlerSkillRegistry()
    return _registry._skills_registry


def get_channel_registry() -> Any:
    if _registry._channel_registry is None:
        from services.realtime.channels import ChannelRegistry

        _registry._channel_registry = ChannelRegistry()
    return _registry._channel_registry


def get_memory_host_sdk() -> Any:
    if _registry._memory_host_sdk is None:
        from services.memory.host_sdk import (
            EmbeddingModelLimits,
            MemoryBackendConfig,
        )

        config = MemoryBackendConfig(
            backend_type="redis",
            connection_string="redis://localhost:6379/2",
            namespace="butler_memory",
        )
        _registry._memory_host_sdk = {"config": config, "limits": EmbeddingModelLimits}
    return _registry._memory_host_sdk


def get_request_id(request: Request) -> str:
    """Extract request_id from request state."""
    return getattr(request.state, "request_id", "unknown")