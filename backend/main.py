"""Butler API — application assembly.

This module is responsible only for:
- application startup/shutdown orchestration
- middleware registration
- exception handler registration
- route registration

No business logic belongs here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.routes.internal_control import InternalOnlyMiddleware, internal_router
from core.circuit_breaker import get_circuit_breaker_registry
from core.deps import (
    get_ab_testing,
    get_audit_logger,
    get_auth_hardening,
    get_channel_registry,
    get_cleanup_worker,
    get_cron_service,
    get_gateway_hardening,
    get_health_agent,
    get_integrations_catalog,
    get_langchain_provider_registry,
    get_mcp_bridge,
    get_memory_host_sdk,
    get_ml_runtime,
    get_model_monitoring,
    get_otel,
    get_pii_detector,
    get_pii_redactor,
    get_rate_limiter,
    get_realtime_listener,
    get_skills_compiler,
    get_skills_registry,
    get_state_syncer,
    get_tenant_resolver,
    get_turboquant_backend,
)
from core.errors import (
    InternalError,
    Problem,
    http_exception_handler,
    problem_exception_handler,
    validation_exception_handler,
)
from core.health import create_health_router
from core.idempotency import IdempotencyMiddleware
from core.logging import setup_logging
from core.middleware import (
    RequestContextMiddleware,
    RuntimeContextMiddleware,
    TenantContextMiddleware,
    TrafficGuardMiddleware,
)
from core.observability import ObservabilityMiddleware, setup_observability
from infrastructure.cache import close_redis, get_redis, get_redis_sync
from infrastructure.config import settings
from infrastructure.database import close_db, engine, init_db
from infrastructure.memory.neo4j_client import neo4j_client
from infrastructure.memory.qdrant_client import qdrant_client
from services.gateway.rate_limiter import RateLimitMiddleware

logger = structlog.get_logger(__name__)


async def _startup_doctor_check() -> None:
    from core.doctor import ButlerDoctor

    doctor = ButlerDoctor()
    report = await doctor.diagnose(fix=True)

    if not report.ok:
        logger.warning(
            "butler_doctor_found_issues",
            checks=[c.model_dump() for c in report.checks if c.status == "FAIL"],
        )
    else:
        logger.info(
            "butler_doctor_passed",
            fixed_count=len([c for c in report.checks if c.status == "FIXED"]),
        )


async def _startup_data_backends() -> None:
    await init_db()
    logger.info("database_connected")

    await get_redis()
    logger.info("redis_connected")

    if settings.KNOWLEDGE_STORE_BACKEND == "neo4j":
        await neo4j_client.connect()
        logger.info("neo4j_connected")

    if settings.VECTOR_STORE_BACKEND == "qdrant":
        await qdrant_client.connect()
        logger.info("qdrant_connected")


async def _startup_application_services() -> None:
    runtime = get_ml_runtime()
    await runtime.on_startup()

    cron_service = await get_cron_service()
    await cron_service.start()

    manifest_path = Path(settings.BUTLER_DATA_DIR) / "mcp" / "manifest.json"
    mcp_bridge = await get_mcp_bridge()
    mcp_bridge.load_manifest_from_file(str(manifest_path))

    realtime_listener = await get_realtime_listener()
    await realtime_listener.start()

    state_syncer = get_state_syncer()
    await state_syncer.start_listening()

    health_agent = get_health_agent()
    await health_agent.start()

    cleanup_worker = get_cleanup_worker()
    await cleanup_worker.start()

    # Initialize langchain Hermes tools
    try:
        from backend.langchain.hermes_loader import load_safe_hermes_tools
        from backend.langchain.hermes_governance import register_hermes_tools_in_butler

        specs = load_safe_hermes_tools()
        logger.info("hermes_tools_loaded", count=len(specs))

        # Register Hermes tools in Butler governance
        register_hermes_tools_in_butler()
        logger.info("hermes_tools_registered_in_butler")
    except Exception as exc:
        logger.warning("hermes_tools_initialization_failed", error=str(exc))

    # Initialize LangGraph integration components
    try:
        # OpenTelemetry
        get_otel()
        logger.info("otel_initialized")

        # Model monitoring
        get_model_monitoring()
        logger.info("model_monitoring_initialized")

        # AB testing
        get_ab_testing()
        logger.info("ab_testing_initialized")

        # Gateway hardening
        get_gateway_hardening()
        logger.info("gateway_hardening_initialized")

        # Integrations catalog
        get_integrations_catalog()
        logger.info("integrations_catalog_initialized")

        # Audit logger
        get_audit_logger()
        logger.info("audit_logger_initialized")

        # PII detection/redaction
        get_pii_detector()
        get_pii_redactor()
        logger.info("pii_services_initialized")

        # TurboQuant backend
        turboquant = get_turboquant_backend()
        await turboquant.initialize()
        logger.info("turboquant_backend_initialized")

        # Auth hardening
        get_auth_hardening()
        logger.info("auth_hardening_initialized")

        # LangChain provider registry
        provider_registry = get_langchain_provider_registry()
        await provider_registry.initialize_all()
        logger.info("langchain_provider_registry_initialized")

        # Skills compiler + registry (load openclaw skills)
        skills_compiler = get_skills_compiler()
        skills_registry = get_skills_registry()
        from langchain.skills import load_all_into_compiler

        loaded_count = load_all_into_compiler(skills_compiler)
        logger.info("openclaw_skills_loaded", count=loaded_count)

        # Channel registry
        channel_registry = get_channel_registry()
        logger.info("channel_registry_initialized")

        # Memory host SDK
        get_memory_host_sdk()
        logger.info("memory_host_sdk_initialized")

    except Exception as exc:
        logger.error("langgraph_components_initialization_failed", error=str(exc))

    logger.info("ml_runtime_warmed")


async def _shutdown_application_services() -> None:
    shutdown_errors: list[str] = []

    async def _safe_shutdown(name: str, fn: Callable[[], Awaitable[None]]) -> None:
        try:
            await fn()
            logger.info("shutdown_step_complete", step=name)
        except Exception as exc:
            shutdown_errors.append(f"{name}: {exc}")
            logger.exception("shutdown_step_failed", step=name)

    async def _stop_realtime_listener() -> None:
        listener = await get_realtime_listener()
        await listener.stop()

    async def _stop_state_syncer() -> None:
        await get_state_syncer().stop_listening()

    async def _stop_health_agent() -> None:
        await get_health_agent().shutdown()

    async def _stop_cron_service() -> None:
        cron_service = await get_cron_service()
        await cron_service.shutdown()

    async def _stop_ml_runtime() -> None:
        await get_ml_runtime().shutdown()

    async def _stop_cleanup_worker() -> None:
        cleanup_worker = get_cleanup_worker()
        await cleanup_worker.stop()

    async def _stop_otel() -> None:
        otel = get_otel()
        otel.shutdown()

    async def _stop_channel_registry() -> None:
        channel_registry = get_channel_registry()
        await channel_registry.disconnect_all()

    async def _stop_langchain_providers() -> None:
        provider_registry = get_langchain_provider_registry()
        await provider_registry.shutdown_all()

    await _safe_shutdown("cleanup_worker", _stop_cleanup_worker)
    await _safe_shutdown("realtime_listener", _stop_realtime_listener)
    await _safe_shutdown("state_syncer", _stop_state_syncer)
    await _safe_shutdown("health_agent", _stop_health_agent)
    await _safe_shutdown("cron_service", _stop_cron_service)
    await _safe_shutdown("ml_runtime", _stop_ml_runtime)
    await _safe_shutdown("langchain_providers", _stop_langchain_providers)
    await _safe_shutdown("channel_registry", _stop_channel_registry)
    await _safe_shutdown("otel", _stop_otel)
    await _safe_shutdown("redis", close_redis)
    await _safe_shutdown("database", close_db)
    await _safe_shutdown("neo4j", neo4j_client.close)
    await _safe_shutdown("qdrant", qdrant_client.close)

    if shutdown_errors:
        logger.warning("butler_shutdown_completed_with_errors", errors=shutdown_errors)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan hooks."""
    del app

    setup_logging(settings.SERVICE_NAME, settings.ENVIRONMENT)
    logger.info(
        "butler_starting",
        version=settings.SERVICE_VERSION,
        env=settings.ENVIRONMENT,
    )

    await _startup_doctor_check()
    await _startup_data_backends()
    await _startup_application_services()

    logger.info("butler_ready")
    try:
        yield
    finally:
        logger.info("butler_shutting_down")
        await _shutdown_application_services()
        logger.info("butler_stopped")


app = FastAPI(
    title="Butler API",
    description="Personal AI system — production backend",
    version=settings.SERVICE_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)


# -----------------------------------------------------------------------------
# Middleware stack
# -----------------------------------------------------------------------------
app.add_middleware(InternalOnlyMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(TenantContextMiddleware, tenant_resolver_getter=get_tenant_resolver)
app.add_middleware(RuntimeContextMiddleware)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(ObservabilityMiddleware)
app.add_middleware(TrafficGuardMiddleware, redis_getter=get_redis)

_global_limiter = get_rate_limiter()
app.add_middleware(RateLimitMiddleware, limiter=_global_limiter)

setup_observability(app, settings.SERVICE_NAME, settings.OTEL_ENDPOINT)


# -----------------------------------------------------------------------------
# Exception handlers
# -----------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "unhandled_exception",
        path=str(request.url.path),
        method=request.method,
    )
    return await problem_exception_handler(
        request,
        InternalError("An unexpected internal error occurred."),
    )


app.add_exception_handler(Problem, problem_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)


# -----------------------------------------------------------------------------
# Health dependencies
# -----------------------------------------------------------------------------
async def _check_db() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _check_redis() -> None:
    redis = await get_redis()
    await redis.ping()


async def _check_doctor() -> None:
    from core.doctor import ButlerDoctor

    report = await ButlerDoctor().diagnose(fix=False)
    if not report.ok:
        raise RuntimeError("Security or infrastructure audit failed. Run doctor --fix.")

    degraded_ids = [c.id for c in report.checks if c.status == "DEGRADED"]
    if degraded_ids:
        logger.warning("system_degraded", checks=degraded_ids)


app.include_router(
    create_health_router(
        deps={
            "database": _check_db,
            "redis": _check_redis,
            "doctor": _check_doctor,
        },
        prefix="/api/v1",
        circuit_breaker_registry=get_circuit_breaker_registry(),
        critical_deps={"database", "redis", "doctor"},
        version=settings.SERVICE_VERSION,
    )
)

# -----------------------------------------------------------------------------
# Openclaw port integration routes
# -----------------------------------------------------------------------------
from api.routes.integrations import channels as channel_routes
from api.routes.integrations import providers as provider_routes

app.include_router(provider_routes.router, prefix="/api/v1")
app.include_router(channel_routes.router, prefix="/api/v1")

app.include_router(
    create_health_router(
        deps={
            "database": _check_db,
            "redis": _check_redis,
            "doctor": _check_doctor,
        },
        prefix="",
        include_in_schema=False,
        circuit_breaker_registry=get_circuit_breaker_registry(),
        critical_deps={"database", "redis", "doctor"},
        version=settings.SERVICE_VERSION,
    )
)


# -----------------------------------------------------------------------------
# Well-known endpoints
# -----------------------------------------------------------------------------
@app.get("/.well-known/jwks.json", tags=["auth"])
async def jwks_discovery() -> dict[str, Any]:
    from services.auth.jwt import get_jwks_manager

    return get_jwks_manager().get_jwks_document()


# -----------------------------------------------------------------------------
# Route registration
# -----------------------------------------------------------------------------
from api.routes import (  # noqa: E402
    audio,
    auth,
    canvas,
    communication,
    device,
    gateway,
    meetings,
    memory,
    mercury,
    ml,
    orchestrator,
    realtime,
    research,
    search,
    security,
    tools,
    vision,
    voice_gateway,
)
from api.routes.acp import create_acp_router  # noqa: E402
from api.routes.admin import create_admin_router  # noqa: E402
from api.routes.cron import create_cron_router  # noqa: E402
from api.routes.mcp import mcp_router  # noqa: E402

# Google Workspace integration not available in upstream Hermes agent
# from integrations.hermes.skills.productivity.google_workspace import (  # noqa: E402
#     auth_flow as google_auth_flow,
# )
from services.memory.mcp_server import router as memory_mcp_router  # noqa: E402

app.include_router(auth.router, prefix="/api/v1")
app.include_router(gateway.router, prefix="/api/v1")
app.include_router(orchestrator.router, prefix="/api/v1")

app.include_router(create_admin_router(cluster_redis=get_redis_sync()), prefix="/api/v1")
app.include_router(create_acp_router(), prefix="/api/v1")
app.include_router(create_cron_router(), prefix="/api/v1")

app.include_router(memory.router, prefix="/api/v1")
app.include_router(tools.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(ml.router, prefix="/api/v1")
app.include_router(realtime.router, prefix="/api/v1")
app.include_router(communication.router, prefix="/api/v1")
app.include_router(security.router, prefix="/api/v1")
app.include_router(device.router, prefix="/api/v1")
app.include_router(vision.router, prefix="/api/v1")
app.include_router(audio.router, prefix="/api/v1")
app.include_router(research.router, prefix="/api/v1")
app.include_router(meetings.router, prefix="/api/v1")
app.include_router(voice_gateway.router)
# Google Workspace integration not available in upstream Hermes agent
# app.include_router(google_auth_flow.router, prefix="/api/v1")
app.include_router(mcp_router, prefix="/api/v1")
app.include_router(memory_mcp_router, prefix="/api/v1")
app.include_router(internal_router)
app.include_router(mercury.router, prefix="/api/v1")
app.include_router(canvas.router, prefix="/api/v1")

logger.info("routes_loaded", router="all")
