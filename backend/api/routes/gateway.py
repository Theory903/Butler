# ruff: noqa: B008

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from core.deps import get_cache, get_hermes_transport, get_ws_mux
from core.envelope import ButlerEnvelope, OrchestratorResult
from core.resilient_client import (
    InternalRequest,
    ResilientClient,
    ResilientClientConfig,
)
from domain.auth.contracts import AccountContext
from domain.runtime import (
    FinalResponseComposer,
    ResponseValidator,
    ToolResultEnvelope,
)
from infrastructure.config import settings
from infrastructure.database import async_session_factory

from services.auth.jwt import get_jwks_manager
from services.gateway.auth_middleware import JWTAuthMiddleware
from services.gateway.idempotency import IdempotencyService
from services.gateway.rate_limiter import RateLimiter
from services.gateway.session_manager import ButlerSessionManager
from services.gateway.stream_bridge import SSE_HEADERS, ButlerStreamBridge

log = structlog.get_logger(__name__)
router = APIRouter(tags=["gateway"])


# =============================================================================
# Shared internal client
# =============================================================================

_orchestrator_client = ResilientClient(
    source_service="gateway",
    base_url=settings.ORCHESTRATOR_URL.rstrip("/"),
    config=ResilientClientConfig(
        timeout=30.0,
    ),
)


# =============================================================================
# Schemas
# =============================================================================


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4096)
    session_id: str = Field(min_length=1, max_length=128)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    location: dict[str, Any] | None = None
    mode: str = Field(default="auto", max_length=64)
    stream: bool = False
    model: str | None = Field(default=None, max_length=128)


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response: str
    session_id: str
    request_id: str
    workflow_id: str | None = None
    actions_taken: list[dict[str, Any]] = Field(default_factory=list)
    requires_approval: bool = False
    approval_id: str | None = None


class VoiceProcessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audio_data: str = Field(..., description="base64-encoded audio")
    format: str = Field(default="wav", max_length=32)
    session_id: str | None = None


class VoiceProcessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    transcript: str
    response: str
    audio_data: str | None = None


class SessionBootstrapResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    request_id: str
    resume_token: str | None = None


# =============================================================================
# Dependencies
# =============================================================================


async def get_current_account(
    request: Request,
    cache=Depends(get_cache),
) -> AccountContext:
    """Authenticate the inbound request and return the resolved account context."""
    middleware = JWTAuthMiddleware(
        jwks=get_jwks_manager(),
        redis=cache,
    )
    authorization = request.headers.get("Authorization")
    ctx = await middleware.authenticate(authorization)
    object.__setattr__(ctx, "device_id", request.headers.get("X-Device-ID"))
    return ctx


@asynccontextmanager
async def _session_scope():
    async with async_session_factory() as db:
        yield db


# =============================================================================
# Helpers
# =============================================================================


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))


def _idempotency_key(request: Request) -> str | None:
    return request.headers.get("Idempotency-Key") or request.headers.get("X-Idempotency-Key")


def _channel(request: Request, fallback: str = "api") -> str:
    raw = request.headers.get("X-Butler-Channel", fallback)
    return raw.strip().lower() if raw else fallback


def _apply_ratelimit_headers(response: Response, rate_result: Any) -> None:
    response.headers["RateLimit"] = rate_result.ratelimit_header()
    response.headers["RateLimit-Policy"] = rate_result.ratelimit_policy_header()


def _streaming_headers(rate_result: Any | None = None) -> dict[str, str]:
    headers = dict(SSE_HEADERS)
    if rate_result is not None:
        headers["RateLimit"] = rate_result.ratelimit_header()
        headers["RateLimit-Policy"] = rate_result.ratelimit_policy_header()
    return headers


def _build_envelope(
    *,
    request: Request,
    req: ChatRequest,
    account: AccountContext,
    request_id: str,
    idempotency_key: str | None,
    rate_remaining: int,
) -> ButlerEnvelope:
    return ButlerEnvelope(
        request_id=request_id,
        account_id=str(account.account_id),
        session_id=req.session_id,
        device_id=getattr(account, "device_id", None),
        channel=_channel(request, "api"),
        message=req.message,
        attachments=req.attachments,
        mode=req.mode,
        model=req.model,
        client={
            "locale": request.headers.get("X-Locale") or request.headers.get("Accept-Language"),
            "timezone": request.headers.get("X-Timezone"),
            "user_agent": request.headers.get("User-Agent"),
            "location": req.location,
        },
        gateway={
            "assurance_level": str(getattr(account, "assurance_level", "AAL1")),
            "idempotency_key": idempotency_key,
            "rate_limit_remaining": rate_remaining,
            "authenticated_user_id": str(getattr(account, "sub", account.account_id)),
            "tenant_id": str(getattr(account, "aid", account.account_id)),
            "ip_address": request.client.host if request.client else None,
        },
    )


async def _ensure_session(
    *,
    cache: Any,
    db: Any,
    account: AccountContext,
    session_id: str,
    channel: str,
) -> Any:
    session_mgr = ButlerSessionManager(redis=cache, db=db)
    return await session_mgr.get_or_create(
        session_id=session_id,
        account_id=account.account_id,
        channel=channel,
        assurance_level=getattr(account, "assurance_level", "AAL1"),
        device_id=getattr(account, "device_id", None),
    )


def _compose_safe_response(
    result: OrchestratorResult,
    locale: str = "en",
    timezone: str = "UTC",
) -> str:
    """Process orchestrator result through Runtime Spine to prevent response leaks."""
    envelopes: list[ToolResultEnvelope] = []
    
    for action in result.actions or []:
        action_dict = (
            action.model_dump()
            if hasattr(action, "model_dump")
            else (action if isinstance(action, dict) else {})
        )
        payload = action_dict.get("payload", {})
        if not isinstance(payload, dict):
            log.warning(
                "gateway_action_payload_not_dict",
                action_type=type(action).__name__,
                action_dict=str(action_dict)[:200],
            )
            continue
            
        data = payload.get("data")
        # Handle both boolean and string status values
        success = payload.get("success")
        if success is None:
            success = payload.get("status") == "success"
        elif isinstance(success, str):
            success = success.lower() in ("true", "success", "completed")
        
        tool_name = action_dict.get("type") or payload.get("tool_name", "tool")
        
        if success and isinstance(data, dict) and data:
            envelopes.append(
                ToolResultEnvelope.success(
                    tool_name=tool_name,
                    data=data,
                    user_visible=True,
                    safe_to_quote=True,
                )
            )

    if envelopes:
        composed = FinalResponseComposer.compose_from_multiple_tool_results(
            envelopes,
            locale=locale,
            timezone=timezone,
        )
        if composed:
            return composed

    content = result.content or ""

    try:
        ResponseValidator.validate_user_facing_response(content)
        return content
    except Exception as exc:
        log.warning(
            "response_validation_failed",
            error=str(exc),
            content_preview=content[:200] if content else None,
        )
        return ResponseValidator.sanitize_user_facing_response(content)


def _error_response(
    *,
    detail: str,
    request_id: str,
    session_id: str | None = None,
    status_code: int = status.HTTP_502_BAD_GATEWAY,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "type": "https://butler.lasmoid.ai/problems/gateway-upstream-failure",
            "title": "Gateway Upstream Failure",
            "status": status_code,
            "detail": detail,
            "request_id": request_id,
            "session_id": session_id,
        },
    )


# =============================================================================
# POST /chat
# =============================================================================


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    request: Request,
    response: Response,
    account: AccountContext = Depends(get_current_account),
    cache=Depends(get_cache),
) -> ChatResponse | JSONResponse:
    """Primary synchronous chat endpoint."""
    request_id = _request_id(request)
    idempotency_key = _idempotency_key(request)

    rate_limiter = RateLimiter(redis=cache, capacity=100, refill_rate=1.0)
    rate_result = await rate_limiter.check(account.account_id)
    _apply_ratelimit_headers(response, rate_result)

    idempotency = IdempotencyService(redis=cache)
    cached = await idempotency.check(idempotency_key, req.model_dump(mode="json"))
    if cached:
        return ChatResponse(**cached.body)

    envelope = _build_envelope(
        request=request,
        req=req,
        account=account,
        request_id=request_id,
        idempotency_key=idempotency_key,
        rate_remaining=rate_result.remaining,
    )

    try:
        async with _session_scope() as db:
            await _ensure_session(
                cache=cache,
                db=db,
                account=account,
                session_id=req.session_id,
                channel=envelope.channel,
            )

        internal_request = InternalRequest(
            service="orchestrator",
            method="POST",
            path="/api/v1/orchestrator/intake",
            data=envelope.model_dump(mode="json"),
            idempotency_key=idempotency_key,
        )
        upstream_response = await _orchestrator_client.call(internal_request)
        result_payload = upstream_response.json()
        
        # Check if orchestrator returned RFC 9457 Problem Details error format
        if "type" in result_payload and "status" in result_payload:
            # This is an error response from orchestrator, forward it as-is
            log.warning(
                "orchestrator_returned_error",
                request_id=request_id,
                session_id=req.session_id,
                error_type=result_payload.get("type"),
                error_status=result_payload.get("status"),
                error_detail=result_payload.get("detail"),
            )
            return JSONResponse(
                status_code=result_payload.get("status", 502),
                content=result_payload,
            )
        
        result_payload.setdefault("session_id", envelope.session_id)
        result_payload.setdefault("request_id", envelope.request_id)
        result = OrchestratorResult(**result_payload)
    except Exception as exc:
        log.exception(
            "gateway_chat_upstream_failed",
            request_id=request_id,
            session_id=req.session_id,
            account_id=str(account.account_id),
            error=str(exc),
        )
        return _error_response(
            detail="Failed to complete chat request.",
            request_id=request_id,
            session_id=req.session_id,
        )

    safe_response = _compose_safe_response(
        result,
        locale=request.headers.get("X-Locale", "en"),
        timezone=request.headers.get("X-Timezone", "UTC"),
    )

    chat_response = ChatResponse(
        response=safe_response,
        session_id=req.session_id,
        request_id=request_id,
        workflow_id=result.workflow_id,
        actions_taken=[
            a.model_dump(mode="json") if hasattr(a, "model_dump") else a
            for a in (result.actions or [])
        ],
        requires_approval=result.requires_approval,
        approval_id=result.approval_id,
    )

    await idempotency.store(
        idempotency_key,
        req.model_dump(mode="json"),
        chat_response.model_dump(mode="json"),
    )
    return chat_response


# =============================================================================
# POST /chat/stream
# =============================================================================


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    request: Request,
    account: AccountContext = Depends(get_current_account),
    cache=Depends(get_cache),
) -> StreamingResponse:
    """Streaming chat via SSE."""
    request_id = _request_id(request)
    idempotency_key = _idempotency_key(request)

    rate_limiter = RateLimiter(redis=cache, capacity=60, refill_rate=1.0)
    rate_result = await rate_limiter.check(account.account_id)

    envelope = _build_envelope(
        request=request,
        req=req,
        account=account,
        request_id=request_id,
        idempotency_key=idempotency_key,
        rate_remaining=rate_result.remaining,
    )

    last_event_id: int | None = None
    raw_last_event_id = request.headers.get("Last-Event-ID")
    if raw_last_event_id and raw_last_event_id.isdigit():
        last_event_id = int(raw_last_event_id)

    bridge = ButlerStreamBridge(
        session_id=req.session_id,
        account_id=account.account_id,
        redis=cache,
        request_id=request_id,
        last_event_id=last_event_id,
    )

    async def _stream_generator() -> AsyncGenerator[str, None]:
        try:
            async with _session_scope() as db:
                await _ensure_session(
                    cache=cache,
                    db=db,
                    account=account,
                    session_id=req.session_id,
                    channel=envelope.channel,
                )

                from core.deps import get_orchestrator_service

                orchestrator = await get_orchestrator_service(db, cache)
                event_gen = orchestrator.intake_streaming(envelope)

                async for frame in bridge.as_sse(event_gen):
                    yield frame
        except Exception as exc:
            log.exception(
                "gateway_chat_stream_failed",
                request_id=request_id,
                session_id=req.session_id,
                account_id=str(account.account_id),
                error=str(exc),
            )
            yield bridge._sse_frame(
                {
                    "event": "error",
                    "type": "https://butler.lasmoid.ai/problems/gateway-upstream-failure",
                    "status": 502,
                    "detail": "Streaming request failed.",
                    "retryable": False,
                }
            )
            yield bridge._sse_frame({"event": "done", "session_id": req.session_id})

    return StreamingResponse(
        _stream_generator(),
        media_type="text/event-stream",
        headers=_streaming_headers(rate_result),
    )


# =============================================================================
# GET /stream/{session_id}
# =============================================================================


@router.get("/stream/{session_id}")
async def stream_session(
    session_id: str,
    request: Request,
    account: AccountContext = Depends(get_current_account),
    cache=Depends(get_cache),
) -> StreamingResponse:
    """Subscribe to an existing session event stream via SSE."""
    raw_last_event_id = request.headers.get("Last-Event-ID")
    last_event_id: int | None = None
    if raw_last_event_id and raw_last_event_id.isdigit():
        last_event_id = int(raw_last_event_id)

    async def _event_tap() -> AsyncGenerator[str, None]:
        pubsub = cache.pubsub()
        channel_key = f"butler:events:{session_id}"
        await pubsub.subscribe(channel_key)

        next_event_id = (last_event_id or 0) + 1
        try:
            while True:
                if await request.is_disconnected():
                    break

                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=14.0,
                )
                if message and message.get("type") == "message":
                    raw = message["data"]
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    data = json.loads(raw)

                    yield f"id: {next_event_id}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    next_event_id += 1

                    if data.get("event") in {"done", "stream_final", "stream_error"}:
                        break
                else:
                    yield ": keepalive\n\n"
        finally:
            await pubsub.unsubscribe(channel_key)
            await pubsub.close()

    return StreamingResponse(
        _event_tap(),
        media_type="text/event-stream",
        headers=dict(SSE_HEADERS),
    )


# =============================================================================
# WS /ws/chat
# =============================================================================


@router.websocket("/ws/chat")
async def websocket_chat(
    websocket: WebSocket,
    cache=Depends(get_cache),
    transport_edge=Depends(get_hermes_transport),
    mux=Depends(get_ws_mux),
) -> None:
    """Bidirectional real-time chat channel."""
    token = websocket.query_params.get("token")
    init_payload: dict[str, Any] = {}

    if not token:
        await websocket.accept()
        try:
            raw = await websocket.receive_text()
            init_payload = json.loads(raw)
            token = init_payload.get("auth") or init_payload.get("token")
        except WebSocketDisconnect:
            return
        except Exception:
            await websocket.close(code=4000, reason="Missing auth token")
            return

    transport_ctx = await transport_edge.connect(websocket, token)
    if not transport_ctx:
        return

    session_id = str(init_payload.get("session_id") or uuid.uuid4())
    account = transport_ctx.account
    object.__setattr__(account, "session_id", session_id)

    mux_task: asyncio.Task | None = None
    ping_task: asyncio.Task | None = None

    try:
        async with _session_scope() as db:
            await _ensure_session(
                cache=cache,
                db=db,
                account=account,
                session_id=session_id,
                channel="websocket",
            )

            from core.deps import get_orchestrator_service

            orchestrator = await get_orchestrator_service(db, cache)

            mux_task = asyncio.create_task(mux.handle_mux_stream(transport_ctx))
            ping_task = asyncio.create_task(transport_edge.run_ping_pong_loop(transport_ctx))

            while True:
                try:
                    raw = await websocket.receive_text()
                except WebSocketDisconnect:
                    break

                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json(
                        {
                            "event": "error",
                            "type": "https://butler.lasmoid.ai/problems/invalid-request",
                            "status": 400,
                            "detail": "Invalid JSON payload.",
                        }
                    )
                    continue

                if "action" in payload:
                    continue

                message = str(payload.get("message", "") or "").strip()
                if not message:
                    continue

                request_id = str(uuid.uuid4())
                envelope = ButlerEnvelope(
                    request_id=request_id,
                    account_id=str(account.account_id),
                    session_id=session_id,
                    device_id=getattr(account, "device_id", None),
                    channel="websocket",
                    message=message,
                    attachments=payload.get("attachments", []),
                    model=payload.get("model"),
                    mode=str(payload.get("mode", "auto")),
                    gateway={
                        "assurance_level": str(getattr(account, "assurance_level", "AAL1")),
                    },
                )

                bridge = ButlerStreamBridge(
                    session_id=session_id,
                    account_id=account.account_id,
                    redis=cache,
                    request_id=request_id,
                )
                event_stream = orchestrator.intake_streaming(envelope)
                await bridge.forward_to_ws(websocket, event_stream)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.exception(
            "gateway_websocket_chat_failed",
            session_id=session_id,
            account_id=str(getattr(account, "account_id", "unknown")),
            error=str(exc),
        )
        with suppress(Exception):
            await websocket.send_json(
                {
                    "event": "error",
                    "type": "https://butler.lasmoid.ai/problems/gateway-upstream-failure",
                    "status": 502,
                    "detail": "WebSocket chat failed.",
                }
            )
    finally:
        if ping_task is not None:
            ping_task.cancel()
        if mux_task is not None:
            mux_task.cancel()
        await transport_edge.disconnect(session_id)


# =============================================================================
# POST /sessions/bootstrap
# =============================================================================


@router.post("/sessions/bootstrap", response_model=SessionBootstrapResponse)
async def session_bootstrap(
    request: Request,
    account: AccountContext = Depends(get_current_account),
    cache=Depends(get_cache),
) -> SessionBootstrapResponse:
    """Create and persist a new Butler session."""
    request_id = _request_id(request)
    channel = _channel(request, "api")

    async with _session_scope() as db:
        session_mgr = ButlerSessionManager(redis=cache, db=db)
        session = await session_mgr.bootstrap(
            account_id=account.account_id,
            channel=channel,
            device_id=request.headers.get("X-Device-ID"),
        )

    return SessionBootstrapResponse(
        session_id=session.session_id,
        request_id=request_id,
        resume_token=session.resume_token,
    )


# =============================================================================
# GET /directory
# =============================================================================


@router.get("/directory")
async def get_channel_directory(
    account: AccountContext = Depends(get_current_account),
) -> dict[str, Any]:
    """Expose the Butler channel directory to authenticated clients."""
    return {
        "directory": {},
        "display": {},
        "note": "Butler-owned channel directory implementation pending",
    }


# =============================================================================
# POST /voice/process
# =============================================================================


@router.post("/voice/process", response_model=VoiceProcessResponse)
async def voice_process(
    req: VoiceProcessRequest,
    request: Request,
    response: Response,
    account: AccountContext = Depends(get_current_account),
    cache=Depends(get_cache),
) -> VoiceProcessResponse | JSONResponse:
    """Voice over HTTP: STT -> Orchestrator -> TTS."""
    from services.audio.service import AudioService

    voice_limiter = RateLimiter(
        redis=cache,
        capacity=20,
        refill_rate=round(20 / 60, 4),
        window_s=60,
        key_prefix="ratelimit:voice:",
    )
    rate_result = await voice_limiter.check(account.account_id)
    _apply_ratelimit_headers(response, rate_result)

    audio_service = AudioService()
    session_id = req.session_id or str(uuid.uuid4())
    request_id = _request_id(request)

    try:
        transcript_result = await audio_service.transcribe(req.audio_data)
        transcript = (
            transcript_result.transcript
            if hasattr(transcript_result, "transcript")
            else str(transcript_result.get("text", "")).strip()
        )

        if not transcript:
            return VoiceProcessResponse(
                session_id=session_id,
                transcript="",
                response="",
                audio_data=None,
            )

        envelope = ButlerEnvelope(
            request_id=request_id,
            account_id=str(account.account_id),
            session_id=session_id,
            device_id=getattr(account, "device_id", None),
            channel="voice",
            message=transcript,
            gateway={
                "assurance_level": str(getattr(account, "assurance_level", "AAL1")),
            },
        )

        async with _session_scope() as db:
            await _ensure_session(
                cache=cache,
                db=db,
                account=account,
                session_id=session_id,
                channel="voice",
            )

            from core.deps import get_orchestrator_service

            orchestrator = await get_orchestrator_service(db, cache)
            result = await orchestrator.intake(envelope)

        answer = result.content
        tts_result = await audio_service.synthesize(answer)
        audio_output = (
            tts_result.audio_data
            if hasattr(tts_result, "audio_data")
            else tts_result.get("audio_data")
        )
        audio_b64 = base64.b64encode(audio_output).decode("utf-8") if audio_output else None

        return VoiceProcessResponse(
            session_id=session_id,
            transcript=transcript,
            response=answer,
            audio_data=audio_b64,
        )
    except Exception as exc:
        log.exception(
            "gateway_voice_process_failed",
            request_id=request_id,
            session_id=session_id,
            account_id=str(account.account_id),
            error=str(exc),
        )
        return _error_response(
            detail="Voice processing failed.",
            request_id=request_id,
            session_id=session_id,
        )