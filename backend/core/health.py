"""Butler Health Probes — Phase 10.

Extends the Phase 0 HealthChecker with circuit breaker integration,
proper HTTP status codes, and the four-state machine.

State machine (per docs/rules/SYSTEM_RULES.md v2.0):
  STARTING   → in lifespan startup, startup probe returns 200
  HEALTHY    → all deps passing, no open circuit breakers → 200
  DEGRADED   → some deps failing OR some breakers open → 200 (still serving)
  UNHEALTHY  → all critical deps failing OR kill-switch active → 503

HTTP status codes per Kubernetes probe semantics:
  /health/live    → 200 always (if process is running)
  /health/ready   → 200 HEALTHY/DEGRADED, 503 UNHEALTHY
  /health/startup → 200 STARTING/HEALTHY, 503 UNHEALTHY

Circuit breaker integration:
  CircuitBreakerRegistry is injected at router creation time.
  Open breakers map to DEGRADED (not UNHEALTHY) unless marked critical.
  Critical services: database, redis, auth.
  Non-critical services: ml, search, realtime, tools.

v2.0 additional fields (per SYSTEM_RULES.md §health):
  - version: SERVICE_VERSION
  - ts: epoch timestamp
  - circuit_breakers: per-service state dict
  - critical_failures: list of critical services that are down
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Awaitable, Callable

import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = structlog.get_logger(__name__)

# ── State model ────────────────────────────────────────────────────────────────

class HealthState(str, Enum):
    STARTING   = "starting"
    HEALTHY    = "healthy"
    DEGRADED   = "degraded"
    UNHEALTHY  = "unhealthy"


_STATE_HTTP_CODE: dict[HealthState, int] = {
    HealthState.STARTING:  200,
    HealthState.HEALTHY:   200,
    HealthState.DEGRADED:  200,   # Still serving — degraded, not dead
    HealthState.UNHEALTHY: 503,
}

# These dep names trigger UNHEALTHY (not just DEGRADED) on failure
_CRITICAL_DEPS = {"database", "redis", "auth"}

DepChecker = Callable[[], Awaitable[None]]


# ── HealthProbeResult ──────────────────────────────────────────────────────────

class HealthProbeResult:
    """Aggregated result of a health check pass."""

    def __init__(self) -> None:
        self.dep_results:      dict[str, str] = {}
        self.breaker_results:  dict[str, str] = {}
        self.critical_failures: list[str] = []
        self.non_critical_failures: list[str] = []
        self.has_open_breakers: bool = False

    def compute_state(self) -> HealthState:
        if self.critical_failures:
            return HealthState.UNHEALTHY
        if self.non_critical_failures or self.has_open_breakers:
            return HealthState.DEGRADED
        return HealthState.HEALTHY

    def to_dict(self, *, status_label: str, version: str = "dev") -> dict:
        state = self.compute_state()
        return {
            "status": status_label,
            "state": state.value,
            "version": version,
            "ts": int(time.time()),
            "checks": self.dep_results,
            "circuit_breakers": self.breaker_results,
            "critical_failures": self.critical_failures,
        }


# ── HealthChecker ──────────────────────────────────────────────────────────────

class HealthChecker:
    """Four-state health checker with circuit breaker integration.

    Replaces the Phase 0 stub. Backward-compatible: still accepts the same
    `deps` dict used in main.py.

    New in Phase 10:
      - circuit_breaker_registry: injected from CircuitBreakerRegistry
      - critical_deps: set of dep names whose failure → UNHEALTHY
      - HTTP 503 when state == UNHEALTHY
      - Returns HealthProbeResult for programmatic use by tests
    """

    def __init__(
        self,
        deps: dict[str, DepChecker] | None = None,
        circuit_breaker_registry=None,  # CircuitBreakerRegistry | None
        critical_deps: set[str] | None = None,
        version: str = "dev",
    ) -> None:
        self._deps      = deps or {}
        self._cbr       = circuit_breaker_registry
        self._critical  = critical_deps or _CRITICAL_DEPS
        self._version   = version
        self._started   = False  # flips to True after first successful startup check

    async def _probe_deps(self) -> HealthProbeResult:
        result = HealthProbeResult()

        # Check dep callables
        for name, checker in self._deps.items():
            try:
                await checker()
                result.dep_results[name] = "healthy"
            except Exception as exc:
                result.dep_results[name] = f"unhealthy: {exc}"
                if name in self._critical:
                    result.critical_failures.append(name)
                else:
                    result.non_critical_failures.append(name)

        # Check circuit breakers
        if self._cbr is not None:
            try:
                for stat in self._cbr.all_stats():
                    svc   = stat.get("name", "unknown")
                    state = stat.get("state", "closed")
                    result.breaker_results[svc] = state
                    if state == "open":
                        result.has_open_breakers = True
                        if svc in self._critical:
                            if svc not in result.critical_failures:
                                result.critical_failures.append(svc)
            except Exception as exc:
                logger.warning("health_circuit_breaker_check_failed", error=str(exc))

        return result

    # ── Live probe (L0: process alive, no deps) ────────────────────────────────

    async def live(self) -> dict:
        """Kubernetes liveness probe: is the process up?

        Never returns 503 — if this call returns at all, the process is alive.
        """
        return {
            "status": "ok",
            "state": HealthState.HEALTHY.value,
            "version": self._version,
            "ts": int(time.time()),
        }

    # ── Ready probe (L1: deps + breakers) ─────────────────────────────────────

    async def ready(self) -> tuple[dict, int]:
        """Kubernetes readiness probe: should traffic be sent here?

        Returns: (response_body, http_status_code)
          200 → HEALTHY or DEGRADED (still serving)
          503 → UNHEALTHY (stop sending traffic)
        """
        result = await self._probe_deps()
        state  = result.compute_state()

        if state == HealthState.UNHEALTHY:
            label = "not_ready"
        elif state == HealthState.DEGRADED:
            label = "degraded"
        else:
            label = "ready"

        body = result.to_dict(status_label=label, version=self._version)
        code = _STATE_HTTP_CODE[state]

        logger.info("health_ready_checked", state=state.value, code=code)
        return body, code

    # ── Startup probe (L2: initialisation complete) ────────────────────────────

    async def startup(self) -> tuple[dict, int]:
        """Kubernetes startup probe: has the service finished initialising?

        Before deps are fully up → STARTING (200 — give it more time).
        After first successful ready → HEALTHY (200).
        Critical dep missing → UNHEALTHY (503).
        """
        result = await self._probe_deps()
        state  = result.compute_state()

        if not self._started and state == HealthState.HEALTHY:
            self._started = True

        if not self._started and state != HealthState.UNHEALTHY:
            # Still starting — not yet confirmed ready
            startup_state = HealthState.STARTING
            label = "starting"
            code  = 200
        elif state == HealthState.UNHEALTHY:
            startup_state = HealthState.UNHEALTHY
            label = "startup_failed"
            code  = 503
        else:
            startup_state = HealthState.HEALTHY
            label = "ready"
            code  = 200

        body = result.to_dict(status_label=label, version=self._version)
        body["state"] = startup_state.value
        return body, code


# ── Router factory ─────────────────────────────────────────────────────────────

def create_health_router(
    deps: dict[str, DepChecker] | None = None,
    prefix: str = "",
    circuit_breaker_registry=None,
    critical_deps: set[str] | None = None,
    version: str = "dev",
) -> APIRouter:
    """Create /health/{live,ready,startup} routes.

    Phase 10: circuit_breaker_registry wired into ready + startup checks.
    Phase 0 signature (deps, prefix) is fully backward-compatible.

    Args:
        deps:                     Async dep checkers (database, redis, …)
        prefix:                   Route prefix (no prefix by default)
        circuit_breaker_registry: CircuitBreakerRegistry for breaker state
        critical_deps:            Override which dep names → UNHEALTHY
        version:                  SERVICE_VERSION string for response body
    """
    checker = HealthChecker(
        deps=deps,
        circuit_breaker_registry=circuit_breaker_registry,
        critical_deps=critical_deps,
        version=version,
    )
    router = APIRouter(prefix=prefix, tags=["health"])

    # ── GET /health/live ──────────────────────────────────────────────────────

    @router.get("/health/live", include_in_schema=True, summary="Liveness probe")
    async def live() -> JSONResponse:
        body = await checker.live()
        return JSONResponse(content=body, status_code=200)

    # ── GET /health/ready ─────────────────────────────────────────────────────

    @router.get("/health/ready", include_in_schema=True, summary="Readiness probe")
    async def ready() -> JSONResponse:
        body, code = await checker.ready()
        return JSONResponse(content=body, status_code=code)

    # ── GET /health/startup ───────────────────────────────────────────────────

    @router.get("/health/startup", include_in_schema=True, summary="Startup probe")
    async def startup() -> JSONResponse:
        body, code = await checker.startup()
        return JSONResponse(content=body, status_code=code)

    return router
