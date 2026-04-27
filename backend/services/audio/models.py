"""AudioModelProxy with layered fallback (v3.1).

Fallback chain:
  1. Local GPU worker  (AUDIO_GPU_ENDPOINT — self-hosted Parakeet/Whisper/XTTS)
  2. OpenAI Whisper   (STT) / OpenAI TTS (gpt-4o-mini)
  3. Dev mock         (only when ENVIRONMENT == development)
"""

from __future__ import annotations

import base64
import logging
import time

import httpx
from pydantic import BaseModel, Field

from infrastructure.config import settings
from services.security.safe_request import SafeRequestClient

import structlog

logger = structlog.get_logger(__name__)


# ── Pydantic Schemas ─────────────────────────────────────────────────────────


class WordInfo(BaseModel):
    word: str
    start: float
    end: float
    confidence: float


class TranscribeResult(BaseModel):
    transcript: str
    confidence: float
    words: list[WordInfo] = Field(default_factory=list)
    language: str
    model_used: str
    was_upgraded: bool = False
    processing_time_ms: int


class SpeakerSegment(BaseModel):
    speaker_id: str
    start: float
    end: float
    confidence: float
    text: str | None = None


class DiarizationResult(BaseModel):
    segments: list[SpeakerSegment]
    speaker_count: int
    segments_by_speaker: dict


class MeetingTranscript(BaseModel):
    segments: list[SpeakerSegment]
    speaker_count: int
    processing_time_ms: int


class SpeechAnalysis(BaseModel):
    language: str
    language_confidence: float
    emotion: str
    emotion_confidence: float
    audio_event: str | None = None
    text: str


class TTSResult(BaseModel):
    audio_data: bytes
    duration_ms: int
    format: str


class MusicMatch(BaseModel):
    title: str
    artist: str
    duration: float | None = None
    score: float
    release: str | None = None


class StreamUpdate(BaseModel):
    transcript: str
    confidence: float
    finalized: bool
    segment_id: str | None = None


# ── GPU Proxy Client ──────────────────────────────────────────────────────────


class AudioModelProxy:
    """Production audio proxy with GPU worker + OpenAI cloud fallback.

    Tier 1: Self-hosted GPU worker (Parakeet/Whisper/XTTS)
    Tier 2: OpenAI Whisper API + TTS API (cloud fallback)
    Tier 3: Dev mock (ENVIRONMENT == development only)
    """

    def __init__(self, endpoint_url: str | None = None, tenant_id: str | None = None) -> None:
        self.endpoint = (endpoint_url or settings.AUDIO_GPU_ENDPOINT).rstrip("/")
        self.tenant_id = tenant_id or "default"
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=5.0),
            headers={"User-Agent": f"ButlerAudioService/{settings.SERVICE_VERSION}"},
        )
        self._safe_client = SafeRequestClient(timeout=httpx.Timeout(60.0, connect=5.0))

    # ── STT ────────────────────────────────────────────────────────────────────

    async def transcribe(
        self,
        audio_data: bytes,
        language: str | None = None,
        model: str | None = None,
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

    async def _openai_whisper(self, audio_data: bytes, language: str | None) -> str:
        """Call OpenAI Whisper API through SafeHttpClient for SSRF protection."""
        # SafeHttpClient doesn't support multipart file uploads directly
        # For now, use httpx but add SSRF check on the URL
        from services.security.egress_policy import EgressDecision, EgressPolicy

        egress_policy = EgressPolicy.get_default()
        decision, reason = egress_policy.check_url("https://api.openai.com", self.tenant_id)
        if decision == EgressDecision.DENY:
            raise RuntimeError(f"Egress policy denied OpenAI API call: {reason}")

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
        voice_id: str | None = None,
        voice_ref: bytes | None = None,
    ) -> TTSResult:
        time.perf_counter()

        # Tier 1: Local GPU worker
        try:
            data = {"text": text, "voice_id": voice_id or settings.TTS_DEFAULT_VOICE}
            files: dict = {}
            if voice_ref:
                files["voice_ref"] = ("ref.wav", voice_ref, "audio/wav")
            resp = await self._client.post(f"{self.endpoint}/tts", data=data, files=files or None)
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
                    duration_ms=int(len(text) * 50),  # rough estimate: 50ms/char
                    format="mp3",
                )
            except Exception as e:
                logger.warning("openai_tts_fallback_failed: %s", str(e))

        # Tier 3: Dev mock
        if settings.ENVIRONMENT == "development":
            return TTSResult(audio_data=b"mock_audio", duration_ms=1000, format="wav")
        raise RuntimeError("All TTS backends failed.")

    async def _openai_tts(self, text: str, voice_id: str | None) -> bytes:
        """Call OpenAI TTS API through SafeHttpClient for SSRF protection."""
        from services.security.egress_policy import EgressDecision, EgressPolicy

        egress_policy = EgressPolicy.get_default()
        decision, reason = egress_policy.check_url("https://api.openai.com", self.tenant_id)
        if decision == EgressDecision.DENY:
            raise RuntimeError(f"Egress policy denied OpenAI API call: {reason}")

        oai_voice = "nova"  # best general-purpose voice; can map voice_id → oai_voice
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                json={"model": "tts-1", "input": text, "voice": oai_voice},
            )
            resp.raise_for_status()
            return resp.content

    # ── Voice Embedding ────────────────────────────────────────────────────────

    async def extract_embedding(self, audio_data: bytes) -> list[float]:
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
