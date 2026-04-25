"""Phase 6 — Circuit Breaker and Admin Plane tests.

Tests ButlerCircuitBreaker (state machine transitions, failure counting,
rolling window, probe recovery, guard() context manager) and
AdminPlane HTTP endpoints (circuit-breakers, services/status,
kill-switch, drain, memory/stats, routing/decision, audit/recent).

All fully isolated — no real Redis, no real FastAPI server.
Admin endpoints tested via FastAPI TestClient.

Verifies:
  1. CircuitBreaker CLOSED: allows requests freely
  2. CircuitBreaker CLOSED → OPEN: threshold failures within window
  3. CircuitBreaker OPEN: rejects requests (allow_request=False)
  4. CircuitBreaker OPEN → HALF_OPEN: after recovery_s elapsed
  5. CircuitBreaker HALF_OPEN → CLOSED: successful probe
  6. CircuitBreaker HALF_OPEN → OPEN: failed probe
  7. CircuitBreaker rolling window: old failures pruned before threshold
  8. CircuitBreaker reset(): force back to CLOSED
  9. CircuitBreaker stats(): correct snapshot
  10. CircuitBreakerRegistry: register + get + all_stats + any_open
  11. CircuitBreakerRegistry: reset_all returns count
  12. AdminPlane GET /admin/circuit-breakers: lists all breakers
  13. AdminPlane POST /admin/circuit-breakers/reset: resets all
  14. AdminPlane GET /admin/services/status: lists services + draining
  15. AdminPlane POST /admin/kill-switch/{service}: sets kill flag
  16. AdminPlane POST /admin/drain: sets draining=True
  17. AdminPlane DELETE /admin/drain: cancels drain
  18. AdminPlane GET /admin/memory/stats: cold store stats included
  19. AdminPlane POST /admin/routing/decision: correct tier returned
  20. AdminPlane GET /admin/audit/recent: returns entries from Redis
"""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.admin import _kill_switches, create_admin_router
from core.circuit_breaker import (
    ButlerCircuitBreaker,
    CircuitBreakerRegistry,
    CircuitOpenError,
    CircuitState,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_breaker(
    name="test",
    threshold=3,
    window_s=60.0,
    recovery_s=5.0,
) -> ButlerCircuitBreaker:
    return ButlerCircuitBreaker(
        name=name,
        threshold=threshold,
        window_s=window_s,
        recovery_s=recovery_s,
    )


def _make_registry() -> CircuitBreakerRegistry:
    reg = CircuitBreakerRegistry()
    reg.register("redis", threshold=3, window_s=30, recovery_s=5)
    reg.register("postgres", threshold=3, window_s=30, recovery_s=5)
    return reg


def _make_app(registry=None, cold_store=None, smart_router=None, audit_redis=None) -> FastAPI:
    app = FastAPI()
    router = create_admin_router(
        registry=registry or _make_registry(),
        cold_store=cold_store,
        smart_router=smart_router,
        audit_redis=audit_redis,
    )
    app.include_router(router)
    return app


# ─────────────────────────────────────────────────────────────────────────────
# Test 20: ButlerCircuitBreaker state machine
# ─────────────────────────────────────────────────────────────────────────────


class TestCircuitBreaker:
    def test_initial_state_is_closed(self):
        breaker = _make_breaker()
        assert breaker.state == CircuitState.CLOSED

    def test_allows_request_when_closed(self):
        breaker = _make_breaker()
        assert breaker.allow_request() is True

    def test_closed_to_open_on_threshold(self):
        """threshold failures → OPEN."""
        breaker = _make_breaker(threshold=3)
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

    def test_below_threshold_stays_closed(self):
        """Below threshold → stays CLOSED."""
        breaker = _make_breaker(threshold=5)
        for _ in range(4):
            breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED

    def test_open_rejects_requests(self):
        """OPEN circuit rejects all requests."""
        breaker = _make_breaker(threshold=1)
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        assert breaker.allow_request() is False

    def test_open_to_half_open_after_recovery(self):
        """After recovery_s, OPEN transitions to HALF_OPEN."""
        breaker = _make_breaker(threshold=1, recovery_s=0.05)
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        time.sleep(0.1)  # wait for recovery window
        assert breaker.state == CircuitState.HALF_OPEN
        assert breaker.allow_request() is True

    def test_half_open_to_closed_on_success(self):
        """Successful probe in HALF_OPEN → CLOSED."""
        breaker = _make_breaker(threshold=1, recovery_s=0.05)
        breaker.record_failure()
        time.sleep(0.1)
        assert breaker.state == CircuitState.HALF_OPEN
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self):
        """Failed probe in HALF_OPEN → back to OPEN."""
        breaker = _make_breaker(threshold=1, recovery_s=0.05)
        breaker.record_failure()
        time.sleep(0.1)
        assert breaker.state == CircuitState.HALF_OPEN
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

    def test_rolling_window_prunes_old_failures(self):
        """Failures older than window_s are pruned before threshold check."""
        breaker = _make_breaker(threshold=3, window_s=0.1)
        # Record 2 failures
        breaker.record_failure()
        breaker.record_failure()
        # Wait for window to expire
        time.sleep(0.15)
        # Record 1 more — old failures pruned, so total = 1 (below threshold)
        breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED
        assert len(breaker._failures) == 1

    def test_reset_returns_to_closed(self):
        """reset() forces CLOSED regardless of current state."""
        breaker = _make_breaker(threshold=1)
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.allow_request() is True

    def test_stats_snapshot(self):
        """stats() returns a CircuitStats with correct values."""
        breaker = _make_breaker(threshold=5, window_s=60, recovery_s=30)
        breaker.record_failure()
        breaker.record_success()
        s = breaker.stats()
        assert s.name == "test"
        assert s.state == CircuitState.CLOSED
        assert s.failure_count == 1
        assert s.success_count == 1
        assert s.threshold == 5

    def test_circuit_open_error_raised_on_guard(self):
        """guard() raises CircuitOpenError when circuit is OPEN."""
        breaker = _make_breaker(threshold=1)
        breaker.record_failure()

        async def _call():
            pass

        async def _run():
            async with breaker.guard(_call):
                pass

        with pytest.raises(CircuitOpenError):
            asyncio.run(_run())

    def test_guard_records_success_on_clean_call(self):
        """guard() records success when call completes without infrastructure error."""
        breaker = _make_breaker()

        async def _call():
            return "ok"

        async def _run():
            async with breaker.guard(_call):
                pass

        asyncio.run(_run())
        assert breaker._success_count == 1

    def test_guard_records_failure_on_connection_error(self):
        """guard() records failure and re-raises on ConnectionError."""
        breaker = _make_breaker(threshold=5)

        async def _failing_call():
            raise ConnectionError("network down")

        async def _run():
            async with breaker.guard(_failing_call):
                pass

        with pytest.raises(ConnectionError):
            asyncio.run(_run())
        assert len(breaker._failures) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Test 21: CircuitBreakerRegistry
# ─────────────────────────────────────────────────────────────────────────────


class TestCircuitBreakerRegistry:
    def test_register_and_get(self):
        reg = CircuitBreakerRegistry()
        b = reg.register("mydb", threshold=3)
        assert reg.get("mydb") is b

    def test_register_idempotent(self):
        reg = CircuitBreakerRegistry()
        b1 = reg.register("svc", threshold=3)
        b2 = reg.register("svc", threshold=10)  # second call — same object
        assert b1 is b2

    def test_all_stats_returns_list(self):
        reg = _make_registry()
        stats = reg.all_stats()
        assert isinstance(stats, list)
        assert len(stats) == 2
        names = {s["name"] for s in stats}
        assert "redis" in names and "postgres" in names

    def test_any_open_false_when_all_closed(self):
        reg = _make_registry()
        assert reg.any_open() is False

    def test_any_open_true_when_one_open(self):
        reg = _make_registry()
        b = reg.get("redis")
        for _ in range(3):
            b.record_failure()
        assert reg.any_open() is True

    def test_reset_all_returns_count(self):
        reg = _make_registry()
        count = reg.reset_all()
        assert count == 2

    def test_reset_all_closes_open_breakers(self):
        reg = _make_registry()
        b = reg.get("postgres")
        for _ in range(3):
            b.record_failure()
        assert reg.any_open() is True
        reg.reset_all()
        assert reg.any_open() is False


# ─────────────────────────────────────────────────────────────────────────────
# Test 22: AdminPlane HTTP endpoints
# ─────────────────────────────────────────────────────────────────────────────


class TestAdminPlane:
    def _client(self, **kwargs) -> TestClient:
        app = _make_app(**kwargs)
        return TestClient(app)

    def test_list_circuit_breakers(self):
        client = self._client()
        resp = client.get("/admin/circuit-breakers")
        assert resp.status_code == 200
        data = resp.json()
        assert "circuit_breakers" in data
        assert "any_open" in data
        assert data["total"] == 2

    def test_reset_circuit_breakers(self):
        reg = _make_registry()
        b = reg.get("redis")
        for _ in range(3):
            b.record_failure()
        assert reg.any_open() is True
        client = self._client(registry=reg)
        resp = client.post("/admin/circuit-breakers/reset")
        assert resp.status_code == 200
        assert resp.json()["reset"] == 2
        assert reg.any_open() is False

    def test_services_status(self):
        client = self._client()
        resp = client.get("/admin/services/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "services" in data
        assert "draining" in data
        assert "gateway" in data["services"]
        assert "orchestrator" in data["services"]

    def test_kill_switch_enable(self):
        reg = _make_registry()
        # Clear any previous state
        _kill_switches.clear()
        client = self._client(registry=reg)
        resp = client.post("/admin/kill-switch/ml", json={"enabled": True, "reason": "test kill"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "ml"
        assert data["killed"] is True

    def test_kill_switch_disable(self):
        _kill_switches.clear()
        client = self._client()
        client.post("/admin/kill-switch/ml", json={"enabled": True})
        resp = client.post("/admin/kill-switch/ml", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["killed"] is False

    def test_drain_enable(self):
        import api.routes.admin as admin_mod

        admin_mod._draining = False
        client = self._client()
        resp = client.post("/admin/drain", json={"timeout_s": 60, "reason": "deploy"})
        assert resp.status_code == 200
        assert resp.json()["draining"] is True

    def test_drain_cancel(self):
        import api.routes.admin as admin_mod

        admin_mod._draining = True
        client = self._client()
        resp = client.request("DELETE", "/admin/drain")
        assert resp.status_code == 200
        assert resp.json()["draining"] is False

    def test_memory_stats_with_cold_store(self):
        cold = MagicMock()
        cold.stats.return_value = {"size": 42, "dim": 1536, "has_turboquant": False}
        client = self._client(cold_store=cold)
        resp = client.get("/admin/memory/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cold_store"]["size"] == 42

    def test_memory_stats_without_cold_store(self):
        client = self._client(cold_store=None)
        resp = client.get("/admin/memory/stats")
        assert resp.status_code == 200
        assert resp.json()["cold_store"] == {}

    def test_routing_dry_run(self):
        from services.ml.runtime import MLRuntimeManager
        from services.ml.smart_router import ButlerSmartRouter

        router = ButlerSmartRouter(runtime=MLRuntimeManager())
        client = self._client(smart_router=router)
        resp = client.post(
            "/admin/routing/decision",
            json={
                "message": "remind me to call Alice tomorrow",
                "intent_label": "reminder",
                "intent_confidence": 0.78,
                "complexity": "tool_action",
                "requires_tools": True,
                "context_token_count": 200,
                "latency_budget_ms": 1500,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "tier" in data
        assert "provider" in data
        assert "reason" in data

    def test_routing_dry_run_without_router(self):
        client = self._client(smart_router=None)
        resp = client.post(
            "/admin/routing/decision",
            json={
                "message": "test",
            },
        )
        assert resp.status_code == 200
        assert "error" in resp.json()

    def test_audit_recent_with_redis(self):
        redis = AsyncMock()
        entry = json.dumps({"action": "tool_call", "tool": "search", "ts": "2026-04-18"}).encode()
        redis.lrange = AsyncMock(return_value=[entry])
        client = self._client(audit_redis=redis)
        resp = client.get("/admin/audit/recent?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["entries"][0]["action"] == "tool_call"

    def test_audit_recent_without_redis(self):
        client = self._client(audit_redis=None)
        resp = client.get("/admin/audit/recent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries"] == []
        assert "note" in data
