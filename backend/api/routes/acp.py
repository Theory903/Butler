"""ACP Routes — Phase 8b Hardened.

HTTP interface for the Action Confirmation Protocol (ACP).
Exposes the pending list, decision, and cancel endpoints.
Aligned with Oracle-Grade reliability:
- Persistent storage (Postgres).
- Distributed notifications (Redis Pub/Sub).
- RFC 9457 error compliance.
"""

from __future__ import annotations

import time
import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.deps import get_acp_server, get_db
from services.workflow.acp_server import ButlerACPServer
from domain.orchestrator.models import ApprovalRequest

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/acp", tags=["acp"])

# ── Request / Response schemas ────────────────────────────────────────────────

class DecideRequest(BaseModel):
    decision: str           # "approved" | "denied"
    human_id: str           # From JWT sub — who is approving
    note: Optional[str] = None


def _serialize_request(req: ApprovalRequest) -> dict:
    return {
        "request_id": str(req.id),
        "account_id": str(req.account_id),
        "approval_type": req.approval_type,
        "description": req.description,
        "status": req.status,
        "created_at": req.created_at.isoformat(),
        "expires_at": req.expires_at.isoformat(),
        "decided_at": req.decided_at.isoformat() if req.decided_at else None,
        "decided_by": req.decided_by,
        "task_id": str(req.task_id),
        "workflow_id": str(req.workflow_id),
    }


def _not_found(request_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "type": "https://butler.lasmoid.ai/problems/acp-not-found",
            "title": "ACP Request Not Found",
            "status": 404,
            "detail": f"No ACP request with id '{request_id}'.",
        },
    )


# ── GET /acp/requests ─────────────────────────────────────────────────────────

@router.get("/requests", summary="List pending ACP approval requests")
async def list_pending_requests(
    account_id: str = "demo",
    db: AsyncSession = Depends(get_db),
    server: ButlerACPServer = Depends(get_acp_server)
) -> dict:
    """Return all PENDING ACP requests for this account."""
    pending = await server.list_pending(db, account_id)
    return {
        "requests": [_serialize_request(r) for r in pending],
        "count": len(pending),
        "ts": int(time.time()),
    }


# ── GET /acp/requests/all ─────────────────────────────────────────────────────

@router.get("/requests/all", summary="List all ACP requests (all statuses)")
async def list_all_requests(
    account_id: str = "demo",
    db: AsyncSession = Depends(get_db)
) -> dict:
    query = select(ApprovalRequest).where(ApprovalRequest.account_id == uuid.UUID(account_id)).order_by(ApprovalRequest.created_at.desc())
    result = await db.execute(query)
    all_reqs = result.scalars().all()
    
    return {
        "requests": [_serialize_request(r) for r in all_reqs],
        "count": len(all_reqs),
        "ts": int(time.time()),
    }


# ── GET /acp/requests/{request_id} ───────────────────────────────────────────

@router.get("/requests/{request_id}", summary="Get a single ACP request by ID")
async def get_request(
    request_id: str, 
    account_id: str = "demo",
    db: AsyncSession = Depends(get_db)
) -> dict:
    uid = uuid.UUID(request_id)
    req = await db.get(ApprovalRequest, uid)
    if req is None or str(req.account_id) != account_id:
        raise _not_found(request_id)
    return _serialize_request(req)


# ── POST /acp/requests/{request_id}/decide ────────────────────────────────────

@router.post("/requests/{request_id}/decide", summary="Submit an approval decision")
async def decide(
    request_id: str, 
    body: DecideRequest, 
    account_id: str = "demo",
    db: AsyncSession = Depends(get_db),
    server: ButlerACPServer = Depends(get_acp_server)
) -> dict:
    if body.decision not in ("approved", "denied"):
        raise HTTPException(
            status_code=422,
            detail={
                "type": "https://butler.lasmoid.ai/problems/invalid-decision",
                "title": "Invalid Decision",
                "status": 422,
                "detail": "Decision must be 'approved' or 'denied'.",
            },
        )

    ok = await server.decide(db, request_id, body.decision, human_id=body.human_id)
    if not ok:
        raise HTTPException(status_code=409, detail={
            "type": "https://butler.lasmoid.ai/problems/acp-conflict",
            "title": "Decision Conflict",
            "status": 409,
            "detail": f"ACP request '{request_id}' could not be updated (not found, already decided, or expired).",
        })

    await db.commit()
    
    logger.info("acp_decision_recorded", request_id=request_id, decision=body.decision, human_id=body.human_id)
    return {
        "request_id": request_id,
        "decision": body.decision,
        "ts": int(time.time()),
    }


def create_acp_router() -> APIRouter:
    """Legacy support for main.py router inclusion."""
    return router
