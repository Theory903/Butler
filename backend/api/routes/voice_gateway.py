import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from core.deps import get_cache
from core.deps import get_orchestrator_service as _get_orchestrator
from domain.orchestrator.meeting_telemetry import meeting_telemetry
from infrastructure.database import async_session_factory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/voice", tags=["voice", "realtime"])


def get_audio_service() -> Any:
    from services.audio.service import AudioService

    return AudioService()


@router.websocket("/stream")
async def voice_stream(
    websocket: WebSocket, audio_svc: Any = Depends(get_audio_service), cache=Depends(get_cache)
):
    """
    Jarvis Voice Stream - Bridging PCM microphone inputs dynamically to Butler
    PlatformId.VOICE orchestrator interface.
    """
    await websocket.accept()
    session_id = f"voice_session_{id(websocket)}"
    accumulated_pcm = bytearray()

    # Notify meeting telemetry hook
    meeting_telemetry.start_session(session_id)

    logger.info(f"[VoiceGateway] Session {session_id} connected.")

    try:
        while True:
            # We receive message payloads. They can be bytes (PCM wrapper) or JSON (control/events)
            message = await websocket.receive()

            if "bytes" in message:
                chunk = message["bytes"]
                accumulated_pcm.extend(chunk)

                # Simple VAD stub - flush transcript once payload hits 32000 bytes (~1 second raw 16kHz)
                if len(accumulated_pcm) >= 32000:
                    pcm_out = bytes(accumulated_pcm)
                    accumulated_pcm.clear()

                    try:
                        # 1. Transcribe the raw audio
                        transcript_res = await audio_svc.transcribe(pcm_out)
                        text = transcript_res.get("text", "").strip()

                        if text:
                            logger.info(f"[VoiceGateway] Transcribed: {text}")

                            # Track user side transaction
                            meeting_telemetry.append_transcript(session_id, text, role="user")

                            # 2. Re-route into Butler's Hermes Agent Backend
                            from api.routes.gateway import ChatRequest

                            req = ChatRequest(message=text, session_id=session_id)

                            async with async_session_factory() as db:
                                orchestrator_svc = await _get_orchestrator(db, cache)
                                response = await orchestrator_svc.intake(
                                    req,
                                    account_id="jarvis_system",  # System account emulation
                                    platform="voice",
                                )

                            answer = response.content

                            # Track AI side transaction
                            meeting_telemetry.append_transcript(
                                session_id, answer, role="assistant"
                            )

                            # 3. Stream text back to the client immediately
                            await websocket.send_json(
                                {"type": "transcript.text.done", "text": answer}
                            )

                            # 4. Generate TTS and broadcast the bytes downstream
                            tts_res = await audio_svc.synthesize(answer)
                            audio_output = tts_res.get("audio_data")
                            if audio_output:
                                # Send binary audio mapping back through the websocket
                                await websocket.send_bytes(audio_output)

                    except Exception as e:
                        logger.error(f"[VoiceGateway] Error routing inference: {e}")

            elif "text" in message:
                try:
                    payload = json.loads(message["text"])
                    if payload.get("type") == "session.close":
                        break
                except Exception:
                    pass

    except WebSocketDisconnect:
        logger.info(f"[VoiceGateway] Client disconnected session: {session_id}")
    finally:
        # Upon termination, trigger meeting summary
        async with async_session_factory() as db:
            orchestrator_svc = await _get_orchestrator(db, cache)
            await meeting_telemetry.end_session(session_id, orchestrator_svc)
