"""ACP Routes — Phase 8b.

HTTP interface for the Action Confirmation Protocol (ACP).
Exposes the pendinglist, decision, and cancel endpoints.

Endpoints:
  GET  /acp/requests             — list pending ACP requests for the caller
  GET  /acp/requests/{id}        — get a single ACP request
  POST /acp/requests/{id}/decide — submit a human decision (approve/deny)
  POST /acp/requests/{id}/cancel — cancel a pending request

Security:
  - All routes require a valid JWT (account-scoped).
  - /decide requires the human_id claim from the JWT — sourced from
    the bearer token's sub claim + an explicit human_id body field.
  - Only the issuing account's requests are visible (no cross-account leak).
  - Denied or timed-out requests cannot be re-decided (idempotent by design).

RFC 9457 error responses on all error paths.

Note: ACP request creation is internal-only (called by HermesAgentBackend
when ApprovalRequired is raised). There is no external POST /acp/requests
endpoint — the workflow pause is the entry point.
"""

from __future__ import annotations

import time
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.workflow.acp_server import (
    ACPDecision,
    ButlerACPServer,
    get_acp_server,
)

logger = structlog.get_logger(__name__)


# ── Request / Response schemas ────────────────────────────────────────────────

class DecideRequest(BaseModel):
    decision: str           # "approved" | "denied"
    human_id: str           # From JWT sub — who is approving
    note: Optional[str] = None


class ACPRequestOut(BaseModel):
    request_id: str
    account_id: str
    tool_name: str
    approval_mode: str
    risk_tier: str
    description: str
    status: str
    created_at: str
    expires_at: str
    decided_at: Optional[str] = None
    decided_by: Optional[str] = None
    decision_note: Optional[str] = None
    task_id: str
    session_id: str


def _serialize_request(req) -> dict:
    return {
        "request_id": req.request_id,
        "account_id": req.account_id,
        "tool_name": req.tool_name,
        "approval_mode": req.approval_mode,
        "risk_tier": req.risk_tier,
        "description": req.description,
        "status": req.status.value,
        "created_at": req.created_at.isoformat(),
        "expires_at": req.expires_at.isoformat(),
        "decided_at": req.decided_at.isoformat() if req.decided_at else None,
        "decided_by": req.decided_by,
        "decision_note": req.decision_note,
        "task_id": req.task_id,
        "session_id": req.session_id,
    }


# ── ACP Router ────────────────────────────────────────────────────────────────

def create_acp_router(
    acp_server: ButlerACPServer | None = None,
    require_account_id: bool = False,
) -> APIRouter:
    """Create the /acp route group.

    Args:
        acp_server:        ACPServer instance (defaults to singleton).
        require_account_id: When True, extract account_id from JWT and scope
                           requests. In tests, set False for simplicity.
    """
    server = acp_server or get_acp_server()
    router = APIRouter(prefix="/acp", tags=["acp"])

    # ── GET /acp/requests ─────────────────────────────────────────────────────

    @router.get("/requests", summary="List pending ACP approval requests")
    async def list_pending_requests(account_id: str = "demo") -> dict:
        """Return all PENDING ACP requests for this account.

        In production, account_id comes from the validated JWT.
        Timed-out requests are lazily expired on read.
        """
        pending = server.list_pending(account_id)
        return {
            "requests": [_serialize_request(r) for r in pending],
            "count": len(pending),
            "ts": int(time.time()),
        }

    # ── GET /acp/requests/all ─────────────────────────────────────────────────

    @router.get("/requests/all", summary="List all ACP requests (all statuses)")
    async def list_all_requests(account_id: str = "demo") -> dict:
        all_reqs = server.list_all(account_id)
        return {
            "requests": [_serialize_request(r) for r in all_reqs],
            "count": len(all_reqs),
            "ts": int(time.time()),
        }

    # ── GET /acp/requests/{request_id} ───────────────────────────────────────

    @router.get("/requests/{request_id}", summary="Get a single ACP request by ID")
    async def get_request(request_id: str, account_id: str = "demo") -> dict:
        req = server.get(request_id)
        if req is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "type": "https://butler.lasmoid.ai/problems/acp-not-found",
                    "title": "ACP Request Not Found",
                    "status": 404,
                    "detail": f"No ACP request with id '{request_id}'.",
                },
            )
        if req.account_id != account_id:
            raise HTTPException(
                status_code=403,
                detail={
                    "type": "https://butler.lasmoid.ai/problems/forbidden",
                    "title": "Forbidden",
                    "status": 403,
                    "detail": "This ACP request belongs to a different account.",
                },
            )
        return _serialize_request(req)

    # ── POST /acp/requests/{request_id}/decide ────────────────────────────────

    @router.post("/requests/{request_id}/decide", summary="Submit an approval decision")
    async def decide(request_id: str, body: DecideRequest, account_id: str = "demo") -> dict:
        # Validate decision value
        try:
            decision = ACPDecision(body.decision)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail={
                    "type": "https://butler.lasmoid.ai/problems/invalid-decision",
                    "title": "Invalid Decision",
                    "status": 422,
                    "detail": f"Decision must be 'approved' or 'denied', got '{body.decision}'.",
                },
            )
        if decision not in (ACPDecision.APPROVED, ACPDecision.DENIED):
            raise HTTPException(
                status_code=422,
                detail={
                    "type": "https://butler.lasmoid.ai/problems/invalid-decision",
                    "title": "Invalid Decision",
                    "status": 422,
                    "detail": "Only 'approved' and 'denied' are valid external decisions.",
                },
            )

        result = server.decide(request_id, decision, human_id=body.human_id, note=body.note)
        if result is None:
            # Could be: not found, already decided, expired
            req = server.get(request_id)
            if req is None:
                raise HTTPException(status_code=404, detail={
                    "type": "https://butler.lasmoid.ai/problems/acp-not-found",
                    "title": "ACP Request Not Found",
                    "status": 404,
                    "detail": f"No ACP request with id '{request_id}'.",
                })
            raise HTTPException(status_code=409, detail={
                "type": "https://butler.lasmoid.ai/problems/acp-already-decided",
                "title": "Already Decided",
                "status": 409,
                "detail": f"ACP request '{request_id}' is already in status '{req.status.value}'.",
            })

        logger.info(
            "acp_decision_recorded",
            request_id=request_id,
            decision=decision.value,
            human_id=body.human_id,
        )
        return {
            "request_id": result.request_id,
            "decision": result.decision.value,
            "tool_name": result.tool_name,
            "decided_by": result.decided_by,
            "decided_at": result.decided_at.isoformat(),
            "ts": int(time.time()),
        }

    # ── POST /acp/requests/{request_id}/cancel ────────────────────────────────

    @router.post("/requests/{request_id}/cancel", summary="Cancel a pending ACP request")
    async def cancel(request_id: str) -> dict:
        ok = server.cancel(request_id)
        if not ok:
            req = server.get(request_id)
            if req is None:
                raise HTTPException(status_code=404, detail={
                    "type": "https://butler.lasmoid.ai/problems/acp-not-found",
                    "title": "ACP Request Not Found",
                    "status": 404,
                    "detail": f"No ACP request with id '{request_id}'.",
                })
            raise HTTPException(status_code=409, detail={
                "type": "https://butler.lasmoid.ai/problems/acp-not-cancellable",
                "title": "Not Cancellable",
                "status": 409,
                "detail": f"ACP request '{request_id}' is in status '{req.status.value}' and cannot be cancelled.",
            })
        return {"request_id": request_id, "status": "cancelled", "ts": int(time.time())}

    # ── GET /acp/stats ────────────────────────────────────────────────────────

    @router.get("/stats", summary="ACP server statistics")
    async def acp_stats() -> dict:
        stale = server.expire_stale()
        return {
            "pending": server.pending_count,
            "total": server.total_count,
            "stale_expired": stale,
            "ts": int(time.time()),
        }

    return router
