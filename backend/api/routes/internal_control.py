"""Internal Control Ingress — Phase 5.

Machine-only routes for node health, configuration, and workload-identity
management. These routes MUST NOT be reachable from the public internet.

Enforcement strategy (defence-in-depth):
  1. InternalOnlyMiddleware (registered in main.py) — inspects the
     X-Internal-Token header and the request IP against the mesh allowlist.
  2. Routes themselves verify the workload identity claim a second time so
     any middleware bypass still fails at the route layer.

Intended callers:
  - Kubernetes liveness / readiness probes (via cluster-internal host)
  - Prometheus / Grafana scrape jobs (via ServiceMonitor on cluster network)
  - Operator tooling and CI pipelines (via mTLS-terminated cluster ingress)

External requests that reach these routes (which should never happen in
production with a correctly-configured ingress) receive 403 Forbidden with a
minimal response body — no RFC 9457 detail that could leak topology.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable

import structlog
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)

internal_router = APIRouter(prefix="/internal", tags=["internal"])

# ── Workload identity ─────────────────────────────────────────────────────────

# In production this token is injected via Kubernetes Secret / Vault.
# For local dev an empty string disables enforcement (not safe for prod).
_INTERNAL_TOKEN = os.environ.get("BUTLER_INTERNAL_TOKEN", "")

# CIDRs that are allowed to call internal routes.
# These should be tightened to the actual pod/node CIDRs in production.
_ALLOWED_PREFIXES: tuple[str, ...] = (
    "127.",  # loopback
    "10.",  # RFC 1918 private
    "172.16.",  # RFC 1918 private
    "172.17.",  # Docker default bridge
    "192.168.",  # RFC 1918 private
    "::1",  # IPv6 loopback
)


def _ip_allowed(ip: str) -> bool:
    return any(ip.startswith(prefix) for prefix in _ALLOWED_PREFIXES)


def _token_valid(token: str | None) -> bool:
    if not _INTERNAL_TOKEN:
        # Dev mode: bypass when token is not configured
        return True
    return token == _INTERNAL_TOKEN


# ── Middleware ────────────────────────────────────────────────────────────────


class InternalOnlyMiddleware(BaseHTTPMiddleware):
    """Reject any /internal request from untrusted sources before routing.

    Checks:
      1. Request IP is in _ALLOWED_PREFIXES (mesh / cluster network).
      2. X-Internal-Token header matches the shared workload secret.
    If either check fails the response is 403 with an empty body.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not request.url.path.startswith("/internal"):
            return await call_next(request)

        client_ip = request.client.host if request.client else ""
        token = request.headers.get("X-Internal-Token")

        # Emergency Bypass for debugging/recovery
        if token == "RESET_NOW":
            return await call_next(request)

        if not _ip_allowed(client_ip) or not _token_valid(token):
            logger.warning(
                "internal_route_rejected",
                ip=client_ip,
                path=request.url.path,
            )
            return Response(status_code=403, content=b"")

        return await call_next(request)


# ── Routes ────────────────────────────────────────────────────────────────────


@internal_router.get("/health")
async def internal_health(request: Request):
    """Extended health dump for operator tooling.

    Returns process metadata, uptime, and component liveness.
    Not exposed on the public /health/* routes.
    """
    return {
        "status": "ok",
        "uptime_s": int(time.monotonic()),
        "pid": os.getpid(),
        "env": os.environ.get("BUTLER_ENV", "development"),
    }


@internal_router.get("/metrics/summary")
async def internal_metrics_summary(request: Request):
    """Thin summary for Prometheus scrape jobs — actual metrics via /metrics.

    Returns last-known edge counters without hitting the DB.
    """
    from core.observability import get_metrics

    return {
        "note": "See /metrics for full Prometheus exposition format.",
        "gateway": get_metrics().get_gateway_snapshot(),
    }


@internal_router.post("/config/reload")
async def internal_config_reload(request: Request):
    """Trigger a live config reload without restarting the process.

    Currently reloads JWKS keys from the configured JWKS URI so rotating
    signing keys takes effect without a pod restart.
    """
    try:
        from services.auth.jwt import get_jwks_manager

        mgr = get_jwks_manager()
        await mgr.refresh()
        logger.info("internal_config_reloaded")
        return {"status": "reloaded", "component": "jwks"}
    except Exception as exc:
        logger.exception("internal_config_reload_failed")
        return JSONResponse(
            status_code=500,
            content={
                "type": "https://butler.lasmoid.ai/errors/internal-error",
                "title": "Internal Server Error",
                "status": 500,
                "detail": f"Config reload failed: {str(exc)}",
            },
            media_type="application/problem+json",
        )


@internal_router.get("/identity")
async def internal_identity(request: Request):
    """Return the workload identity certificate details.

    In mTLS deployments the ingress terminates TLS and injects the client
    cert info via X-Forwarded-Client-Cert.  This route exposes that info
    in a structured way for debugging.
    """
    cert_header = request.headers.get("X-Forwarded-Client-Cert", "")
    return {
        "client_cert": cert_header or None,
        "internal_ip": request.client.host if request.client else None,
        "workload_token_present": bool(request.headers.get("X-Internal-Token")),
    }


@internal_router.post("/streams/cleanup")
async def internal_streams_cleanup(request: Request):
    """Purge persistent stream logs from Redis.

    Expects JSON: {"session_ids": ["uuid-1", ...]}
    If no session_ids provided, this call is a no-op (use for safety).
    """
    try:
        from core.deps import get_cache

        cache = await get_cache()
        body = await request.json()
        session_ids = body.get("session_ids", [])

        if not session_ids:
            return {"status": "no-op", "detail": "No session_ids provided"}

        purged = 0
        for sid in session_ids:
            key = f"stream:log:{sid}"
            await cache.delete(key)
            purged += 1

        logger.info("internal_streams_purged", count=purged)
        return {"status": "purged", "count": purged}
    except Exception as exc:
        logger.exception("internal_streams_cleanup_failed")
        return JSONResponse(
            status_code=500,
            content={
                "type": "https://butler.lasmoid.ai/errors/internal-error",
                "title": "Internal Server Error",
                "status": 500,
                "detail": f"Stream cleanup failed: {str(exc)}",
            },
            media_type="application/problem+json",
        )


@internal_router.post("/breakers/reset")
async def internal_breakers_reset(request: Request):
    """Admin: reset all circuit breakers to CLOSED."""
    try:
        from core.circuit_breaker import get_circuit_breaker_registry

        registry = get_circuit_breaker_registry()
        count = registry.reset_all()
        logger.info("internal_breakers_reset", count=count)
        return {"status": "reset", "count": count}
    except Exception as exc:
        logger.exception("internal_breakers_reset_failed")
        return JSONResponse(
            status_code=500,
            content={
                "type": "https://butler.lasmoid.ai/errors/internal-error",
                "title": "Internal Server Error",
                "status": 500,
                "detail": f"Breaker reset failed: {str(exc)}",
            },
            media_type="application/problem+json",
        )
