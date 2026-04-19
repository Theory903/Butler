import uuid
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from api.schemas.communication import (
    SendRequest,
    DeliveryState,
    PolicyResultResponse,
    CanonicalInbound
)
from services.communication.policy import CommunicationPolicy
from services.communication.delivery import DeliveryService
from services.communication.webhooks import WebhookValidator
from core.deps import get_db, get_cache

router = APIRouter(prefix="/communication", tags=["communication"])


# ── Dependency factories ───────────────────────────────────────────────────────

async def get_communication_policy(
    db: AsyncSession = Depends(get_db),
) -> CommunicationPolicy:
    return CommunicationPolicy(db=db)


async def get_delivery_service(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_cache),
    bg_tasks: BackgroundTasks = None,
) -> DeliveryService:
    policy = CommunicationPolicy(db=db)
    return DeliveryService(db=db, redis=redis, policy=policy, bg_tasks=bg_tasks)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/prepare", response_model=PolicyResultResponse)
async def prepare_message(
    request: SendRequest,
    policy: CommunicationPolicy = Depends(get_communication_policy),
):
    """
    Check if a message is allowed to be sent without enqueueing.
    Evaluates consent, quiet hours, sender verification, and risk tokens.
    """
    result = await policy.pre_send_check(request)
    return PolicyResultResponse(
        allowed=result.allowed,
        reason=result.reason,
        suppressed=result.suppressed
    )

@router.post("/send")
async def send_message(
    request: SendRequest,
    delivery_service: DeliveryService = Depends(get_delivery_service),
) -> Dict[str, Any]:
    """
    Enqueue a message for delivery via the Communication Control Plane.
    Returns tracking info.
    """
    message_id = await delivery_service.enqueue_delivery(request)

    return {
        "message_id": message_id,
        "status": "queued",
        "status_url": f"/api/v1/comm/status/{message_id}",
        "phase": "accepted"
    }

@router.get("/status/{message_id}", response_model=DeliveryState)
async def get_message_status(
    message_id: str,
    delivery_service: DeliveryService = Depends(get_delivery_service),
):
    """
    Retrieve the current multi-stage status of a message.
    """
    state = await delivery_service.get_delivery_state(message_id)
    if not state:
        raise HTTPException(status_code=404, detail="Message not found")
    return state

@router.post("/webhooks/{provider}")
async def provider_webhook(
    provider: str,
    request: Request,
    background_tasks: BackgroundTasks,
    validator: WebhookValidator = Depends(),
    delivery_service: DeliveryService = Depends(get_delivery_service),
):
    """
    Inbound webhooks for delivery status updates and inbound messages.
    Strictly verifies provider signature before processing.
    """
    body = await request.body()

    # 1. Verification
    is_valid = False
    if provider == "twilio":
        is_valid = await validator.verify_twilio(request)
    elif provider == "sendgrid":
        is_valid = await validator.verify_sendgrid(request, body)
    elif provider == "meta":
        is_valid = await validator.verify_whatsapp(request, body)
    else:
        raise HTTPException(status_code=400, detail="Unsupported provider")

    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid provider signature")

    # 2. Async processing
    payload = None
    if request.headers.get("Content-Type") == "application/json":
        payload = await request.json()
    else:
        payload = dict(await request.form())

    background_tasks.add_task(
        delivery_service.process_webhook_event,
        provider,
        payload
    )

    return Response(content="Accepted", status_code=202)
