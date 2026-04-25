from __future__ import annotations

import abc
import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import APIRouter, FastAPI
from starlette.responses import JSONResponse

from core.base_config import ButlerBaseConfig
from core.errors import Problem, problem_exception_handler
from core.health import create_health_router
from core.idempotency import IdempotencyMiddleware
from core.logging import setup_logging
from core.middleware import RequestContextMiddleware
from core.observability import ObservabilityMiddleware, get_metrics

logger = structlog.get_logger(__name__)


class ButlerBaseService(abc.ABC):
    """Production-grade base service runtime for Butler services.

    Responsibilities:
    - standardized FastAPI app construction
    - unified lifespan management
    - admin and health surfaces
    - request middleware registration
    - readiness / liveness state tracking
    - startup and shutdown timing
    """

    def __init__(self, config: ButlerBaseConfig) -> None:
        self.config = config
        self._started_at_monotonic: float | None = None
        self._startup_completed_at: float | None = None
        self._state: str = "created"  # created | starting | ready | stopping | stopped | failed
        self._startup_error: str | None = None

        self.app = self._init_app()
        self._admin_router = APIRouter(prefix="/admin", tags=["admin"])
        self._setup_admin_routes()

    def _init_app(self) -> FastAPI:
        app = FastAPI(
            title=f"Butler {self.config.SERVICE_NAME.title()}",
            version=self.config.VERSION,
            lifespan=self._lifespan_context,
            docs_url="/docs" if self.config.ENVIRONMENT == "development" else None,
            redoc_url="/redoc" if self.config.ENVIRONMENT == "development" else None,
        )

        # Exception handlers
        app.add_exception_handler(Problem, problem_exception_handler)

        # Middleware order matters.
        # Request context should be early.
        app.add_middleware(RequestContextMiddleware)

        # Observability should wrap application execution broadly.
        app.add_middleware(ObservabilityMiddleware)

        # Idempotency should apply to mutation endpoints after request context exists.
        app.add_middleware(IdempotencyMiddleware)

        return app

    @asynccontextmanager
    async def _lifespan_context(self, app: FastAPI):
        del app

        setup_logging(self.config.SERVICE_NAME, self.config.ENVIRONMENT)
        self._started_at_monotonic = time.monotonic()
        self._state = "starting"
        self._startup_error = None

        logger.info(
            "service_starting",
            service=self.config.SERVICE_NAME,
            environment=self.config.ENVIRONMENT,
            version=self.config.VERSION,
        )

        startup_started = time.monotonic()

        try:
            await self.on_startup()
            self._startup_completed_at = time.monotonic()
            self._state = "ready"

            logger.info(
                "service_ready",
                service=self.config.SERVICE_NAME,
                startup_duration_ms=round((self._startup_completed_at - startup_started) * 1000, 2),
            )

            yield

        except Exception as exc:
            self._state = "failed"
            self._startup_error = f"{type(exc).__name__}: {exc}"

            logger.exception(
                "service_startup_failed",
                service=self.config.SERVICE_NAME,
                error=self._startup_error,
            )
            raise

        finally:
            shutdown_started = time.monotonic()
            self._state = "stopping"

            logger.info(
                "service_stopping",
                service=self.config.SERVICE_NAME,
            )

            try:
                await asyncio.wait_for(
                    self.on_shutdown(),
                    timeout=self.config.SHUTDOWN_TIMEOUT_S,
                )
            except TimeoutError:
                logger.error(
                    "service_shutdown_timed_out",
                    service=self.config.SERVICE_NAME,
                    timeout_s=self.config.SHUTDOWN_TIMEOUT_S,
                )
            except Exception:
                logger.exception(
                    "service_shutdown_failed",
                    service=self.config.SERVICE_NAME,
                )
            finally:
                self._state = "stopped"
                logger.info(
                    "service_stopped",
                    service=self.config.SERVICE_NAME,
                    shutdown_duration_ms=round((time.monotonic() - shutdown_started) * 1000, 2),
                )

    def _setup_admin_routes(self) -> None:
        @self._admin_router.get("/health/live")
        async def live_probe() -> dict[str, str]:
            return {"status": "up"}

        @self._admin_router.get("/server_info")
        async def get_server_info() -> dict[str, Any]:
            return {
                "service": self.config.SERVICE_NAME,
                "environment": self.config.ENVIRONMENT,
                "version": self.config.VERSION,
                "state": self._state,
                "uptime_s": await self.get_uptime_s(),
                "startup_error": self._startup_error,
            }

        @self._admin_router.get("/ready_state")
        async def get_ready_state() -> JSONResponse:
            status_code = 200 if self._state == "ready" else 503
            return JSONResponse(
                status_code=status_code,
                content={
                    "service": self.config.SERVICE_NAME,
                    "state": self._state,
                    "startup_error": self._startup_error,
                },
            )

        @self._admin_router.get("/threads")
        async def get_thread_dump() -> dict[str, Any]:
            import threading

            return {
                "active_tasks": len(asyncio.all_tasks()),
                "thread_count": threading.active_count(),
                "threads": [thread.name for thread in threading.enumerate()],
            }

        @self._admin_router.get("/flags")
        async def get_flags() -> dict[str, Any]:
            return await self.get_runtime_flags()

        @self._admin_router.get("/metrics_summary")
        async def get_metrics_summary() -> dict[str, Any]:
            metrics = get_metrics()
            return {
                "metrics_available": metrics.is_available,
                "gateway": metrics.get_gateway_snapshot() if metrics.is_available else {},
            }

        self.app.include_router(self._admin_router)

        health_router = create_health_router(deps=self.get_health_dependencies())
        self.app.include_router(health_router, prefix="/health")

    @abc.abstractmethod
    async def on_startup(self) -> None:
        """Run service-specific startup logic."""

    @abc.abstractmethod
    async def on_shutdown(self) -> None:
        """Run service-specific shutdown logic."""

    def get_health_dependencies(self) -> dict[str, Any]:
        return {}

    async def get_runtime_flags(self) -> dict[str, Any]:
        return {"service_mode": "default"}

    async def get_uptime_s(self) -> float:
        if self._started_at_monotonic is None:
            return 0.0
        return round(time.monotonic() - self._started_at_monotonic, 3)

    def is_ready(self) -> bool:
        return self._state == "ready"

    def include_router(self, router: APIRouter, **kwargs: Any) -> None:
        self.app.include_router(router, **kwargs)
