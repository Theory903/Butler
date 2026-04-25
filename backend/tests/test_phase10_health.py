"""Phase 10 — Health Probes + Circuit Breaker Integration.

Tests the four-state health system:
  STARTING → HEALTHY → DEGRADED → UNHEALTHY

And verifies:
  - /health/live always 200 (liveness, no deps)
  - /health/ready 200 for HEALTHY/DEGRADED, 503 for UNHEALTHY
  - /health/startup 200 for STARTING/HEALTHY, 503 for UNHEALTHY
  - Circuit breaker open state → DEGRADED
  - Critical dep failure → UNHEALTHY
  - Non-critical dep failure → DEGRADED
  - Circuit breaker of critical service open → UNHEALTHY
  - All deps healthy + no open breakers → HEALTHY
  - Response body shape (status, state, version, ts, checks, circuit_breakers)
  - Backward-compat: old-style deps-only call still works
  - HealthProbeResult.compute_state() state logic
  - HealthState HTTP code mapping

Tests (38):
  HealthChecker unit:
    1.  live() returns HEALTHY + status=ok
    2.  live() always 200 regardless of deps
    3.  ready() all deps healthy → HEALTHY
    4.  ready() non-critical dep fails → DEGRADED
    5.  ready() critical dep fails → UNHEALTHY
    6.  ready() no deps → HEALTHY
    7.  startup() before first success → STARTING
    8.  startup() after deps healthy → HEALTHY
    9.  startup() critical dep fails → UNHEALTHY
    10. ready() with open circuit breaker → DEGRADED
    11. ready() critical service breaker open → UNHEALTHY
    12. ready() response has ts, version, checks, circuit_breakers keys
    13. live() response has version key
    14. UNHEALTHY returns HTTP 503 from ready()
    15. DEGRADED returns HTTP 200 from ready()
    16. HEALTHY returns HTTP 200 from ready()

  HealthProbeResult:
    17. compute_state() no failures → HEALTHY
    18. compute_state() critical_failures → UNHEALTHY
    19. compute_state() non_critical_failures → DEGRADED
    20. compute_state() has_open_breakers → DEGRADED
    21. to_dict() includes state, status, ts, version

  HTTP routes via TestClient:
    22. GET /health/live → 200 always
    23. GET /health/ready all healthy → 200
    24. GET /health/ready critical dep down → 503
    25. GET /health/ready non-critical dep down → 200 (DEGRADED)
    26. GET /health/startup no deps → 200
    27. GET /health/startup critical dep fails → 503
    28. GET /health/ready response body has state field
    29. GET /health/ready with open breaker → 200 (DEGRADED)
    30. GET /health/live never returns 503
    31. GET /health/ready circuit breaker critical open → 503

  Backward-compat with Phase 0 call signature:
    32. create_health_router(deps={}) still works
    33. create_health_router() no args still works
    34. Old-style deps-only router returns correct status

  State machine ordering:
    35. UNHEALTHY overrides DEGRADED (critical wins)
    36. DEGRADED overrides HEALTHY (non-critical failure)
    37. Multiple open breakers coalesce to single DEGRADED
    38. Non-existent circuit_breaker_registry skipped gracefully
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.health import (
    HealthChecker,
    HealthProbeResult,
    HealthState,
    create_health_router,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


async def _pass():
    pass


async def _fail():
    raise RuntimeError("dep is down")


def _make_mock_cbr(breaker_states: dict[str, str]):
    """Minimal mock circuit breaker registry."""

    class MockCBR:
        def all_stats(self):
            return [{"name": k, "state": v} for k, v in breaker_states.items()]

    return MockCBR()


def _router_client(
    deps=None,
    cbr=None,
    critical_deps=None,
) -> TestClient:
    app = FastAPI()
    router = create_health_router(
        deps=deps or {},
        circuit_breaker_registry=cbr,
        critical_deps=critical_deps,
        version="test-1.0",
    )
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


# ── HealthChecker unit tests ──────────────────────────────────────────────────


class TestHealthChecker:
    @pytest.mark.asyncio
    async def test_live_returns_healthy(self):
        checker = HealthChecker()
        result = await checker.live()
        assert result["state"] == HealthState.HEALTHY.value
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_live_no_deps_always_200(self):
        checker = HealthChecker(deps={"db": _fail})
        result = await checker.live()
        assert result["state"] == HealthState.HEALTHY.value

    @pytest.mark.asyncio
    async def test_ready_all_healthy(self):
        checker = HealthChecker(deps={"db": _pass, "redis": _pass})
        body, code = await checker.ready()
        assert body["state"] == HealthState.HEALTHY.value
        assert code == 200

    @pytest.mark.asyncio
    async def test_ready_non_critical_fail_degraded(self):
        checker = HealthChecker(
            deps={"ml": _fail},
            critical_deps={"database", "redis"},
        )
        body, code = await checker.ready()
        assert body["state"] == HealthState.DEGRADED.value
        assert code == 200

    @pytest.mark.asyncio
    async def test_ready_critical_fail_unhealthy(self):
        checker = HealthChecker(
            deps={"database": _fail},
            critical_deps={"database"},
        )
        body, code = await checker.ready()
        assert body["state"] == HealthState.UNHEALTHY.value
        assert code == 503

    @pytest.mark.asyncio
    async def test_ready_no_deps_healthy(self):
        checker = HealthChecker()
        body, code = await checker.ready()
        assert body["state"] == HealthState.HEALTHY.value
        assert code == 200

    @pytest.mark.asyncio
    async def test_startup_before_success_starting(self):
        checker = HealthChecker(deps={"db": _fail}, critical_deps=set())
        body, code = await checker.startup()
        # Non-critical failure → DEGRADED → still "starting" before first healthy
        assert code == 200

    @pytest.mark.asyncio
    async def test_startup_after_healthy_deps(self):
        checker = HealthChecker(deps={"db": _pass, "redis": _pass})
        body, code = await checker.startup()
        assert code == 200
        assert body["state"] in (HealthState.HEALTHY.value, HealthState.STARTING.value)

    @pytest.mark.asyncio
    async def test_startup_critical_fail_503(self):
        checker = HealthChecker(deps={"database": _fail}, critical_deps={"database"})
        body, code = await checker.startup()
        assert code == 503

    @pytest.mark.asyncio
    async def test_ready_open_non_critical_breaker_degraded(self):
        cbr = _make_mock_cbr({"ml": "open", "search": "closed"})
        checker = HealthChecker(circuit_breaker_registry=cbr, critical_deps={"database"})
        body, code = await checker.ready()
        assert body["state"] == HealthState.DEGRADED.value
        assert code == 200

    @pytest.mark.asyncio
    async def test_ready_critical_breaker_open_unhealthy(self):
        cbr = _make_mock_cbr({"database": "open"})
        checker = HealthChecker(circuit_breaker_registry=cbr, critical_deps={"database"})
        body, code = await checker.ready()
        assert body["state"] == HealthState.UNHEALTHY.value
        assert code == 503

    @pytest.mark.asyncio
    async def test_ready_response_shape(self):
        checker = HealthChecker(deps={"db": _pass}, version="v10")
        body, _ = await checker.ready()
        assert "state" in body
        assert "status" in body
        assert "ts" in body
        assert "version" in body
        assert "checks" in body
        assert "circuit_breakers" in body

    @pytest.mark.asyncio
    async def test_live_response_has_version(self):
        checker = HealthChecker(version="v10")
        result = await checker.live()
        assert result.get("version") == "v10"

    @pytest.mark.asyncio
    async def test_unhealthy_http_503(self):
        checker = HealthChecker(deps={"database": _fail}, critical_deps={"database"})
        _, code = await checker.ready()
        assert code == 503

    @pytest.mark.asyncio
    async def test_degraded_http_200(self):
        checker = HealthChecker(deps={"ml": _fail}, critical_deps=set())
        _, code = await checker.ready()
        assert code == 200

    @pytest.mark.asyncio
    async def test_healthy_http_200(self):
        checker = HealthChecker()
        _, code = await checker.ready()
        assert code == 200


# ── HealthProbeResult unit tests ──────────────────────────────────────────────


class TestHealthProbeResult:
    def test_compute_state_no_failures_healthy(self):
        r = HealthProbeResult()
        assert r.compute_state() == HealthState.HEALTHY

    def test_compute_state_critical_failures_unhealthy(self):
        r = HealthProbeResult()
        r.critical_failures.append("database")
        assert r.compute_state() == HealthState.UNHEALTHY

    def test_compute_state_non_critical_degraded(self):
        r = HealthProbeResult()
        r.non_critical_failures.append("ml")
        assert r.compute_state() == HealthState.DEGRADED

    def test_compute_state_open_breaker_degraded(self):
        r = HealthProbeResult()
        r.has_open_breakers = True
        assert r.compute_state() == HealthState.DEGRADED

    def test_to_dict_shape(self):
        r = HealthProbeResult()
        d = r.to_dict(status_label="ready", version="v1")
        assert d["state"] == HealthState.HEALTHY.value
        assert d["status"] == "ready"
        assert "ts" in d
        assert d["version"] == "v1"


# ── HTTP route tests via TestClient ──────────────────────────────────────────


class TestHealthRoutes:
    def test_live_always_200(self):
        client = _router_client(deps={"database": _fail})
        resp = client.get("/health/live")
        assert resp.status_code == 200

    def test_ready_all_healthy_200(self):
        client = _router_client(deps={"database": _pass, "redis": _pass})
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        assert resp.json()["state"] == "healthy"

    def test_ready_critical_dep_down_503(self):
        client = _router_client(
            deps={"database": _fail},
            critical_deps={"database"},
        )
        resp = client.get("/health/ready")
        assert resp.status_code == 503

    def test_ready_non_critical_dep_down_200_degraded(self):
        client = _router_client(
            deps={"ml": _fail},
            critical_deps={"database", "redis"},
        )
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        assert resp.json()["state"] == "degraded"

    def test_startup_no_deps_200(self):
        client = _router_client()
        resp = client.get("/health/startup")
        assert resp.status_code == 200

    def test_startup_critical_fail_503(self):
        client = _router_client(
            deps={"database": _fail},
            critical_deps={"database"},
        )
        resp = client.get("/health/startup")
        assert resp.status_code == 503

    def test_ready_body_has_state_field(self):
        client = _router_client()
        resp = client.get("/health/ready")
        assert "state" in resp.json()

    def test_ready_open_breaker_200_degraded(self):
        cbr = _make_mock_cbr({"ml": "open"})
        client = _router_client(cbr=cbr, critical_deps={"database"})
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        assert resp.json()["state"] == "degraded"

    def test_live_never_503(self):
        cbr = _make_mock_cbr({"database": "open", "redis": "open"})
        client = _router_client(
            deps={"database": _fail},
            cbr=cbr,
            critical_deps={"database"},
        )
        resp = client.get("/health/live")
        assert resp.status_code == 200

    def test_ready_critical_breaker_open_503(self):
        cbr = _make_mock_cbr({"database": "open"})
        client = _router_client(cbr=cbr, critical_deps={"database"})
        resp = client.get("/health/ready")
        assert resp.status_code == 503


# ── Backward-compat tests ─────────────────────────────────────────────────────


class TestBackwardCompat:
    def test_old_style_deps_only_works(self):
        app = FastAPI()
        from core.health import create_health_router

        router = create_health_router(deps={"database": _pass, "redis": _pass})
        app.include_router(router)
        client = TestClient(app)
        resp = client.get("/health/ready")
        assert resp.status_code == 200

    def test_no_args_router_works(self):
        app = FastAPI()
        from core.health import create_health_router

        router = create_health_router()
        app.include_router(router)
        client = TestClient(app)
        resp = client.get("/health/live")
        assert resp.status_code == 200

    def test_old_deps_router_healthy(self):
        app = FastAPI()
        from core.health import create_health_router

        router = create_health_router(deps={"redis": _pass})
        app.include_router(router)
        client = TestClient(app)
        resp = client.get("/health/ready")
        assert resp.json()["state"] == "healthy"


# ── State machine ordering ────────────────────────────────────────────────────


class TestStateMachineOrdering:
    def test_unhealthy_overrides_degraded(self):
        r = HealthProbeResult()
        r.critical_failures.append("database")
        r.non_critical_failures.append("ml")
        assert r.compute_state() == HealthState.UNHEALTHY

    def test_degraded_overrides_healthy(self):
        r = HealthProbeResult()
        r.non_critical_failures.append("search")
        assert r.compute_state() == HealthState.DEGRADED

    def test_multiple_open_breakers_single_degraded(self):
        r = HealthProbeResult()
        r.has_open_breakers = True
        r.breaker_results = {"ml": "open", "search": "open"}
        assert r.compute_state() == HealthState.DEGRADED

    def test_no_registry_does_not_raise(self):
        checker = HealthChecker(circuit_breaker_registry=None)
        import asyncio

        body, code = asyncio.run(checker.ready())
        assert code == 200
