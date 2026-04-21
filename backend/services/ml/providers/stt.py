"""Speech-to-Text (STT) Providers — Deepgram, Whisper."""

from __future__ import annotations

import os
import base64
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=5.0)


class STTResult:
    """Result of speech-to-text transcription."""
    
    def __init__(self, text: str, language: Optional[str] = None, confidence: Optional[float] = None):
        self.text = text
        self.language = language
        self.confidence = confidence


# ── Deepgram STT Provider ─────────────────────────────────────────────────────

class DeepgramSTTProvider:
    """Deepgram Speech-to-Text Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.deepgram.com/v1",
        model: str = "nova-2",
    ) -> None:
        self._api_key = api_key or os.environ.get("DEEPGRAM_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

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
        
        response = await self._client.post(
            url,
            content=audio_data,
            headers=headers,
            params=params
        )
        response.raise_for_status()
        data = response.json()
        
        transcript = data.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("transcript", "")
        confidence = data.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("confidence", None)
        
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
        
        response = await self._client.post(api_url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        transcript = data.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("transcript", "")
        
        return STTResult(text=transcript, language=language)


# ── OpenAI Whisper STT Provider ───────────────────────────────────────────────

class WhisperSTTProvider:
    """OpenAI Whisper Speech-to-Text Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.openai.com/v1",
        model: str = "whisper-1",
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

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
        
        response = await self._client.post(url, files=files, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        transcript = data.get("text", "")
        
        return STTResult(text=transcript, language=language)

    async def transcribe_url(self, url: str, language: str = "en") -> STTResult:
        """Transcribe audio from a URL (downloads first)."""
        # Download the audio file first
        audio_response = await self._client.get(url)
        audio_response.raise_for_status()
        
        return await self.transcribe(audio_response.content, language)


# ── Google Cloud STT Provider ───────────────────────────────────────────────

class GoogleCloudSTTProvider:
    """Google Cloud Speech-to-Text Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "default",
    ) -> None:
        self._api_key = api_key or os.environ.get("GOOGLE_CLOUD_API_KEY")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def transcribe(self, audio_data: bytes, language: str = "en-US") -> STTResult:
        """Transcribe audio data to text using Google Cloud Speech-to-Text."""
        import base64
        
        url = f"https://speech.googleapis.com/v1/speech:recognize?key={self._api_key}"
        
        payload = {
            "config": {
                "encoding": "LINEAR16",
                "sampleRateHertz": 16000,
                "languageCode": language,
                "model": self._model,
            },
            "audio": {
                "content": base64.b64encode(audio_data).decode("utf-8")
            },
        }
        
        response = await self._client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        
        transcript = ""
        if data.get("results"):
            for result in data["results"]:
                if result.get("alternatives"):
                    transcript += result["alternatives"][0].get("transcript", "") + " "
        
        return STTResult(text=transcript.strip(), language=language)
