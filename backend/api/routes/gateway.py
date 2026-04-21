"""Gateway chat + health routes — thin HTTP layer only.

Phase 3: Real SSE + WebSocket paths wired to OrchestratorService.intake_streaming().
No business logic here. No tool calls. No memory writes. No Hermes imports.

Endpoints:
  POST /chat                    — synchronous chat (non-streaming)
  POST /chat/stream             — streaming chat via SSE
  GET  /stream/{session_id}     — SSE event subscription for existing workflow
  WS   /ws/chat                 — WebSocket real-time channel
  POST /sessions/bootstrap      — new session creation
  GET  /channels                — Hermes channel directory
  POST /voice/process           — voice stub (Phase 5)
  POST/GET /mcp                 — MCP edge terminator stub
  GET  /health/live             — liveness probe
  GET  /health/ready            — readiness probe (DB + Redis)
  GET  /health/startup          — startup probe
"""

from __future__ import annotations

import asyncio
import json
import uuid
import structlog
from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from core.deps import get_cache, get_db, get_hermes_transport, get_ws_mux
from core.envelope import ButlerEnvelope
from domain.auth.contracts import AccountContext
from domain.auth.exceptions import GatewayErrors
from infrastructure.database import engine, async_session_factory
from services.auth.jwt import get_jwks_manager
from services.gateway.auth_middleware import JWTAuthMiddleware
from services.gateway.idempotency import IdempotencyService
from services.gateway.rate_limiter import RateLimiter
from services.gateway.session_manager import ButlerSessionManager
from services.gateway.stream_bridge import ButlerStreamBridge, SSE_HEADERS
from core.resilient_client import ResilientClient, InternalRequest
from infrastructure.config import settings
from integrations.hermes.gateway.channel_directory import load_directory, format_directory_for_display
from services.orchestrator.service import OrchestratorService

# Shared Resilient Client for Orchestrator communication
# In Butler v3.0, the Gateway routes to the federated Intelligence Engine via this resilient pipe.
_orch_client = ResilientClient(
    source_service="gateway",
    base_url=settings.ORCHESTRATOR_URL,
    timeout=30.0
)

log = structlog.get_logger(__name__)
router = APIRouter(tags=["gateway"])


# ── Dependency: authenticated account ────────────────────────────────────────

async def get_current_account(
    request: Request,
    cache=Depends(get_cache),
) -> AccountContext:
    """Verify Bearer token and return AccountContext."""
    middleware = JWTAuthMiddleware(jwks=get_jwks_manager(), redis=cache)
    authorization = request.headers.get("Authorization")
    ctx = await middleware.authenticate(authorization)
    object.__setattr__(ctx, "device_id", request.headers.get("X-Device-ID"))
    return ctx


# ── Request / Response schemas ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4096)
    session_id: str = Field(min_length=1, max_length=64)
    attachments: list[dict] = Field(default_factory=list)
    location: dict | None = None
    mode: str = "auto"
    stream: bool = False
    model: str | None = None  # provider/model selection, e.g. "cloud-deepseek"


class ChatResponse(BaseModel):
    response: str
    session_id: str
    request_id: str
    workflow_id: str | None = None
    actions_taken: list[dict] = Field(default_factory=list)
    requires_approval: bool = False
    approval_id: str | None = None


class VoiceProcessRequest(BaseModel):
    audio_data: str = Field(..., description="base64 audio bytes")
    format: str = "wav"
    session_id: str | None = None


class VoiceProcessResponse(BaseModel):
    session_id: str
    transcript: str
    response: str
    audio_data: str | None = None


class SessionBootstrapResponse(BaseModel):
    session_id: str
    request_id: str
    resume_token: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_envelope(
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
        device_id=account.device_id,
        channel=request.headers.get("X-Butler-Channel", "api"),
        message=req.message,
        attachments=req.attachments,
        mode=req.mode,
        location=req.location,
        model=req.model,
        assurance_level=str(account.assurance_level),
        idempotency_key=idempotency_key,
        rate_limit_remaining=rate_remaining,
    )


async def _get_orchestrator(db, cache):
    """Resolve OrchestratorService using the production-grade manager."""
    from core.deps import get_orchestrator_service
    return await get_orchestrator_service(db, cache)


# ── POST /chat — synchronous ──────────────────────────────────────────────────

from fastapi import Response

@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    request: Request,
    response: Response,
    account: AccountContext = Depends(get_current_account),
    cache=Depends(get_cache),
) -> ChatResponse:
    """Primary chat endpoint — synchronous. Gateway never calls Memory/Tools directly."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    idempotency_key = request.headers.get("Idempotency-Key")

    # 1. Rate limit (Lua Token Bucket)
    rate_result = await RateLimiter(redis=cache, capacity=100, refill_rate=1.0).check(
        account.account_id
    )
    
    # IETF draft-ietf-httpapi-ratelimit-headers composite headers
    response.headers["RateLimit"] = rate_result.ratelimit_header()
    response.headers["RateLimit-Policy"] = rate_result.ratelimit_policy_header()

    # 2. Idempotency check (With Hashes!)
    idempotency = IdempotencyService(redis=cache)
    cached = await idempotency.check(idempotency_key, req.model_dump())
    if cached:
        return ChatResponse(**cached.body)

    envelope = _build_envelope(request, req, account, request_id, idempotency_key, rate_result.remaining)

    async with async_session_factory() as db:
        session_mgr = ButlerSessionManager(redis=cache, db=db)
        session = await session_mgr.get_or_create(
            session_id=req.session_id,
            account_id=account.account_id,
            channel=envelope.channel,
            assurance_level=account.assurance_level,
            device_id=account.device_id,
        )

        try:
            # 3. Resilient call to Orchestrator
            call_request = InternalRequest(
                service="orchestrator",
                method="POST",
                path="/api/v1/orchestrator/intake",
                data=envelope.model_dump(),
                idempotency_key=idempotency_key
            )
            resp = await _orch_client.call(call_request)
            if resp.status_code >= 400:
                raise Exception(f"Orchestrator returned {resp.status_code}: {resp.text}")
            result_data = resp.json()
            from domain.orchestrator.contracts import OrchestratorResult
            result = OrchestratorResult(**result_data)
        except Exception as exc:
            log.exception("orchestrator_error", session_id=req.session_id, error=str(exc))
            chat_response = ChatResponse(
                response=f"Butler encountered an error: {str(exc)}",
                session_id=req.session_id,
                request_id=request_id,
            )
            await idempotency.store(idempotency_key, req.model_dump(), chat_response.model_dump())
            return chat_response

    chat_response = ChatResponse(
        response=result.content,
        session_id=req.session_id,
        request_id=request_id,
        workflow_id=result.workflow_id,
        actions_taken=result.actions,
        requires_approval=result.requires_approval,
        approval_id=result.approval_id,
    )
    await idempotency.store(idempotency_key, req.model_dump(), chat_response.model_dump())
    return chat_response


# ── POST /chat/stream — SSE-wrapped intake ────────────────────────────────────

@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    request: Request,
    response: Response,
    account: AccountContext = Depends(get_current_account),
    cache=Depends(get_cache),
) -> StreamingResponse:
    """Streaming chat via SSE. Client receives ButlerEvent frames as they arrive.

    Typical frame sequence:
      stream_start → stream_token* → stream_tool_call? → stream_tool_result?
      → [stream_approval_required | stream_final | stream_error] → done
    """
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    idempotency_key = request.headers.get("Idempotency-Key")

    rate_result = await RateLimiter(redis=cache, capacity=60, refill_rate=1.0).check(
        account.account_id
    )
    
    # IETF RateLimit composite headers
    response.headers["RateLimit"] = rate_result.ratelimit_header()
    response.headers["RateLimit-Policy"] = rate_result.ratelimit_policy_header()

    envelope = _build_envelope(request, req, account, request_id, idempotency_key, rate_result.remaining)

    # Extract Last-Event-ID for stream resume support
    last_event_id = None
    hdr = request.headers.get("Last-Event-ID")
    if hdr and hdr.isdigit():
        last_event_id = int(hdr)

    bridge = ButlerStreamBridge(
        session_id=req.session_id,
        account_id=account.account_id,
        redis=cache,
        request_id=request_id,
        last_event_id=last_event_id,
    )

    async def _stream_generator():
        async with async_session_factory() as db:
            session_mgr = ButlerSessionManager(redis=cache, db=db)
            session = await session_mgr.get_or_create(
                session_id=req.session_id,
                account_id=account.account_id,
                channel=envelope.channel,
                assurance_level=account.assurance_level,
            )
            try:
                orchestrator = await _get_orchestrator(db, cache)
                async with session_mgr.hermes_context(session):
                    event_gen = orchestrator.intake_streaming(envelope)
                    async for frame in bridge.as_sse(event_gen):
                        yield frame
            except Exception as exc:
                log.exception("stream_generator_error", session_id=req.session_id)
                yield bridge._sse_frame({
                    "event": "error",
                    "type": "https://butler.lasmoid.ai/errors/internal-error",
                    "status": 500,
                    "detail": str(exc),
                    "retryable": False,
                })
                yield bridge._sse_frame({"event": "done", "session_id": req.session_id})

    return StreamingResponse(
        _stream_generator(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


# ── GET /stream/{session_id} — subscribe to existing session events ───────────

@router.get("/stream/{session_id}")
async def stream_session(
    session_id: str,
    request: Request,
    account: AccountContext = Depends(get_current_account),
    cache=Depends(get_cache),
) -> StreamingResponse:
    """SSE subscription endpoint for an existing session_id.

    Supports Last-Event-ID resume: on reconnect the client sends the id of
    the last event it received; we replay from the next sequence number.
    Yields keepalive comments every 15 s when no events arrive.
    """
    # Parse Last-Event-ID for resume semantics
    last_event_id_raw = request.headers.get("Last-Event-ID")
    last_event_id: int | None = None
    if last_event_id_raw and last_event_id_raw.isdigit():
        last_event_id = int(last_event_id_raw)

    bridge = ButlerStreamBridge(
        session_id=session_id,
        account_id=account.account_id,
        last_event_id=last_event_id,
    )
    event_counter = (last_event_id or 0) + 1

    async def _event_tap():
        nonlocal event_counter
        pubsub = cache.pubsub()
        channel_key = f"butler:events:{session_id}"
        await pubsub.subscribe(channel_key)

        try:
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=14.0,
                )
                if message and message.get("type") == "message":
                    raw = message["data"]
                    if isinstance(raw, bytes):
                        raw = raw.decode()
                    data = json.loads(raw)
                    # Emit id: field on every frame for Last-Event-ID tracking
                    yield f"id: {event_counter}\ndata: {json.dumps(data)}\n\n"
                    event_counter += 1
                    if data.get("event") in ("done", "stream_final", "stream_error"):
                        break
                else:
                    yield ": keepalive\n\n"

                if await request.is_disconnected():
                    break
        finally:
            await pubsub.unsubscribe(channel_key)
            await pubsub.close()

    return StreamingResponse(
        _event_tap(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


# ── WebSocket /ws/chat — real-time bidirectional channel ─────────────────────

@router.websocket("/ws/chat")
async def websocket_chat(
    websocket: WebSocket,
    cache=Depends(get_cache),
    transport_edge=Depends(get_hermes_transport),
    mux=Depends(get_ws_mux),
):
    """Hardened real-time bidirectional channel using Hermes Integration Layer.
    
    1. Edge Hardening: Authenticates and rate-limits via HermesTransportEdge.
    2. Resilience: Background ping/pong prevents zombie connections.
    3. Multiplexing: Supports multiple data topics via WebSocketMultiplexer.
    """
    # WS handshake is already accepted inside HermesTransportEdge.connect
    # but we need the token from the first message OR query param.
    # OpenClaw standards suggest 'token' query param or 'auth' in first JSON.
    
    token = websocket.query_params.get("token")
    init_payload = {}
    
    if not token:
        await websocket.accept()
        try:
            raw = await websocket.receive_text()
            init_payload = json.loads(raw)
            token = init_payload.get("auth") or init_payload.get("token")
        except Exception:
            await websocket.close(code=4000, reason="Missing Auth Token")
            return

    # 1. Transport Hardening (Authentication + Leaky Bucket RL)
    transport_ctx = await transport_edge.connect(websocket, token)
    if not transport_ctx:
        return 

    session_id = init_payload.get("session_id") or str(uuid.uuid4())
    account = transport_ctx.account
    account.session_id = session_id

    # 2. Restore Prod-Level Chat Orchestration
    async with async_session_factory() as db:
        session_mgr = ButlerSessionManager(redis=cache, db=db)
        session = await session_mgr.get_or_create(
            session_id=session_id,
            account_id=account.account_id,
            channel="web",
        )

        try:
            # Run mux commands in background for topics/presence
            mux_task = asyncio.create_task(mux.handle_mux_stream(transport_ctx))
            ping_task = asyncio.create_task(transport_edge.run_ping_pong_loop(transport_ctx))

            # Main Chat Loop (The Prod Implementation)
            while True:
                try:
                    raw = await websocket.receive_text()
                    msg = json.loads(raw)
                    
                    # Handle Mux commands or Direct Chat
                    if "action" in msg:
                        # Pass complex mux actions to the multiplexer
                        # (Mux loop is also running but we check for chat here)
                        pass
                        
                    user_message = msg.get("message", "")
                    if not user_message:
                        continue

                    request_id = str(uuid.uuid4())
                    envelope = ButlerEnvelope(
                        request_id=request_id,
                        account_id=account.account_id,
                        session_id=session_id,
                        device_id=None,
                        channel="web",
                        message=user_message,
                        attachments=msg.get("attachments", []),
                        assurance_level=account.assurance_level,
                    )

                    bridge = ButlerStreamBridge(
                        session_id=session_id,
                        account_id=account.account_id,
                        redis=cache,
                        request_id=request_id,
                    )

                    from core.deps import get_orchestrator_service
                    orchestrator = await get_orchestrator_service(db, cache)
                    
                    async with session_mgr.hermes_context(session):
                        event_stream = orchestrator.intake_streaming(envelope)
                        await bridge.forward_to_ws(websocket, event_stream)

                except (WebSocketDisconnect, json.JSONDecodeError):
                    break

        except Exception as e:
            log.error("websocket_hybrid_error", error=str(e), session_id=session_id)
        finally:
            ping_task.cancel()
            mux_task.cancel()
            await transport_edge.disconnect(session_id)


# ── POST /sessions/bootstrap ──────────────────────────────────────────────────

@router.post("/sessions/bootstrap", response_model=SessionBootstrapResponse)
async def session_bootstrap(
    request: Request,
    account: AccountContext = Depends(get_current_account),
    cache=Depends(get_cache),
) -> SessionBootstrapResponse:
    """Create a new Butler session. Returns session_id and resume_token."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    channel = request.headers.get("X-Butler-Channel", "api")

    async with async_session_factory() as db:
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


# ── GET /channels — Hermes channel directory (read-only) ─────────────────────

@router.get("/channels")
async def get_channels(account: AccountContext = Depends(get_current_account)):
    """Expose Hermes Channel Directory to the frontend. Read-only reference."""
    return {
        "directory": load_directory(),
        "display": format_directory_for_display(),
    }


# ── POST /voice/process — Phase 5 ─────────────────────────────────────

@router.post("/voice/process", response_model=VoiceProcessResponse)
async def voice_process(
    req: VoiceProcessRequest,
    request: Request,
    account: AccountContext = Depends(get_current_account),
    cache=Depends(get_cache),
):
    """Voice processing over HTTP — STT → Orchestrator → TTS.

    Rate limited separately from /chat at a tighter budget because this
    endpoint chains 3 expensive operations (transcription, LLM, synthesis).
    """
    from services.audio.service import AudioService

    # Rate limit: 20 req/min for voice (tighter than /chat's 100 req/min)
    voice_limiter = RateLimiter(
        redis=cache,
        capacity=20,
        refill_rate=round(20 / 60, 4),
        window_s=60,
        key_prefix="ratelimit:voice:",
    )
    rate_result = await voice_limiter.check(account.account_id)
    request.state.response_headers = {
        "RateLimit": rate_result.ratelimit_header(),
        "RateLimit-Policy": rate_result.ratelimit_policy_header(),
    }

    audio_svc = AudioService()
    session_id = req.session_id or str(uuid.uuid4())


    try:
        # 1. Transcribe the raw audio
        transcript_res = await audio_svc.transcribe(req.audio_data)
        text = transcript_res.transcript if hasattr(transcript_res, "transcript") else transcript_res.get("text", "").strip()
        
        if not text:
            return VoiceProcessResponse(
                session_id=session_id,
                transcript="",
                response="",
                audio_data=None,
            )

        # 2. Re-route into Butler's Orchestrator
        async with async_session_factory() as db:
            orchestrator = await _get_orchestrator(db, cache)
            envelope = ButlerEnvelope(
                request_id=str(uuid.uuid4()),
                account_id=str(account.account_id),
                session_id=session_id,
                device_id=None,
                channel="voice",
                message=text,
                assurance_level=account.assurance_level,
            )
            result = await orchestrator.intake(envelope)
            
        answer = result.content
        
        # 3. Generate TTS 
        tts_res = await audio_svc.synthesize(answer)
        audio_output = tts_res.audio_data if hasattr(tts_res, "audio_data") else tts_res.get("audio_data")
        
        import base64
        audio_b64 = base64.b64encode(audio_output).decode("utf-8") if audio_output else None

        return VoiceProcessResponse(
            session_id=session_id,
            transcript=text,
            response=answer,
            audio_data=audio_b64,
        )
    except Exception as exc:
        log.exception("voice_process_error", error=str(exc))
        raise GatewayErrors.INTERNAL_ERROR from exc


# NOTE: /mcp POST and GET endpoints have been moved to api/routes/mcp.py
# and registered in main.py as mcp_router at prefix /api/v1.
# The /ws/chat, /voice/process, and all streaming routes remain here.

# NOTE: health probes have been moved to core/health.py and are registered in main.py
