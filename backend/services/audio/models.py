"""AudioModelProxy with layered fallback (v3.1).

Fallback chain:
  1. Local GPU worker  (AUDIO_GPU_ENDPOINT — self-hosted Parakeet/Whisper/XTTS)
  2. OpenAI Whisper   (STT) / OpenAI TTS (gpt-4o-mini)
  3. Dev mock         (only when ENVIRONMENT == development)
"""
from __future__ import annotations

import base64
import io
import logging
import time
from typing import Optional, List

import httpx
from pydantic import BaseModel, Field

from infrastructure.config import settings

logger = logging.getLogger(__name__)


# ── Pydantic Schemas ─────────────────────────────────────────────────────────

class WordInfo(BaseModel):
    word: str
    start: float
    end: float
    confidence: float

class TranscribeResult(BaseModel):
    transcript: str
    confidence: float
    words: List[WordInfo] = Field(default_factory=list)
    language: str
    model_used: str
    was_upgraded: bool = False
    processing_time_ms: int

class SpeakerSegment(BaseModel):
    speaker_id: str
    start: float
    end: float
    confidence: float
    text: Optional[str] = None

class DiarizationResult(BaseModel):
    segments: List[SpeakerSegment]
    speaker_count: int
    segments_by_speaker: dict

class MeetingTranscript(BaseModel):
    segments: List[SpeakerSegment]
    speaker_count: int
    processing_time_ms: int

class SpeechAnalysis(BaseModel):
    language: str
    language_confidence: float
    emotion: str
    emotion_confidence: float
    audio_event: Optional[str] = None
    text: str

class TTSResult(BaseModel):
    audio_data: bytes
    duration_ms: int
    format: str

class MusicMatch(BaseModel):
    title: str
    artist: str
    duration: Optional[float] = None
    score: float
    release: Optional[str] = None

class StreamUpdate(BaseModel):
    transcript: str
    confidence: float
    finalized: bool
    segment_id: Optional[str] = None


# ── GPU Proxy Client ──────────────────────────────────────────────────────────

class AudioModelProxy:
    """Production audio proxy with GPU worker + OpenAI cloud fallback.

    Tier 1: Self-hosted GPU worker (Parakeet/Whisper/XTTS)
    Tier 2: OpenAI Whisper API + TTS API (cloud fallback)
    Tier 3: Dev mock (ENVIRONMENT == development only)
    """

    def __init__(self, endpoint_url: Optional[str] = None) -> None:
        self.endpoint = (endpoint_url or settings.AUDIO_GPU_ENDPOINT).rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=5.0),
            headers={"User-Agent": f"ButlerAudioService/{settings.SERVICE_VERSION}"},
        )

    # ── STT ────────────────────────────────────────────────────────────────────

    async def transcribe(
        self,
        audio_data: bytes,
        language: Optional[str] = None,
        model: Optional[str] = None,
    ) -> TranscribeResult:
        start = time.perf_counter()

        # Tier 1: Local GPU worker
        try:
            files = {"audio": ("audio.wav", audio_data, "audio/wav")}
            data = {"language": language or "en", "model": model or settings.STT_PRIMARY_MODEL}
            resp = await self._client.post(f"{self.endpoint}/stt", files=files, data=data)
            resp.raise_for_status()
            rd = resp.json()
            return TranscribeResult(
                **rd,
                processing_time_ms=int((time.perf_counter() - start) * 1000),
            )
        except (httpx.HTTPError, httpx.ConnectError) as e:
            logger.warning("gpu_stt_failed_trying_openai: %s", str(e))

        # Tier 2: OpenAI Whisper cloud fallback
        if settings.OPENAI_API_KEY:
            try:
                transcript = await self._openai_whisper(audio_data, language)
                return TranscribeResult(
                    transcript=transcript,
                    confidence=0.9,
                    language=language or "en",
                    model_used="openai/whisper-1",
                    processing_time_ms=int((time.perf_counter() - start) * 1000),
                )
            except Exception as e:
                logger.warning("openai_whisper_fallback_failed: %s", str(e))

        # Tier 3: Dev mock
        if settings.ENVIRONMENT == "development":
            return TranscribeResult(
                transcript="[DEV MOCK] Audio processing unavailable.",
                confidence=0.5,
                language=language or "en",
                model_used="mock-fallback",
                processing_time_ms=0,
            )
        raise RuntimeError("All STT backends failed and ENVIRONMENT is not development.")

    async def _openai_whisper(self, audio_data: bytes, language: Optional[str]) -> str:
        """Call OpenAI Whisper API directly."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                files={"file": ("audio.wav", audio_data, "audio/wav")},
                data={"model": "whisper-1", "language": language or "en"},
            )
            resp.raise_for_status()
            return resp.json()["text"]

    # ── TTS ────────────────────────────────────────────────────────────────────

    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        voice_ref: Optional[bytes] = None,
    ) -> TTSResult:
        start = time.perf_counter()

        # Tier 1: Local GPU worker
        try:
            data = {"text": text, "voice_id": voice_id or settings.TTS_DEFAULT_VOICE}
            files: dict = {}
            if voice_ref:
                files["voice_ref"] = ("ref.wav", voice_ref, "audio/wav")
            resp = await self._client.post(
                f"{self.endpoint}/tts", data=data, files=files or None
            )
            resp.raise_for_status()
            res = resp.json()
            return TTSResult(
                audio_data=base64.b64decode(res["audio_base64"]),
                duration_ms=res.get("duration_ms", 0),
                format=res.get("format", "wav"),
            )
        except (httpx.HTTPError, httpx.ConnectError) as e:
            logger.warning("gpu_tts_failed_trying_openai: %s", str(e))

        # Tier 2: OpenAI TTS cloud fallback
        if settings.OPENAI_API_KEY:
            try:
                audio_bytes = await self._openai_tts(text, voice_id)
                return TTSResult(
                    audio_data=audio_bytes,
                    duration_ms=int(len(text) * 50),   # rough estimate: 50ms/char
                    format="mp3",
                )
            except Exception as e:
                logger.warning("openai_tts_fallback_failed: %s", str(e))

        # Tier 3: Dev mock
        if settings.ENVIRONMENT == "development":
            return TTSResult(audio_data=b"mock_audio", duration_ms=1000, format="wav")
        raise RuntimeError("All TTS backends failed.")

    async def _openai_tts(self, text: str, voice_id: Optional[str]) -> bytes:
        """Call OpenAI TTS API directly."""
        oai_voice = "nova"   # best general-purpose voice; can map voice_id → oai_voice
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                json={"model": "tts-1", "input": text, "voice": oai_voice},
            )
            resp.raise_for_status()
            return resp.content

    # ── Voice Embedding ────────────────────────────────────────────────────────

    async def extract_embedding(self, audio_data: bytes) -> List[float]:
        try:
            files = {"audio": ("audio.wav", audio_data, "audio/wav")}
            resp = await self._client.post(f"{self.endpoint}/embedding", files=files)
            resp.raise_for_status()
            return resp.json()["embedding"]
        except Exception as e:
            logger.error("gpu_embedding_failed: %s", str(e))
            if settings.ENVIRONMENT == "development":
                import hashlib
                h = hashlib.sha256(audio_data).digest()
                return [float(b) / 255.0 for b in h[:128]]
            raise

    async def close(self) -> None:
        await self._client.aclose()
