"""Media Generation — ComfyUI, FAL, Video, Music."""

from __future__ import annotations
import os
import base64
import json
from typing import Optional, AsyncGenerator
from abc import ABC, abstractmethod

import httpx
import structlog

logger = structlog.get_logger(__name__)
_DEFAULT_TIMEOUT = httpx.Timeout(connect=30.0, read=300.0, write=30.0)


class MediaGenerationRequest:
    def __init__(
        self,
        prompt: str,
        model: str = "default",
        negative_prompt: str = "",
        width: int = 512,
        height: int = 512,
        num_images: int = 1,
        seed: int = -1,
        guidance_scale: float = 7.5,
        steps: int = 20,
        metadata: dict = None,
    ):
        self.prompt = prompt
        self.model = model
        self.negative_prompt = negative_prompt
        self.width = width
        self.height = height
        self.num_images = num_images
        self.seed = seed
        self.guidance_scale = guidance_scale
        self.steps = steps
        self.metadata = metadata or {}


class MediaGenerationResponse:
    def __init__(
        self,
        images: list[bytes] = None,
        urls: list[str] = None,
        seed: int = -1,
        metadata: dict = None,
    ):
        self.images = images or []
        self.urls = urls or []
        self.seed = seed
        self.metadata = metadata or {}


class VideoGenerationRequest:
    def __init__(
        self,
        prompt: str,
        duration: int = 5,
        fps: int = 24,
        model: str = "default",
        metadata: dict = None,
    ):
        self.prompt = prompt
        self.duration = duration
        self.fps = fps
        self.model = model
        self.metadata = metadata or {}


class MusicGenerationRequest:
    def __init__(
        self,
        prompt: str,
        duration: int = 30,
        bpm: int = 120,
        genre: str = "",
        metadata: dict = None,
    ):
        self.prompt = prompt
        self.duration = duration
        self.bpm = bpm
        self.genre = genre
        self.metadata = metadata or {}


class BaseMediaProvider(ABC):
    @abstractmethod
    async def generate_image(self, request: MediaGenerationRequest) -> MediaGenerationResponse:
        pass

    @abstractmethod
    async def generate_video(self, request: VideoGenerationRequest) -> MediaGenerationResponse:
        pass

    @abstractmethod
    async def generate_music(self, request: MusicGenerationRequest) -> MediaGenerationResponse:
        pass


class ComfyUIProvider(BaseMediaProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "http://localhost:8188",
    ):
        self._api_key = api_key or os.environ.get("COMFY_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def generate_image(self, request: MediaGenerationRequest) -> MediaGenerationResponse:
        url = f"{self._base_url}/prompt"
        payload = {
            "prompt": {
                "nodes": [
                    {
                        "id": 1,
                        "type": "TextToImage",
                        "values": {
                            "prompt": request.prompt,
                            "negative_prompt": request.negative_prompt,
                            "width": request.width,
                            "height": request.height,
                            "steps": request.steps,
                            "guidance_scale": request.guidance_scale,
                            "seed": request.seed if request.seed >= 0 else 42,
                        },
                    }
                ]
            }
        }
        resp = await self._client.post(url, json=payload)
        resp.raise_for_status()
        return MediaGenerationResponse(images=[], seed=payload["prompt"]["nodes"][0]["values"]["seed"])

    async def generate_video(self, request: VideoGenerationRequest) -> MediaGenerationResponse:
        url = f"{self._base_url}/prompt"
        payload = {"prompt": {"nodes": [{"id": 1, "type": "TextToVideo", "values": {"prompt": request.prompt}}]}
        resp = await self._client.post(url, json=payload)
        resp.raise_for_status()
        return MediaGenerationResponse()

    async def generate_music(self, request: MusicGenerationRequest) -> MediaGenerationResponse:
        url = f"{self._base_url}/prompt"
        payload = {"prompt": {"nodes": [{"id": 1, "type": "TextToMusic", "values": {"prompt": request.prompt}}]}
        resp = await self._client.post(url, json=payload)
        resp.raise_for_status()
        return MediaGenerationResponse()


class FALProvider(BaseMediaProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://queue.fal.run",
    ):
        self._api_key = api_key or os.environ.get("FAL_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def generate_image(self, request: MediaGenerationRequest) -> MediaGenerationResponse:
        url = f"{self._base_url}/image-generation"
        headers = {"Authorization": f"Key {self._api_key}"}
        payload = {
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "image_size": {"width": request.width, "height": request.height},
            "num_images": request.num_images,
        }
        resp = await self._client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return MediaGenerationResponse(images=[], urls=data.get("urls", []))

    async def generate_video(self, request: VideoGenerationRequest) -> MediaGenerationResponse:
        url = f"{self._base_url}/video-generation"
        headers = {"Authorization": f"Key {self._api_key}"}
        payload = {"prompt": request.prompt, "duration": request.duration}
        resp = await self._client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return MediaGenerationResponse()

    async def generate_music(self, request: MusicGenerationRequest) -> MediaGenerationResponse:
        url = f"{self._base_url}/music-generation"
        headers = {"Authorization": f"Key {self._api_key}"}
        payload = {"prompt": request.prompt, "duration": request.duration}
        resp = await self._client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return MediaGenerationResponse()


class MediaProviderFactory:
    _instances: dict = {}

    @classmethod
    def get_provider(cls, provider_type: str):
        if provider_type in cls._instances:
            return cls._instances[provider_type]
        provider = {
            "comfy": lambda: ComfyUIProvider(),
            "fal": lambda: FALProvider(),
        }.get(provider_type)()
        cls._instances[provider_type] = provider
        return provider