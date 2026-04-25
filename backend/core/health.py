"""Butler Health Probes.

Four-state health model:
- STARTING
- HEALTHY
- DEGRADED
- UNHEALTHY

Probe semantics:
- /health/live: process is alive
- /health/ready: instance can serve traffic
- /health/startup: instance has completed startup successfully

Design goals:
- framework-thin router
- explicit state computation
- policy-driven critical dependency handling
- circuit breakers degrade readiness unless explicitly configured otherwise
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = structlog.get_logger(__name__)

DepChecker = Callable[[], Awaitable[None]]


class HealthState(StrEnum):
    STARTING = "starting"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


_STATE_HTTP_CODE: dict[HealthState, int] = {
    HealthState.STARTING: 200,
    HealthState.HEALTHY: 200,
    HealthState.DEGRADED: 200,
    HealthState.UNHEALTHY: 503,
}


class HealthHTTPResult(dict[str, Any]):
    """Dictionary health body that also unpacks as ``(body, status_code)``."""

    def __init__(self, body: dict[str, Any], status_code: int) -> None:
        super().__init__(body)
        self.status_code = status_code

    def __iter__(self) -> Iterator[dict[str, Any] | int]:
        yield dict(self)
        yield self.status_code


@dataclass(frozen=True, slots=True)
class BreakerSnapshot:
    name: str
    state: str
    critical: bool = False


@dataclass(frozen=True, slots=True)
class DependencyStatus:
    name: str
    healthy: bool
    detail: str | None = None
    critical: bool = False


@dataclass(slots=True)
class HealthEvaluation:
    dependency_checks: dict[str, str] = field(default_factory=dict)
    circuit_breakers: dict[str, str] = field(default_factory=dict)
    critical_failures: list[str] = field(default_factory=list)
    degraded_dependencies: list[str] = field(default_factory=list)
    open_breakers: list[str] = field(default_factory=list)

    def compute_state(self) -> HealthState:
        if self.critical_failures:
            return HealthState.UNHEALTHY
        if self.degraded_dependencies or self.open_breakers:
            return HealthState.DEGRADED
        return HealthState.HEALTHY

    def to_dict(self, *, status: str, version: str) -> dict[str, Any]:
        state = self.compute_state()
        return {
            "status": status,
            "state": state.value,
            "version": version,
            "ts": int(time.time()),
            "checks": self.dependency_checks,
            "circuit_breakers": self.circuit_breakers,
            "critical_failures": self.critical_failures,
            "degraded_dependencies": self.degraded_dependencies,
            "open_breakers": self.open_breakers,
        }


@dataclass(slots=True)
class HealthProbeResult:
    """Backward-compatible health result model used by phase tests."""

    dependency_results: dict[str, str] = field(default_factory=dict)
    breaker_results: dict[str, str] = field(default_factory=dict)
    critical_failures: list[str] = field(default_factory=list)
    non_critical_failures: list[str] = field(default_factory=list)
    has_open_breakers: bool = False

    def compute_state(self) -> HealthState:
        if self.critical_failures:
            return HealthState.UNHEALTHY
        if self.non_critical_failures or self.has_open_breakers:
            return HealthState.DEGRADED
        return HealthState.HEALTHY

    def to_dict(self, *, status_label: str = "ready", version: str = "dev") -> dict[str, Any]:
        return {
            "status": status_label,
            "state": self.compute_state().value,
            "version": version,
            "ts": int(time.time()),
            "checks": self.dependency_results,
            "circuit_breakers": self.breaker_results,
        }


class HealthChecker:
    """Policy-driven health checker."""

    def __init__(
        self,
        deps: dict[str, DepChecker] | None = None,
        *,
        circuit_breaker_registry: Any | None = None,
        critical_deps: set[str] | None = None,
        critical_breakers: set[str] | None = None,
        version: str = "dev",
    ) -> None:
        self._deps = deps or {}
        self._circuit_breaker_registry = circuit_breaker_registry
        self._critical_deps = critical_deps or {"database", "redis", "auth"}
        self._critical_breakers = critical_breakers or set()
        self._version = version
        self._startup_confirmed = False

    async def live(self) -> HealthHTTPResult:
        body = {
            "status": "ok",
            "state": HealthState.HEALTHY.value,
            "version": self._version,
            "ts": int(time.time()),
        }
        return HealthHTTPResult(body, 200)

    async def ready(self) -> tuple[dict[str, Any], int]:
        evaluation = await self._probe()
        state = evaluation.compute_state()

        if state is HealthState.UNHEALTHY:
            status = "not_ready"
            code = 503
        elif state is HealthState.DEGRADED:
            status = "degraded"
            code = 200
        else:
            status = "ready"
            code = 200

        body = evaluation.to_dict(status=status, version=self._version)
        logger.info("health_ready_checked", state=state.value, status_code=code)
        return body, code

    async def startup(self) -> tuple[dict[str, Any], int]:
        evaluation = await self._probe()
        state = evaluation.compute_state()

        if state is HealthState.HEALTHY:
            self._startup_confirmed = True

        if not self._startup_confirmed and state is not HealthState.UNHEALTHY:
            body = evaluation.to_dict(status="starting", version=self._version)
            body["state"] = HealthState.STARTING.value
            return body, 200

        if state is HealthState.UNHEALTHY:
            body = evaluation.to_dict(status="startup_failed", version=self._version)
            body["state"] = HealthState.UNHEALTHY.value
            return body, 503

        body = evaluation.to_dict(status="ready", version=self._version)
        body["state"] = HealthState.HEALTHY.value
        return body, 200

    async def _probe(self) -> HealthEvaluation:
        evaluation = HealthEvaluation()

        for name, checker in self._deps.items():
            try:
                await checker()
                evaluation.dependency_checks[name] = "healthy"
            except Exception as exc:
                detail = str(exc)
                evaluation.dependency_checks[name] = f"unhealthy: {detail}"
                if name in self._critical_deps:
                    evaluation.critical_failures.append(name)
                else:
                    evaluation.degraded_dependencies.append(name)

        if self._circuit_breaker_registry is not None:
            try:
                for stat in self._circuit_breaker_registry.all_stats():
                    name = stat.get("name", "unknown")
                    state = stat.get("state", "closed")
                    evaluation.circuit_breakers[name] = state

                    if state == "open":
                        if name in self._critical_breakers or name in self._critical_deps:
                            evaluation.critical_failures.append(name)
                        else:
                            evaluation.open_breakers.append(name)
            except Exception as exc:
                logger.warning("health_breaker_probe_failed", error=str(exc))

        evaluation.critical_failures = sorted(set(evaluation.critical_failures))
        evaluation.degraded_dependencies = sorted(set(evaluation.degraded_dependencies))
        evaluation.open_breakers = sorted(set(evaluation.open_breakers))

        return evaluation


def create_health_router(
    deps: dict[str, DepChecker] | None = None,
    prefix: str = "",
    *,
    include_in_schema: bool = True,
    circuit_breaker_registry: Any | None = None,
    critical_deps: set[str] | None = None,
    critical_breakers: set[str] | None = None,
    version: str = "dev",
) -> APIRouter:
    """Create health probe routes."""
    checker = HealthChecker(
        deps=deps,
        circuit_breaker_registry=circuit_breaker_registry,
        critical_deps=critical_deps,
        critical_breakers=critical_breakers,
        version=version,
    )

    router = APIRouter(prefix=prefix, tags=["health"])

    @router.get("/health/live", include_in_schema=include_in_schema, summary="Liveness probe")
    async def live() -> JSONResponse:
        body, code = await checker.live()
        return JSONResponse(content=body, status_code=code)

    @router.get("/health/ready", include_in_schema=include_in_schema, summary="Readiness probe")
    async def ready() -> JSONResponse:
        body, code = await checker.ready()
        return JSONResponse(content=body, status_code=code)

    @router.get("/health/startup", include_in_schema=include_in_schema, summary="Startup probe")
    async def startup() -> JSONResponse:
        body, code = await checker.startup()
        return JSONResponse(content=body, status_code=code)

    return router
