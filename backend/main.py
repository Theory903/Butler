"""Butler API — application assembly.

This file is ONLY responsible for wiring together:
 - Infrastructure (DB, Redis)
 - Middleware stack
 - Exception handlers
 - Route registration

No business logic lives here.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from core.errors import Problem, problem_exception_handler
from core.logging import setup_logging
from core.middleware import RequestContextMiddleware
from core.observability import setup_observability
from infrastructure.cache import close_redis, get_redis
from infrastructure.config import settings
from infrastructure.database import close_db, init_db
from infrastructure.memory.neo4j_client import neo4j_client
from infrastructure.memory.qdrant_client import qdrant_client
from fastapi.middleware.cors import CORSMiddleware

from core.idempotency import IdempotencyMiddleware
from core.deps import get_ml_runtime, get_orchestrator_service

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown hooks."""
    # ── Startup ──────────────────────────────────────────────────────
    setup_logging(settings.SERVICE_NAME, settings.ENVIRONMENT)

    logger.info("butler_starting", version=settings.SERVICE_VERSION, env=settings.ENVIRONMENT)

    await init_db()
    logger.info("database_connected")

    await get_redis()  # Warm up connection
    logger.info("redis_connected")

    # Optional: Warm up Neo4j and Qdrant if using them as backends
    if settings.KNOWLEDGE_STORE_BACKEND == "neo4j":
        await neo4j_client.connect()
        logger.info("neo4j_connected")
    
    if settings.VECTOR_STORE_BACKEND == "qdrant":
        await qdrant_client.connect()
        logger.info("qdrant_connected")

    # ── Service Warmup ──────────────────────────────────────────────
    # Initialize ML Runtime and warm up providers
    runtime = get_ml_runtime()
    await runtime.on_startup()
    logger.info("ml_runtime_warmed")

    logger.info("butler_ready")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("butler_shutting_down")
    await get_ml_runtime().on_shutdown()
    await close_redis()
    await close_db()
    await neo4j_client.close()
    await qdrant_client.close()
    logger.info("butler_stopped")


app = FastAPI(
    title="Butler API",
    description="Personal AI system — production backend",
    version=settings.SERVICE_VERSION,
    lifespan=lifespan,
    # Disable default /docs redirect in prod
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# ── Middleware stack (order matters — first in = outermost) ──────────────────

# InternalOnlyMiddleware MUST be added before CORS so /internal routes are
# rejected before any CORS pre-flight processing reveals route existence.
from api.routes.internal_control import InternalOnlyMiddleware  # noqa: E402
app.add_middleware(InternalOnlyMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(IdempotencyMiddleware)

# ── Observability ─────────────────────────────────────────────────────────────
setup_observability(app, settings.SERVICE_NAME, settings.OTEL_ENDPOINT)

# ── Exception handlers ────────────────────────────────────────────────────────

from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
from core.errors import http_exception_handler, validation_exception_handler

app.add_exception_handler(Problem, problem_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

# ── Routes — Phase 0: health only ────────────────────────────────────────────
# Additional routers are imported below as phases are implemented.

from core.health import create_health_router  # noqa: E402
from infrastructure.database import engine  # noqa: E402

from sqlalchemy import text  # noqa: E402


async def _check_db() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _check_redis() -> None:
    client = await get_redis()
    await client.ping()


app.include_router(
    create_health_router(deps={"database": _check_db, "redis": _check_redis}),
    prefix="/api/v1",
)

# ── OIDC / Identity Platform Well-Knowns ─────────────────────────────────────
@app.get("/.well-known/jwks.json", tags=["auth"])
async def jwks_discovery():
    from services.auth.jwt import get_jwks_manager
    return get_jwks_manager().get_jwks_document()

# ── Application Routes ────────────────────────────────────────────────────────
try:
    from api.routes import (
        admin, acp, auth, gateway, orchestrator, memory, tools, search, ml, realtime,
        communication, security, device, vision, audio, cron, voice_gateway,
        research, meetings
    )  # noqa: E402
    from api.routes.mcp import mcp_router  # noqa: E402
    from api.routes.internal_control import internal_router  # noqa: E402
    from integrations.hermes.skills.productivity.google_workspace import auth_flow as google_auth_flow
    
    # ── 6. Include API Routers (Standard Versioning) ─────────────────────────
    app.include_router(auth.router, prefix="/api/v1/auth")
    app.include_router(gateway.router, prefix="/api/v1")
    app.include_router(orchestrator.router, prefix="/api/v1")
    
    # System Routers (Admin/ACP/Cron) using factory functions
    from api.routes.admin import create_admin_router
    from api.routes.acp import create_acp_router
    from api.routes.cron import create_cron_router
    
    app.include_router(create_admin_router(), prefix="/api/v1")
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
    app.include_router(google_auth_flow.router, prefix="/api/v1")
    # Phase 4: MCP Streamable HTTP transport
    app.include_router(mcp_router, prefix="/api/v1")
    # Phase 5: Internal control ingress (machine-only, protected by InternalOnlyMiddleware)
    app.include_router(internal_router)
    logger.info("routes_loaded", router="all")
except ImportError as e:
    logger.warning("routes_not_ready", router="api", error=str(e))