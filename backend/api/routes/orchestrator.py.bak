from fastapi import APIRouter, Depends
from typing import List
from pydantic import BaseModel

from core.errors import Problem
from domain.auth.contracts import AccountContext
from api.routes.gateway import get_current_account
from core.envelope import ButlerEnvelope
from services.orchestrator.service import OrchestratorService
from core.deps import get_db, get_redis, get_orchestrator_service

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])

class ApprovalDecisionRequest(BaseModel):
    decision: str  # 'approved' or 'denied'

@router.post("/intake")
async def orchestrator_intake(
    envelope: ButlerEnvelope,
    svc: OrchestratorService = Depends(get_orchestrator_service),
):
    """Canonical entry point for intelligence task ingestion."""
    return await svc.intake(envelope)

@router.post("/intake_streaming")
async def orchestrator_intake_streaming(
    envelope: ButlerEnvelope,
    svc: OrchestratorService = Depends(get_orchestrator_service),
):
    """Streaming entry point for intelligence tasks."""
    from fastapi.responses import StreamingResponse
    from services.gateway.stream_bridge import SSE_HEADERS
    
    return StreamingResponse(
        svc.intake_streaming(envelope),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )

@router.get("/workflows/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    account: AccountContext = Depends(get_current_account),
    svc: OrchestratorService = Depends(get_orchestrator_service),
):
    workflow = await svc.get_workflow(workflow_id)
    if not workflow or str(workflow.account_id) != account.account_id:
        raise Problem(type="https://docs.butler.lasmoid.ai/problems/workflow-not-found", title="Workflow Not Found", status=404)
    return workflow

@router.get("/approvals")
async def list_approvals(
    account: AccountContext = Depends(get_current_account),
    svc: OrchestratorService = Depends(get_orchestrator_service),
):
    approvals = await svc.get_pending_approvals(account.account_id)
    return approvals

@router.post("/approvals/{approval_id}")
async def decide_approval(
    approval_id: str,
    req: ApprovalDecisionRequest,
    account: AccountContext = Depends(get_current_account),
    svc: OrchestratorService = Depends(get_orchestrator_service),
):
    return await svc.approve_request(approval_id, req.decision)
