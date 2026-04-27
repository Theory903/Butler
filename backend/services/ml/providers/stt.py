"""Speech-to-Text (STT) Providers — Deepgram, Whisper."""

from __future__ import annotations

import base64
import os

import httpx
import structlog

from services.security.safe_request import SafeRequestClient

logger = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=5.0)


class STTResult:
    """Result of speech-to-text transcription."""

    def __init__(self, text: str, language: str | None = None, confidence: float | None = None):
        self.text = text
        self.language = language
        self.confidence = confidence


# ── Deepgram STT Provider ─────────────────────────────────────────────────────


class DeepgramSTTProvider:
    """Deepgram Speech-to-Text Provider."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.deepgram.com/v1",
        model: str = "nova-2",
        tenant_id: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("DEEPGRAM_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self.tenant_id = tenant_id or "default"
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        self._safe_client = SafeRequestClient(timeout=_DEFAULT_TIMEOUT)

    async def transcribe(self, audio_data: bytes, language: str = "en") -> STTResult:
        """Transcribe audio data to text."""
        url = f"{self._base_url}/listen"

        headers = {
            "Authorization": f"Token {self._api_key}",
            "Content-Type": "audio/wav",
        }

        params = {
            "model": self._model,
            "language": language,
            "smart_format": True,
            "diarize": True,
        }

        if self._safe_client and self.tenant_id:
            response = await self._safe_client.post(
                url,
                self.tenant_id,
                content=audio_data,
                headers=headers,
                params=params,
            )
        else:
            response = await self._client.post(
                url, content=audio_data, headers=headers, params=params
            )
        response.raise_for_status()
        data = response.json()

        transcript = (
            data.get("results", {})
            .get("channels", [{}])[0]
            .get("alternatives", [{}])[0]
            .get("transcript", "")
        )
        confidence = (
            data.get("results", {})
            .get("channels", [{}])[0]
            .get("alternatives", [{}])[0]
            .get("confidence", None)
        )

        return STTResult(text=transcript, language=language, confidence=confidence)

    async def transcribe_url(self, url: str, language: str = "en") -> STTResult:
        """Transcribe audio from a URL."""
        api_url = f"{self._base_url}/listen"

        headers = {
            "Authorization": f"Token {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "url": url,
            "model": self._model,
            "language": language,
            "smart_format": True,
        }

        if self._safe_client and self.tenant_id:
            response = await self._safe_client.post(
                api_url,
                self.tenant_id,
                json=payload,
                headers=headers,
            )
        else:
            response = await self._client.post(api_url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        transcript = (
            data.get("results", {})
            .get("channels", [{}])[0]
            .get("alternatives", [{}])[0]
            .get("transcript", "")
        )

        return STTResult(text=transcript, language=language)


# ── OpenAI Whisper STT Provider ───────────────────────────────────────────────


class WhisperSTTProvider:
    """OpenAI Whisper Speech-to-Text Provider."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        model: str = "whisper-1",
        tenant_id: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self.tenant_id = tenant_id or "default"
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        self._safe_client = SafeRequestClient(timeout=_DEFAULT_TIMEOUT)

    async def transcribe(self, audio_data: bytes, language: str = "en") -> STTResult:
        """Transcribe audio data to text."""
        url = f"{self._base_url}/audio/transcriptions"

        headers = {
            "Authorization": f"Bearer {self._api_key}",
        }

        files = {
            "file": ("audio.wav", audio_data, "audio/wav"),
            "model": (None, self._model),
            "language": (None, language),
        }

        # SafeRequestClient doesn't support multipart file uploads, use httpx directly
        # For now, use direct httpx since multipart is not supported by SafeRequestClient
        response = await self._client.post(url, files=files, headers=headers)
        response.raise_for_status()
        data = response.json()

        transcript = data.get("text", "")

        return STTResult(text=transcript, language=language)

    async def transcribe_url(self, url: str, language: str = "en") -> STTResult:
        """Transcribe audio from a URL (downloads first)."""
        # Download the audio file first
        if self._safe_client and self.tenant_id:
            audio_response = await self._safe_client.get(url, self.tenant_id)
        else:
            audio_response = await self._client.get(url)
        audio_response.raise_for_status()

        return await self.transcribe(audio_response.content, language)


# ── Google Cloud STT Provider ───────────────────────────────────────────────


class GoogleCloudSTTProvider:
    """Google Cloud Speech-to-Text Provider."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "default",
        tenant_id: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("GOOGLE_CLOUD_API_KEY")
        self._model = model
        self.tenant_id = tenant_id or "default"
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        self._safe_client = SafeRequestClient(timeout=_DEFAULT_TIMEOUT)

    async def transcribe(self, audio_data: bytes, language: str = "en-US") -> STTResult:
        """Transcribe audio data to text using Google Cloud Speech-to-Text."""

        url = f"https://speech.googleapis.com/v1/speech:recognize?key={self._api_key}"

        payload = {
            "config": {
                "encoding": "LINEAR16",
                "sampleRateHertz": 16000,
                "languageCode": language,
                "model": self._model,
            },
            "audio": {"content": base64.b64encode(audio_data).decode("utf-8")},
        }

        if self._safe_client and self.tenant_id:
            response = await self._safe_client.post(url, self.tenant_id, json=payload)
        else:
            response = await self._client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

        transcript = ""
        if data.get("results"):
            for result in data["results"]:
                if result.get("alternatives"):
                    transcript += result["alternatives"][0].get("transcript", "") + " "

        return STTResult(text=transcript.strip(), language=language)
