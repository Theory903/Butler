"""Text-to-Speech (TTS) Providers — ElevenLabs, OpenAI TTS, Coqui."""

from __future__ import annotations

import os

import httpx
import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=5.0)


class TTSResult:
    """Result of text-to-speech synthesis."""

    def __init__(self, audio_data: bytes | None = None, audio_url: str | None = None):
        self.audio_data = audio_data
        self.audio_url = audio_url


# ── ElevenLabs TTS Provider ───────────────────────────────────────────────────


class ElevenLabsTTSProvider:
    """ElevenLabs Text-to-Speech Provider."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.elevenlabs.io/v1",
        voice_id: str = "21m00Tcm4TlvDq8ikWAM",
        model: str = "eleven_monolingual_v1",
    ) -> None:
        self._api_key = api_key or os.environ.get("ELEVENLABS_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._voice_id = voice_id
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def speak(self, text: str, voice_id: str | None = None) -> TTSResult:
        """Convert text to speech audio."""
        voice = voice_id or self._voice_id
        url = f"{self._base_url}/text-to-speech/{voice}"

        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self._api_key,
        }

        payload = {
            "text": text,
            "model_id": self._model,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5,
            },
        }

        response = await self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()

        return TTSResult(audio_data=response.content)

    async def speak_streaming(self, text: str, voice_id: str | None = None) -> bytes:
        """Convert text to speech audio with streaming."""
        voice = voice_id or self._voice_id
        url = f"{self._base_url}/text-to-speech/{voice}/stream"

        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self._api_key,
        }

        payload = {
            "text": text,
            "model_id": self._model,
        }

        response = await self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()

        return response.content


# ── OpenAI TTS Provider ────────────────────────────────────────────────


class OpenAITTSProvider:
    """OpenAI Text-to-Speech Provider."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        model: str = "tts-1",
        voice: str = "alloy",
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._voice = voice
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def speak(self, text: str) -> TTSResult:
        """Convert text to speech audio."""
        url = f"{self._base_url}/audio/speech"

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self._model,
            "voice": self._voice,
            "input": text,
            "response_format": "mp3",
        }

        response = await self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()

        return TTSResult(audio_data=response.content)

    async def speak_streaming(self, text: str) -> bytes:
        """Convert text to speech audio with streaming."""
        url = f"{self._base_url}/audio/speech"

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self._model,
            "voice": self._voice,
            "input": text,
            "response_format": "mp3",
        }

        response = await self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()

        return response.content


# ── Coqui TTS Provider ────────────────────────────────────────────────


class CoquiTTSProvider:
    """Coqui Open-Source TTS Provider."""

    def __init__(
        self,
        base_url: str = "http://localhost:5002",
        model_id: str = "阚胆仪-多个中文说话人-女-20240125",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model_id = model_id
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def speak(self, text: str, language: str = "en") -> TTSResult:
        """Convert text to speech audio."""
        url = f"{self._base_url}/api/tts"

        params = {
            "text": text,
            "language": language,
            "model_id": self._model_id,
        }

        response = await self._client.get(url, params=params)
        response.raise_for_status()

        return TTSResult(audio_data=response.content)


# ── TTS Registry ────────────────────────────────────────────────────────


class TTSProviderFactory:
    """Factory for TTS providers."""

    _instances = {}

    @classmethod
    def get_provider(cls, provider_type: str):
        """Return a singleton instance of the requested TTS provider."""
        if provider_type in cls._instances:
            return cls._instances[provider_type]

        provider = None
        if provider_type == "elevenlabs":
            from services.ml.providers.stt import ElevenLabsTTSProvider

            provider = ElevenLabsTTSProvider()
        elif provider_type == "openai_tts":
            from services.ml.providers.stt import OpenAITTSProvider

            provider = OpenAITTSProvider()
        elif provider_type == "coqui":
            from services.ml.providers.stt import CoquiTTSProvider

            provider = CoquiTTSProvider()
        else:
            raise ValueError(f"Unsupported TTS provider: {provider_type}")

        cls._instances[provider_type] = provider
        return provider
