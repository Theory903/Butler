"""Phase 8b + Phase 9 — ACP routes, Cron routes, and Observability tests.

Tests ACP HTTP endpoints (list, get, decide, cancel, stats),
Cron HTTP endpoints (list, create, get, pause, resume, delete, history, validate),
and Observability layer (ButlerTracer, ButlerMetrics, ObservabilityMiddleware).

All tests use FastAPI TestClient — no real HTTP, no DB, no Redis.

ACP Routes:
  1.  GET /acp/requests returns empty list initially
  2.  GET /acp/requests/{id} returns 404 for unknown id
  3.  POST /acp/requests/{id}/decide returns 404 for unknown id
  4.  POST /acp/requests/{id}/cancel returns 404 for unknown id
  5.  Full flow: create → GET list → decide approved → GET confirms decided
  6.  Decide with invalid decision value returns 422
  7.  Decide approved on already-decided returns 409
  8.  Cancel a pending request transitions to cancelled
  9.  Cancel non-pending returns 409
  10. GET /acp/stats returns pending + total counts
  11. Cross-account: get returns 403

Cron Routes:
  12. GET /cron/jobs returns empty list initially
  13. POST /cron/jobs creates job with status=active
  14. POST /cron/jobs invalid cron returns 422
  15. POST /cron/jobs 50-job limit returns 429
  16. GET /cron/jobs/{id} returns job
  17. GET /cron/jobs/{id} unknown returns 404
  18. POST /cron/jobs/{id}/pause transitions to paused
  19. POST /cron/jobs/{id}/resume transitions back to active
  20. DELETE /cron/jobs/{id} removes job
  21. DELETE /cron/jobs/{id} unknown returns 404
  22. GET /cron/jobs/{id}/history returns run_count
  23. POST /cron/validate valid expression returns valid=True
  24. POST /cron/validate invalid expression returns valid=False (not 422)
  25. GET /cron/jobs?status=paused filters by status
  26. Cross-account: get returns 403

Observability:
  27. ButlerTracer.get() returns same singleton
  28. ButlerTracer.reset() forces new instance
  29. tracer.span() context manager yields without raising (no-op path)
  30. tracer.record_error() does not raise (no-op path)
  31. tracer.is_available is bool
  32. ButlerMetrics.get() returns same singleton
  33. ButlerMetrics.reset() forces new instance
  34. metrics.record_http_request() does not raise
  35. metrics.record_tool_call() does not raise
  36. metrics.record_llm_tokens() does not raise
  37. metrics.set_circuit_breaker_state() does not raise
  38. metrics.record_memory_write() does not raise
  39. metrics.set_cron_active() does not raise
  40. metrics.set_acp_pending() does not raise
  41. metrics.is_available is bool
  42. get_tracer() convenience accessor works
  43. get_metrics() convenience accessor works
  44. setup_observability() no-ops when endpoint=None (no raise)
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.acp import create_acp_router
from api.routes.cron import create_cron_router
from services.workflow.acp_server import ButlerACPServer, ACPDecision, ACPStatus
from services.cron.cron_service import ButlerCronService, CreateCronJobRequest


# ───────────────────────────────────────────────────────────────────────────────
# Fixtures
# ───────────────────────────────────────────────────────────────────────────────

def _acp_app(server: ButlerACPServer) -> TestClient:
    app = FastAPI()
    app.include_router(create_acp_router(acp_server=server))
    return TestClient(app, raise_server_exceptions=False)


def _cron_app(svc: ButlerCronService) -> TestClient:
    app = FastAPI()
    app.include_router(create_cron_router(cron_service=svc))
    return TestClient(app, raise_server_exceptions=False)


def _fresh_acp_server() -> ButlerACPServer:
    return ButlerACPServer()


def _fresh_cron_svc() -> ButlerCronService:
    return ButlerCronService()


def _seed_acp_request(server: ButlerACPServer, account_id: str = "demo") -> str:
    """Create an ACP request and return its request_id."""
    req = server.create(
        account_id=account_id,
        tool_name="send_email",
        approval_mode="explicit",
        risk_tier="L2",
        description="Test approval",
        task_id="t1",
        session_id="s1",
    )
    return req.request_id


def _seed_cron_job(svc: ButlerCronService, account_id: str = "demo") -> str:
    """Create a cron job and return its id."""
    job = svc.create(CreateCronJobRequest(
        account_id=account_id,
        name="test job",
        cron_expression="0 9 * * *",
        action="send_notification",
    ))
    return job.id


# ───────────────────────────────────────────────────────────────────────────────
# Phase 8b: ACP Routes
# ───────────────────────────────────────────────────────────────────────────────

class TestACPRoutes:

    def test_list_pending_empty(self):
        server = _fresh_acp_server()
        client = _acp_app(server)
        resp = client.get("/acp/requests?account_id=demo")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_get_unknown_request_returns_404(self):
        server = _fresh_acp_server()
        client = _acp_app(server)
        resp = client.get("/acp/requests/ghost_id?account_id=demo")
        assert resp.status_code == 404

    def test_decide_unknown_request_returns_404(self):
        server = _fresh_acp_server()
        client = _acp_app(server)
        resp = client.post(
            "/acp/requests/ghost_id/decide?account_id=demo",
            json={"decision": "approved", "human_id": "h1"},
        )
        assert resp.status_code == 404

    def test_cancel_unknown_request_returns_404(self):
        server = _fresh_acp_server()
        client = _acp_app(server)
        resp = client.post("/acp/requests/ghost_id/cancel?account_id=demo")
        assert resp.status_code == 404

    def test_full_flow_create_list_decide_confirm(self):
        server = _fresh_acp_server()
        client = _acp_app(server)
        rid = _seed_acp_request(server)

        # list shows pending
        resp = client.get("/acp/requests?account_id=demo")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

        # decide approved
        resp = client.post(
            f"/acp/requests/{rid}/decide?account_id=demo",
            json={"decision": "approved", "human_id": "human_42"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["decision"] == "approved"
        assert body["decided_by"] == "human_42"

        # list no longer has pending
        resp = client.get("/acp/requests?account_id=demo")
        assert resp.json()["count"] == 0

    def test_decide_invalid_value_returns_422(self):
        server = _fresh_acp_server()
        client = _acp_app(server)
        rid = _seed_acp_request(server)
        resp = client.post(
            f"/acp/requests/{rid}/decide?account_id=demo",
            json={"decision": "maybe", "human_id": "h1"},
        )
        assert resp.status_code == 422

    def test_decide_already_decided_returns_409(self):
        server = _fresh_acp_server()
        client = _acp_app(server)
        rid = _seed_acp_request(server)
        client.post(
            f"/acp/requests/{rid}/decide?account_id=demo",
            json={"decision": "approved", "human_id": "h1"},
        )
        resp = client.post(
            f"/acp/requests/{rid}/decide?account_id=demo",
            json={"decision": "approved", "human_id": "h1"},
        )
        assert resp.status_code == 409

    def test_cancel_pending_request(self):
        server = _fresh_acp_server()
        client = _acp_app(server)
        rid = _seed_acp_request(server)
        resp = client.post(f"/acp/requests/{rid}/cancel?account_id=demo")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_cancel_non_pending_returns_409(self):
        server = _fresh_acp_server()
        client = _acp_app(server)
        rid = _seed_acp_request(server)
        server.decide(rid, ACPDecision.APPROVED, human_id="h1")
        resp = client.post(f"/acp/requests/{rid}/cancel?account_id=demo")
        assert resp.status_code == 409

    def test_stats_endpoint(self):
        server = _fresh_acp_server()
        client = _acp_app(server)
        _seed_acp_request(server)
        resp = client.get("/acp/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["pending"] == 1
        assert body["total"] == 1

    def test_get_cross_account_returns_403(self):
        server = _fresh_acp_server()
        client = _acp_app(server)
        rid = _seed_acp_request(server, account_id="acc_owner")
        resp = client.get(f"/acp/requests/{rid}?account_id=acc_other")
        assert resp.status_code == 403

    def test_list_all_returns_all_statuses(self):
        server = _fresh_acp_server()
        client = _acp_app(server)
        rid = _seed_acp_request(server)
        server.decide(rid, ACPDecision.DENIED, human_id="h1")
        resp = client.get("/acp/requests/all?account_id=demo")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1


# ───────────────────────────────────────────────────────────────────────────────
# Phase 8b: Cron Routes
# ───────────────────────────────────────────────────────────────────────────────

class TestCronRoutes:

    def test_list_jobs_empty(self):
        svc = _fresh_cron_svc()
        client = _cron_app(svc)
        resp = client.get("/cron/jobs?account_id=demo")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_create_job_success(self):
        svc = _fresh_cron_svc()
        client = _cron_app(svc)
        resp = client.post(
            "/cron/jobs?account_id=demo",
            json={"name": "Morning", "cron_expression": "0 9 * * *", "action": "notify"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "active"
        assert body["account_id"] == "demo"
        assert body["cron_expression"] == "0 9 * * *"

    def test_create_job_invalid_cron_returns_422(self):
        svc = _fresh_cron_svc()
        client = _cron_app(svc)
        resp = client.post(
            "/cron/jobs?account_id=demo",
            json={"name": "Bad", "cron_expression": "not a cron", "action": "noop"},
        )
        assert resp.status_code == 422
        assert "invalid-cron-expression" in resp.json()["detail"]["type"]

    def test_create_job_limit_exceeded_returns_429(self):
        svc = _fresh_cron_svc()
        client = _cron_app(svc)
        # Pre-fill 50 jobs directly via service
        for i in range(50):
            svc.create(CreateCronJobRequest(
                account_id="demo", name=f"j{i}",
                cron_expression="0 9 * * *", action="noop",
            ))
        resp = client.post(
            "/cron/jobs?account_id=demo",
            json={"name": "Over", "cron_expression": "0 9 * * *", "action": "noop"},
        )
        assert resp.status_code == 429

    def test_get_job(self):
        svc = _fresh_cron_svc()
        client = _cron_app(svc)
        job_id = _seed_cron_job(svc)
        resp = client.get(f"/cron/jobs/{job_id}?account_id=demo")
        assert resp.status_code == 200
        assert resp.json()["id"] == job_id

    def test_get_job_unknown_returns_404(self):
        svc = _fresh_cron_svc()
        client = _cron_app(svc)
        resp = client.get("/cron/jobs/ghost?account_id=demo")
        assert resp.status_code == 404

    def test_pause_job(self):
        svc = _fresh_cron_svc()
        client = _cron_app(svc)
        job_id = _seed_cron_job(svc)
        resp = client.post(f"/cron/jobs/{job_id}/pause?account_id=demo")
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

    def test_resume_job(self):
        svc = _fresh_cron_svc()
        client = _cron_app(svc)
        job_id = _seed_cron_job(svc)
        svc.pause(job_id)
        resp = client.post(f"/cron/jobs/{job_id}/resume?account_id=demo")
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_resume_non_paused_returns_409(self):
        svc = _fresh_cron_svc()
        client = _cron_app(svc)
        job_id = _seed_cron_job(svc)
        resp = client.post(f"/cron/jobs/{job_id}/resume?account_id=demo")
        assert resp.status_code == 409

    def test_delete_job(self):
        svc = _fresh_cron_svc()
        client = _cron_app(svc)
        job_id = _seed_cron_job(svc)
        resp = client.delete(f"/cron/jobs/{job_id}?account_id=demo")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_delete_unknown_returns_404(self):
        svc = _fresh_cron_svc()
        client = _cron_app(svc)
        resp = client.delete("/cron/jobs/ghost?account_id=demo")
        assert resp.status_code == 404

    def test_job_history(self):
        svc = _fresh_cron_svc()
        client = _cron_app(svc)
        job_id = _seed_cron_job(svc)
        svc.record_trigger(job_id, success=True)
        resp = client.get(f"/cron/jobs/{job_id}/history?account_id=demo")
        assert resp.status_code == 200
        assert resp.json()["run_count"] == 1

    def test_validate_valid_expression(self):
        svc = _fresh_cron_svc()
        client = _cron_app(svc)
        resp = client.post("/cron/validate", json={"cron_expression": "0 9 * * 1-5"})
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_validate_invalid_expression_returns_valid_false(self):
        svc = _fresh_cron_svc()
        client = _cron_app(svc)
        resp = client.post("/cron/validate", json={"cron_expression": "bad"})
        assert resp.status_code == 200  # Not a 422 — returns structured response
        assert resp.json()["valid"] is False
        assert "error" in resp.json()

    def test_list_jobs_filter_by_status(self):
        svc = _fresh_cron_svc()
        client = _cron_app(svc)
        job_id = _seed_cron_job(svc)
        svc.pause(job_id)
        resp = client.get("/cron/jobs?account_id=demo&status=paused")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_get_cross_account_returns_403(self):
        svc = _fresh_cron_svc()
        client = _cron_app(svc)
        job_id = _seed_cron_job(svc, account_id="owner")
        resp = client.get(f"/cron/jobs/{job_id}?account_id=other")
        assert resp.status_code == 403


# ───────────────────────────────────────────────────────────────────────────────
# Phase 9: Observability
# ───────────────────────────────────────────────────────────────────────────────

class TestObservability:

    def setup_method(self):
        from core.observability import ButlerTracer, ButlerMetrics
        ButlerTracer.reset()
        ButlerMetrics.reset()

    def test_tracer_singleton(self):
        from core.observability import ButlerTracer
        t1 = ButlerTracer.get()
        t2 = ButlerTracer.get()
        assert t1 is t2

    def test_tracer_reset_gives_new_instance(self):
        from core.observability import ButlerTracer
        t1 = ButlerTracer.get()
        ButlerTracer.reset()
        t2 = ButlerTracer.get()
        assert t1 is not t2

    def test_tracer_span_noop_does_not_raise(self):
        from core.observability import ButlerTracer
        tracer = ButlerTracer.get()
        with tracer.span("test.span", attrs={"key": "value"}, account_id="acc1"):
            pass  # Should not raise regardless of OTel availability

    def test_tracer_span_with_no_attrs(self):
        from core.observability import ButlerTracer
        tracer = ButlerTracer.get()
        with tracer.span("bare.span"):
            pass

    def test_tracer_record_error_does_not_raise(self):
        from core.observability import ButlerTracer
        tracer = ButlerTracer.get()
        tracer.record_error(ValueError("test error"))

    def test_tracer_is_available_is_bool(self):
        from core.observability import ButlerTracer
        tracer = ButlerTracer.get()
        assert isinstance(tracer.is_available, bool)

    def test_metrics_singleton(self):
        from core.observability import ButlerMetrics
        m1 = ButlerMetrics.get()
        m2 = ButlerMetrics.get()
        assert m1 is m2

    def test_metrics_reset_gives_new_instance(self):
        from core.observability import ButlerMetrics
        m1 = ButlerMetrics.get()
        ButlerMetrics.reset()
        m2 = ButlerMetrics.get()
        assert m1 is not m2

    def test_record_http_request_does_not_raise(self):
        from core.observability import ButlerMetrics
        m = ButlerMetrics.get()
        m.record_http_request("GET", "/api/v1/chat", 200, 0.123)

    def test_record_tool_call_does_not_raise(self):
        from core.observability import ButlerMetrics
        m = ButlerMetrics.get()
        m.record_tool_call("web_search", "L0", success=True)

    def test_record_llm_tokens_does_not_raise(self):
        from core.observability import ButlerMetrics
        m = ButlerMetrics.get()
        m.record_llm_tokens("anthropic", "claude-3-5-sonnet", 100, 200, 50)

    def test_set_circuit_breaker_state_does_not_raise(self):
        from core.observability import ButlerMetrics
        m = ButlerMetrics.get()
        m.set_circuit_breaker_state("redis", "open")
        m.set_circuit_breaker_state("redis", "closed")
        m.set_circuit_breaker_state("redis", "half_open")

    def test_record_memory_write_does_not_raise(self):
        from core.observability import ButlerMetrics
        m = ButlerMetrics.get()
        m.record_memory_write("HOT")
        m.record_memory_write("COLD")

    def test_set_cron_active_does_not_raise(self):
        from core.observability import ButlerMetrics
        m = ButlerMetrics.get()
        m.set_cron_active(7)

    def test_set_acp_pending_does_not_raise(self):
        from core.observability import ButlerMetrics
        m = ButlerMetrics.get()
        m.set_acp_pending(3)

    def test_metrics_is_available_is_bool(self):
        from core.observability import ButlerMetrics
        m = ButlerMetrics.get()
        assert isinstance(m.is_available, bool)

    def test_get_tracer_convenience(self):
        from core.observability import get_tracer, ButlerTracer
        t = get_tracer()
        assert isinstance(t, ButlerTracer)

    def test_get_metrics_convenience(self):
        from core.observability import get_metrics, ButlerMetrics
        m = get_metrics()
        assert isinstance(m, ButlerMetrics)

    def test_setup_observability_noop_no_endpoint(self):
        from core.observability import setup_observability
        # Should not raise even with no OTel packages active
        setup_observability(None, "butler", otel_endpoint=None)
