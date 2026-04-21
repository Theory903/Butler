"""AI Gateways — OpenRouter, Cloudflare, Vercel."""

from __future__ import annotations

import os
import time
import json
from typing import Optional, AsyncGenerator

import httpx
import structlog

from domain.ml.contracts import ReasoningContract, ReasoningRequest, ReasoningResponse

logger = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0)


# ── OpenRouter Provider ───────────────────────────────────────────────────

class OpenRouterProvider(ReasoningContract):
    """OpenRouter AI Gateway (aggregates multiple providers)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "anthropic/claude-3.5-sonnet",
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://butler.ai",
            "X-Title": "Butler AI",
        }
        payload = {
            "model": request.metadata.get("model", self._model),
            "messages": [],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.system_prompt:
            payload["messages"].append({"role": "system", "content": request.system_prompt})
        payload["messages"].append({"role": "user", "content": request.prompt})

        t0 = time.monotonic()
        response = await self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        latency = (time.monotonic() - t0) * 1000

        content = data["choices"][0]["message"]["content"]
        return ReasoningResponse(
            content=content,
            raw_response=data,
            usage=data.get("usage", {}),
            model_version=data.get("model", self._model),
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str, None]:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://butler.ai",
            "X-Title": "Butler AI",
        }
        payload = {
            "model": request.metadata.get("model", self._model),
            "messages": [],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
        }
        if request.system_prompt:
            payload["messages"].append({"role": "system", "content": request.system_prompt})
        payload["messages"].append({"role": "user", "content": request.prompt})

        async with self._client.stream("POST", url, json=payload, headers=headers) as response:
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                chunk_data = line[6:]
                if chunk_data == "[DONE]":
                    break
                try:
                    chunk_json = json.loads(chunk_data)
                    delta = chunk_json["choices"][0]["delta"].get("content", "")
                    if delta:
                        yield delta
                except Exception:
                    continue


# ── Cloudflare AI Gateway Provider ────────────────────────────────────────

class CloudflareAIGatewayProvider(ReasoningContract):
    """Cloudflare AI Gateway Provider."""

    def __init__(
        self,
        account_id: Optional[str] = None,
        api_token: Optional[str] = None,
        base_url: str = "",
        model: str = "@cf/meta/llama-3.1-8b-instruct",
    ) -> None:
        self._account_id = account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        self._api_token = api_token or os.environ.get("CLOUDFLARE_API_TOKEN")
        self._base_url = base_url or f"https://gateway.ai.cloudflare.com/v1/{self._account_id}"
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}/workers-ai/{self._model}"
        headers = {
            "Authorization": f"Bearer {self._api_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messages": [],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.system_prompt:
            payload["messages"].append({"role": "system", "content": request.system_prompt})
        payload["messages"].append({"role": "user", "content": request.prompt})

        t0 = time.monotonic()
        response = await self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        latency = (time.monotonic() - t0) * 1000

        content = data.get("result", {}).get("response", "")
        return ReasoningResponse(
            content=content,
            raw_response=data,
            usage={},
            model_version=self._model,
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str, None]:
        # Cloudflare Workers AI doesn't support streaming in same way
        result = await self.generate(request)
        yield result.content


# ── Vercel AI Gateway Provider ────────────────────────────────────────────

class VercelAIGatewayProvider(ReasoningContract):
    """Vercel AI Gateway Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "",
        project_id: Optional[str] = None,
        model: str = "openai/gpt-4o",
    ) -> None:
        self._api_key = api_key or os.environ.get("VERCEL_API_KEY")
        self._base_url = base_url or "https://gateway.vercel.ai"
        self._project_id = project_id or os.environ.get("VERCEL_PROJECT_ID")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}/api/{self._project_id or 'gateway'}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": request.metadata.get("model", self._model),
            "messages": [],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.system_prompt:
            payload["messages"].append({"role": "system", "content": request.system_prompt})
        payload["messages"].append({"role": "user", "content": request.prompt})

        t0 = time.monotonic()
        response = await self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        latency = (time.monotonic() - t0) * 1000

        content = data["choices"][0]["message"]["content"]
        return ReasoningResponse(
            content=content,
            raw_response=data,
            usage=data.get("usage", {}),
            model_version=data.get("model", self._model),
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str, None]:
        url = f"{self._base_url}/api/{self._project_id or 'gateway'}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": request.metadata.get("model", self._model),
            "messages": [],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
        }
        if request.system_prompt:
            payload["messages"].append({"role": "system", "content": request.system_prompt})
        payload["messages"].append({"role": "user", "content": request.prompt})

        async with self._client.stream("POST", url, json=payload, headers=headers) as response:
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                chunk_data = line[6:]
                if chunk_data == "[DONE]":
                    break
                try:
                    chunk_json = json.loads(chunk_data)
                    delta = chunk_json["choices"][0]["delta"].get("content", "")
                    if delta:
                        yield delta
                except Exception:
                    continue


# ── AI Gateway Factory ────────────────────────────────────────────────

class AIGatewayFactory:
    """Factory for AI gateway providers."""

    _instances = {}

    @classmethod
    def get_provider(cls, provider_type: str):
        """Return an AI gateway provider instance."""
        if provider_type in cls._instances:
            return cls._instances[provider_type]

        provider = None
        if provider_type == "openrouter":
            from services.ml.providers.gateway import OpenRouterProvider
            provider = OpenRouterProvider()
        elif provider_type == "cloudflare":
            from services.ml.providers.gateway import CloudflareAIGatewayProvider
            provider = CloudflareAIGatewayProvider()
        elif provider_type == "vercel":
            from services.ml.providers.gateway import VercelAIGatewayProvider
            provider = VercelAIGatewayProvider()
        else:
            raise ValueError(f"Unsupported AI gateway provider: {provider_type}")

        cls._instances[provider_type] = provider
        return provider