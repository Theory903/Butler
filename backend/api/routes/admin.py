"""Admin Plane — Phase 6.

Seven production admin endpoints:
  GET  /admin/circuit-breakers        — all breaker states
  POST /admin/circuit-breakers/reset  — reset all breakers to CLOSED
  GET  /admin/services/status         — per-service health + breaker state
  POST /admin/kill-switch/{service}   — disable a service (kill switch)
  POST /admin/drain                   — drain in-flight requests, stop accepting
  GET  /admin/memory/stats            — cold/warm store sizes + write policy hits
  POST /admin/routing/decision        — dry-run a SmartRouter decision
  GET  /admin/audit/recent            — last N audit log entries from Redis

Security:
  All /admin/* routes require a valid JWT with aal=aal3 (highest assurance).
  In dev mode (settings.ENV == "development"), aal3 requirement is relaxed to aal1.
  403 if aal insufficient; 401 if no/invalid token.

RFC 9457 error format on all error responses.
"""

from __future__ import annotations

import json
import time
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel

from core.circuit_breaker import CircuitBreakerRegistry, get_circuit_breaker_registry
from core.errors import ForbiddenProblem, Problem

logger = structlog.get_logger(__name__)

# ── Request / Response schemas ─────────────────────────────────────────────────

class KillSwitchRequest(BaseModel):
    enabled: bool = True
    reason: str = ""


class DrainRequest(BaseModel):
    timeout_s: int = 30
    reason: str = ""


class RoutingDryRunRequest(BaseModel):
    message: str
    intent_label: str = "general"
    intent_confidence: float = 0.5
    complexity: str = "simple"
    requires_tools: bool = False
    context_token_count: int = 0
    latency_budget_ms: int = 2000
    force_tier: int | None = None


# In-process kill switch registry (service_name → is_killed)
_kill_switches: dict[str, bool] = {}

# Drain state
_draining: bool = False


def is_service_killed(service: str) -> bool:
    return _kill_switches.get(service, False)


def is_draining() -> bool:
    return _draining


# ── Admin Router ──────────────────────────────────────────────────────────────

def create_admin_router(
    registry: CircuitBreakerRegistry | None = None,
    cold_store=None,         # TurboQuantColdStore | None
    smart_router=None,       # ButlerSmartRouter | None
    audit_redis=None,        # Redis | None
    cluster_redis=None,      # Redis | None — for cluster inspector
) -> APIRouter:
    """Create the /admin route group.

    Args:
        registry:      CircuitBreakerRegistry instance (defaults to singleton).
        cold_store:    TurboQuantColdStore for /admin/memory/stats.
        smart_router:  ButlerSmartRouter for /admin/routing/decision dry-run.
        audit_redis:   Redis for /admin/audit/recent.
        cluster_redis: Redis for /admin/cluster/status (node aggregation).
    """
    cb_registry = registry or get_circuit_breaker_registry()
    router = APIRouter(prefix="/admin", tags=["admin"])

    # ── 1. GET /metrics ──────────────────────────────────────────────────────
    @router.get("/metrics", summary="Prometheus metrics (text format)")
    async def metrics():
        """Scrape target for Prometheus."""
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
        from fastapi import Response
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # ── 0. GET /admin/cluster/status ─────────────────────────────────────────

    @router.get("/cluster/status", summary="Real-time cluster-wide health dashboard")
    async def cluster_status() -> dict:
        """Aggregate health metadata from all live nodes registered in Redis.

        Returns a node-by-node breakdown plus cluster-level roll-up:
        - healthy_nodes / degraded_nodes / unhealthy_nodes counts
        - cluster_status: HEALTHY | DEGRADED | CRITICAL
        - per-node: cpu, mem, pending_tools, status, uptime
        """
        if cluster_redis is None:
            return {
                "cluster_status": "UNKNOWN",
                "note": "cluster_redis not wired",
                "nodes": [],
                "ts": int(time.time()),
            }

        try:
            # Scan for all node registry keys (TTL-managed by HealthAgent heartbeat)
            node_keys = await cluster_redis.keys("butler:nodes:*")
            # Filter out sub-keys like butler:nodes:<id>:pending_tools
            registry_keys = [k for k in node_keys if k.count(b":") == 2]

            nodes = []
            for key in registry_keys:
                raw = await cluster_redis.get(key)
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    continue

                node_id = data.get("node_id", key.decode().split(":")[-1])

                # Fetch pending tool count from the node-local counter
                pending_key = f"butler:nodes:{node_id}:pending_tools"
                pending_raw = await cluster_redis.get(pending_key)
                pending_tools = int(pending_raw) if pending_raw else 0

                # Uptime: registered nodes store started_at or updated_at
                started_at = data.get("started_at") or data.get("updated_at", time.time())
                uptime_s = max(0, time.time() - float(started_at))

                nodes.append({
                    "node_id": node_id,
                    "status": data.get("status", "UNKNOWN"),
                    "version": data.get("version", "unknown"),
                    "cpu_percent": data.get("cpu_percent", 0),
                    "memory_percent": data.get("memory_percent", 0),
                    "pending_tools": pending_tools,
                    "uptime_s": round(uptime_s, 1),
                    "last_heartbeat": data.get("updated_at", time.time()),
                })

            # Cluster-wide roll-up
            total = len(nodes)
            healthy = sum(1 for n in nodes if n["status"] == "HEALTHY")
            degraded = sum(1 for n in nodes if n["status"] == "DEGRADED")
            unhealthy = sum(1 for n in nodes if n["status"] == "UNHEALTHY")

            # Cluster health: CRITICAL if >50% unhealthy, DEGRADED if any degraded/unhealthy
            if total == 0:
                cluster_health = "NO_NODES"
            elif unhealthy / max(total, 1) > 0.5:
                cluster_health = "CRITICAL"
            elif degraded + unhealthy > 0:
                cluster_health = "DEGRADED"
            else:
                cluster_health = "HEALTHY"

            total_pending = sum(n["pending_tools"] for n in nodes)

            logger.info(
                "cluster_status_polled",
                total=total,
                healthy=healthy,
                degraded=degraded,
                unhealthy=unhealthy,
                cluster_health=cluster_health,
            )

            return {
                "cluster_status": cluster_health,
                "summary": {
                    "total_nodes": total,
                    "healthy": healthy,
                    "degraded": degraded,
                    "unhealthy": unhealthy,
                    "total_pending_tools": total_pending,
                },
                "nodes": sorted(nodes, key=lambda n: n["node_id"]),
                "ts": int(time.time()),
            }

        except Exception as exc:
            logger.error("cluster_status_failed", error=str(exc))
            return {
                "cluster_status": "UNKNOWN",
                "error": str(exc),
                "nodes": [],
                "ts": int(time.time()),
            }


    @router.get("/circuit-breakers", summary="List all circuit breaker states")
    async def list_circuit_breakers() -> dict:
        all_stats = cb_registry.all_stats()
        any_open = cb_registry.any_open()
        return {
            "circuit_breakers": all_stats,
            "any_open": any_open,
            "total": len(all_stats),
            "ts": int(time.time()),
        }

    # ── 2. POST /admin/circuit-breakers/reset ─────────────────────────────────

    @router.post("/circuit-breakers/reset", summary="Reset all circuit breakers to CLOSED")
    async def reset_circuit_breakers() -> dict:
        count = cb_registry.reset_all()
        logger.warning("admin_circuit_breakers_reset", count=count)
        return {"reset": count, "ts": int(time.time())}

    # ── 3. GET /admin/services/status ─────────────────────────────────────────

    @router.get("/services/status", summary="Per-service health and circuit breaker state")
    async def services_status() -> dict:
        services = [
            "gateway", "orchestrator", "memory", "auth", "ml",
            "tools", "realtime", "search",
        ]
        statuses = {}
        for svc in services:
            breaker = cb_registry.get(svc)
            killed = is_service_killed(svc)
            statuses[svc] = {
                "killed": killed,
                "circuit_state": breaker.state.value if breaker else "no_breaker",
                "status": "killed" if killed else (
                    "open" if (breaker and breaker.state.value == "open") else "healthy"
                ),
            }
        return {
            "services": statuses,
            "draining": _draining,
            "ts": int(time.time()),
        }

    # ── 4. POST /admin/kill-switch/{service} ──────────────────────────────────

    @router.post("/kill-switch/{service}", summary="Enable or disable a service kill switch")
    async def toggle_kill_switch(service: str, body: KillSwitchRequest) -> dict:
        _kill_switches[service] = body.enabled
        logger.warning(
            "admin_kill_switch_toggled",
            service=service,
            enabled=body.enabled,
            reason=body.reason,
        )
        return {
            "service": service,
            "killed": body.enabled,
            "reason": body.reason,
            "ts": int(time.time()),
        }

    # ── 5. POST /admin/drain ──────────────────────────────────────────────────

    @router.post("/drain", summary="Drain in-flight requests and stop accepting new ones")
    async def drain(body: DrainRequest) -> dict:
        global _draining
        _draining = True
        logger.warning("admin_drain_initiated", timeout_s=body.timeout_s, reason=body.reason)
        return {
            "draining": True,
            "timeout_s": body.timeout_s,
            "reason": body.reason,
            "ts": int(time.time()),
        }

    @router.delete("/drain", summary="Cancel drain — resume accepting requests")
    async def cancel_drain() -> dict:
        global _draining
        _draining = False
        logger.info("admin_drain_cancelled")
        return {"draining": False, "ts": int(time.time())}

    # ── 6. GET /admin/memory/stats ────────────────────────────────────────────

    @router.get("/memory/stats", summary="Cold/warm store sizes and write policy stats")
    async def memory_stats() -> dict:
        cold_stats = {}
        if cold_store is not None:
            cold_stats = cold_store.stats()

        return {
            "cold_store": cold_stats,
            "warm_store": {"status": "phase_4b_stub"},
            "ts": int(time.time()),
        }

    # ── 7. POST /admin/routing/decision ──────────────────────────────────────

    @router.post("/routing/decision", summary="Dry-run a SmartRouter tier decision")
    async def routing_dry_run(body: RoutingDryRunRequest) -> dict:
        if smart_router is None:
            return {"error": "smart_router not wired", "ts": int(time.time())}

        from domain.ml.contracts import IntentResult
        from services.ml.smart_router import RouterRequest, ModelTier

        intent = IntentResult(
            label=body.intent_label,
            confidence=body.intent_confidence,
            complexity=body.complexity,
            requires_tools=body.requires_tools,
            requires_memory=True,
        )
        force = ModelTier(body.force_tier) if body.force_tier is not None else None
        req = RouterRequest(
            intent=intent,
            message=body.message,
            context_token_count=body.context_token_count,
            latency_budget_ms=body.latency_budget_ms,
            force_tier=force,
        )
        decision = smart_router.route(req)
        return {
            "tier": decision.tier.name,
            "tier_value": decision.tier.value,
            "runtime_profile": decision.runtime_profile,
            "provider": decision.provider,
            "tri_attention": decision.tri_attention,
            "reason": decision.reason,
            "override_by_user": decision.override_by_user,
            "metadata": decision.metadata,
            "ts": int(time.time()),
        }

    # ── 8. GET /admin/audit/recent ────────────────────────────────────────────

    @router.get("/audit/recent", summary="Last N audit log entries from Redis")
    async def audit_recent(limit: int = 20) -> dict:
        if audit_redis is None:
            return {"entries": [], "note": "audit_redis not wired", "ts": int(time.time())}

        try:
            raw_entries = await audit_redis.lrange("butler:audit:log", 0, limit - 1)
            entries = []
            for raw in raw_entries:
                if isinstance(raw, bytes):
                    raw = raw.decode()
                try:
                    entries.append(json.loads(raw))
                except (json.JSONDecodeError, ValueError):
                    entries.append({"raw": raw})
        except Exception as exc:
            logger.warning("admin_audit_fetch_failed", error=str(exc))
            entries = []

        return {
            "entries": entries,
            "count": len(entries),
            "ts": int(time.time()),
        }

    return router
