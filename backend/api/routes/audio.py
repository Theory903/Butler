import base64
import json
import logging
from typing import Any, Optional, List
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel, Field

from services.audio.models import TranscribeResult, MeetingTranscript, TTSResult, MusicMatch

logger = logging.getLogger(__name__)

# ─── Dependencies ───

async def get_audio_service() -> Any:
    from services.audio import AudioService

    svc = AudioService()
    try:
        yield svc
    finally:
        await svc.close()

router = APIRouter(prefix="/audio", tags=["audio"])

# ─── Request Models ───

class STTRequest(BaseModel):
    audio_data: str = Field(..., description="Base64 encoded audio data")
    language: Optional[str] = "en"
    quality_mode: str = "balanced"

class MeetingRequest(BaseModel):
    audio_data: str
    min_speakers: int = 1
    max_speakers: int = 10
    identify_speakers: bool = False

class EnrollmentRequest(BaseModel):
    account_id: str
    audio_data: str

class TTSRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None
    voice_reference: Optional[str] = None
    consent_verified: bool = False

class MusicIDRequest(BaseModel):
    audio_data: str

# ─── REST Endpoints ───

@router.post("/stt", response_model=TranscribeResult)
async def transcribe(req: STTRequest, svc: Any = Depends(get_audio_service)):
    """Convert speech to text with dual-strategy pass."""
    return await svc.transcribe(req.audio_data, req.language, req.quality_mode)

@router.post("/meeting", response_model=MeetingTranscript)
async def process_meeting(req: MeetingRequest, svc: Any = Depends(get_audio_service)):
    """Process a meeting audio file with diarization and multi-speaker transcription."""
    return await svc.process_meeting(
        req.audio_data, 
        req.min_speakers, 
        req.max_speakers,
        req.identify_speakers
    )

@router.post("/enroll")
async def enroll_voice(req: EnrollmentRequest, svc: Any = Depends(get_audio_service)):
    """Enrolls a user's voice for future speaker identification."""
    success = await svc.enroll_user_voice(req.account_id, req.audio_data)
    if not success:
        raise HTTPException(status_code=500, detail="Voice enrollment failed")
    return {"status": "success", "message": f"Voice enrolled for account {req.account_id}"}

@router.post("/tts")
async def synthesize(req: TTSRequest, svc: Any = Depends(get_audio_service)):
    """Synthesize text to speech with optional voice cloning."""
    result = await svc.synthesize(
        req.text, 
        req.voice_id, 
        req.voice_reference, 
        req.consent_verified
    )
    # Convert bytes to b64 for JSON response
    return {
        "audio_base64": base64.b64encode(result.audio_data).decode("utf-8"),
        "duration_ms": result.duration_ms,
        "format": result.format
    }

@router.post("/music/identify", response_model=MusicMatch)
async def identify_music(req: MusicIDRequest, svc: Any = Depends(get_audio_service)):
    """Identify music from audio fingerprint."""
    return await svc.identify_music(req.audio_data)

# ─── Streaming WebSocket ───

@router.websocket("/stream")
async def audio_stream(websocket: WebSocket, svc: Any = Depends(get_audio_service)):
    """
    WebSocket endpoint for real-time audio streaming.
    Protocol:
    - Client sends: { "type": "audio", "data": "base64_chunk" }
    - Server sends: { "type": "partial", "transcript": "..." }
    - Server sends: { "type": "final", "transcript": "...", "confidence": 0.95 }
    """
    await websocket.accept()
    logger.info("audio_stream_connected")
    
    # In a prod scenario, we use a buffer and VAD for endpointing
    # This is a simplified version of the streaming logic
    from services.audio.errors import AudioError

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "audio":
                chunk_b64 = message.get("data")
                # Process the chunk (simulated streaming path)
                # In a real impl, we'd feed this into a StreamingSTT class
                try:
                    # In streaming mode, we can attempt identification on the chunk
                    account_id = await svc.identity.identify_speaker(base64.b64decode(chunk_b64))
                    
                    result = await svc.transcribe(chunk_b64, quality_mode="fast")
                    await websocket.send_json({
                        "type": "final",
                        "transcript": result.transcript,
                        "confidence": result.confidence,
                        "speaker_id": f"USER:{account_id}" if account_id else "UNKNOWN"
                    })
                except AudioError as e:
                    # Specific audio errors (e.g. no speech) don't close the socket
                    await websocket.send_json({
                        "type": "error",
                        "code": getattr(e, "extensions", {}).get("code", "unknown"),
                        "detail": e.detail
                    })

    except WebSocketDisconnect:
        logger.info("audio_stream_disconnected")
    except Exception as e:
        logger.error("audio_stream_error", error=str(e))
        await websocket.close(code=1011)
