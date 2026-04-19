from __future__ import annotations

import abc
import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Type

import structlog
from fastapi import FastAPI, APIRouter
from pydantic import BaseModel

from core.base_config import ButlerBaseConfig
from core.errors import Problem, problem_exception_handler
from core.health import create_health_router
from core.logging import setup_logging
from core.middleware import RequestContextMiddleware
from core.idempotency import IdempotencyMiddleware

logger = structlog.get_logger(__name__)

class ButlerBaseService(abc.ABC):
    """
    Abstract Base Service for all Butler system components (v3.0).
    
    Provides:
    - Standardized FastAPI app initialization.
    - Template methods for startup/shutdown hooks.
    - Unified Admin and Health surfaces.
    - Strict configuration enforcement.
    """

    def __init__(self, config: ButlerBaseConfig):
        self.config = config
        self.app = self._init_app()
        self._admin_router = APIRouter(prefix="/admin", tags=["admin"])
        self._setup_admin_routes()

    def _init_app(self) -> FastAPI:
        """Initialize and configure the FastAPI application."""
        app = FastAPI(
            title=f"Butler {self.config.SERVICE_NAME.title()}",
            version=self.config.VERSION,
            lifespan=self._lifespan_context,
            docs_url="/docs" if self.config.ENVIRONMENT == "development" else None,
        )

        # Standard Middleware Layer
        app.add_middleware(RequestContextMiddleware)
        app.add_middleware(IdempotencyMiddleware)

        # Standard Error Handlers
        app.add_exception_handler(Problem, problem_exception_handler)

        return app

    @asynccontextmanager
    async def _lifespan_context(self, app: FastAPI):
        """Lifecycle management using the asynccontextmanager pattern."""
        # ── Startup Phase ────────────────────────────────────────────────
        setup_logging(self.config.SERVICE_NAME, self.config.ENVIRONMENT)
        logger.info("service_base_starting", 
                    service=self.config.SERVICE_NAME, 
                    env=self.config.ENVIRONMENT)

        try:
            await self.on_startup()
            logger.info("service_base_ready")
            yield
        finally:
            # ── Shutdown Phase ───────────────────────────────────────────
            logger.info("service_base_shutting_down")
            await asyncio.wait_for(
                self.on_shutdown(), 
                timeout=self.config.SHUTDOWN_TIMEOUT_S
            )
            logger.info("service_base_stopped")

    def _setup_admin_routes(self):
        """Register the standard administrative endpoints."""
        
        @self._admin_router.get("/health/live")
        async def live_probe():
            return {"status": "up"}

        @self._admin_router.get("/server_info")
        async def get_server_info():
            """Twitter-Server standard: Build and environment info."""
            return {
                "service": self.config.SERVICE_NAME,
                "environment": self.config.ENVIRONMENT,
                "version": self.config.VERSION,
                "uptime_s": await self.get_uptime_s()
            }

        @self._admin_router.get("/threads")
        async def get_thread_dump():
            """Twitter-Server standard: Snapshot of active tasks."""
            import threading
            return {
                "active_tasks": len(asyncio.all_tasks()),
                "thread_count": threading.active_count(),
                "threads": [t.name for t in threading.enumerate()]
            }

        @self._admin_router.get("/flags")
        async def get_flags():
            return await self.get_runtime_flags()

        self.app.include_router(self._admin_router)
        
        # Standard Health (Live/Ready/Startup)
        health_router = create_health_router(deps=self.get_health_dependencies())
        self.app.include_router(health_router, prefix="/health")

    # -- Template Methods (To be overridden by subclasses) --

    @abc.abstractmethod
    async def on_startup(self) -> None:
        """Logic to run during service start (e.g. DB connection)."""
        pass

    @abc.abstractmethod
    async def on_shutdown(self) -> None:
        """Logic to run during service shutdown (e.g. closing pools)."""
        pass

    def get_health_dependencies(self) -> Dict[str, Any]:
        """Return dict of health check callables for the health router."""
        return {}

    async def get_runtime_flags(self) -> Dict[str, Any]:
        """Return the current state of dynamic service flags."""
        return {"service_mode": "default"}

    async def get_uptime_s(self) -> float:
        """Return service uptime in seconds."""
        # This will be initialized in on_startup by subclasses if needed
        return 0.0

    def include_router(self, router: APIRouter, **kwargs):
        """Convenience wrapper for standard route inclusion."""
        self.app.include_router(router, **kwargs)
