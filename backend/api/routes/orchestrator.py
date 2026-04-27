from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.routes.gateway import get_current_account
from core.deps import get_orchestrator_service
from core.envelope import ButlerEnvelope
from core.errors import Problem
from domain.auth.contracts import AccountContext
from domain.runtime import ResponseValidator
from services.orchestrator.service import OrchestratorService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])

CurrentAccount = Annotated[AccountContext, Depends(get_current_account)]
OrchestratorDep = Annotated[OrchestratorService, Depends(get_orchestrator_service)]


class ApprovalDecisionRequest(BaseModel):
    decision: str  # 'approved' or 'denied'


class ApprovalResolutionResponse(BaseModel):
    approval_id: str
    decision: str
    task_id: str
    task_status: str


async def _resolve_approval(
    *,
    approval_id: str,
    req: ApprovalDecisionRequest,
    account: AccountContext,
    svc: OrchestratorService,
) -> ApprovalResolutionResponse:
    task = await svc.approve_request(
        approval_id,
        req.decision,
        account_id=account.account_id,
    )
    return ApprovalResolutionResponse(
        approval_id=approval_id,
        decision=req.decision,
        task_id=str(task.id),
        task_status=str(task.status),
    )


@router.post("/intake")
async def orchestrator_intake(
    envelope: ButlerEnvelope,
    svc: OrchestratorDep,
):
    """Canonical entry point for intelligence task ingestion.

    Response is validated through Runtime Spine to prevent leaks.
    """
    logger.info("orchestrator_route_intake_called", session_id=envelope.session_id)
    result = await svc.intake(envelope)

    # Validate response content to prevent leaks
    if hasattr(result, "content") and result.content:
        try:
            ResponseValidator.validate_user_facing_response(result.content)
        except Exception:
            # Sanitize if validation fails
            result.content = ResponseValidator.sanitize_user_facing_response(result.content)

    return result


@router.post("/intake_streaming")
async def orchestrator_intake_streaming(
    envelope: ButlerEnvelope,
    svc: OrchestratorDep,
):
    """Streaming entry point for intelligence tasks."""
    from services.gateway.stream_bridge import SSE_HEADERS

    async def event_stream() -> AsyncGenerator[str]:
        async for event in svc.intake_streaming(envelope):
            yield event.to_sse()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("/workflows/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    account: CurrentAccount,
    svc: OrchestratorDep,
):
    workflow = await svc.get_workflow(workflow_id)
    if not workflow or str(workflow.account_id) != account.account_id:
        raise Problem(
            type="https://docs.butler.lasmoid.ai/problems/workflow-not-found",
            title="Workflow Not Found",
            status=404,
        )
    return workflow


@router.get("/approvals")
async def list_approvals(
    account: CurrentAccount,
    svc: OrchestratorDep,
):
    return await svc.get_pending_approvals(account.account_id)


@router.post("/approval/{approval_id}/resolve")
async def resolve_approval(
    approval_id: str,
    req: ApprovalDecisionRequest,
    account: CurrentAccount,
    svc: OrchestratorDep,
) -> ApprovalResolutionResponse:
    return await _resolve_approval(
        approval_id=approval_id,
        req=req,
        account=account,
        svc=svc,
    )


@router.post("/approvals/{approval_id}")
async def decide_approval_legacy(
    approval_id: str,
    req: ApprovalDecisionRequest,
    account: CurrentAccount,
    svc: OrchestratorDep,
) -> ApprovalResolutionResponse:
    return await _resolve_approval(
        approval_id=approval_id,
        req=req,
        account=account,
        svc=svc,
    )
