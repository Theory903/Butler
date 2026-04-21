"""Additional LLM Providers — DeepSeek, Groq, Ollama, Mistral, Perplexity, Together, xAI."""

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
_STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)


# ── DeepSeek Provider ────────────────────────────────────────────────────────

class DeepSeekProvider(ReasoningContract):
    """DeepSeek Chat API Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
    ) -> None:
        self._api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}/chat/completions"
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
        url = f"{self._base_url}/chat/completions"
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


# ── Groq Provider ────────────────────────────────────────────────────────────────

class GroqProvider(ReasoningContract):
    """Groq API Provider — Ultra-fast inference."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.groq.com/openai/v1",
        model: str = "llama-3.3-70b-versatile",
    ) -> None:
        self._api_key = api_key or os.environ.get("GROQ_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}/chat/completions"
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
        url = f"{self._base_url}/chat/completions"
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


# ── Ollama Provider ────────────────────────────────────────────────────────────────

class OllamaProvider(ReasoningContract):
    """Ollama Local LLM Provider."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": request.metadata.get("model", self._model),
            "messages": [],
            "temperature": request.temperature,
            "stream": False,
        }
        if request.system_prompt:
            payload["messages"].append({"role": "system", "content": request.system_prompt})
        payload["messages"].append({"role": "user", "content": request.prompt})

        t0 = time.monotonic()
        response = await self._client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        latency = (time.monotonic() - t0) * 1000

        content = data.get("message", {}).get("content", "")
        return ReasoningResponse(
            content=content,
            raw_response=data,
            usage={"prompt_tokens": data.get("prompt_eval_count", 0), "completion_tokens": data.get("eval_count", 0)},
            model_version=self._model,
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str, None]:
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": request.metadata.get("model", self._model),
            "messages": [],
            "temperature": request.temperature,
            "stream": True,
        }
        if request.system_prompt:
            payload["messages"].append({"role": "system", "content": request.system_prompt})
        payload["messages"].append({"role": "user", "content": request.prompt})

        async with self._client.stream("POST", url, json=payload) as response:
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk_json = json.loads(line)
                    delta = chunk_json.get("message", {}).get("content", "")
                    if delta:
                        yield delta
                    if chunk_json.get("done", False):
                        break
                except Exception:
                    continue


# ── Mistral Provider ────────────────────────────────────────────────────────────

class MistralProvider(ReasoningContract):
    """Mistral API Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.mistral.ai/v1",
        model: str = "mistral-small-latest",
    ) -> None:
        self._api_key = api_key or os.environ.get("MISTRAL_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}/chat/completions"
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
        url = f"{self._base_url}/chat/completions"
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


# ── Perplexity Provider ──────────────────────────────────────────────────────

class PerplexityProvider(ReasoningContract):
    """Perplexity AI API Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.perplexity.ai",
        model: str = "llama-3.1-sonar-small-128k-online",
    ) -> None:
        self._api_key = api_key or os.environ.get("PERPLEXITY_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}/chat/completions"
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
        url = f"{self._base_url}/chat/completions"
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


# ── Together AI Provider ──────────────────────────────────────────────────────

class TogetherProvider(ReasoningContract):
    """Together AI API Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.together.xyz/v1",
        model: str = "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    ) -> None:
        self._api_key = api_key or os.environ.get("TOGETHER_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}/chat/completions"
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
        url = f"{self._base_url}/chat/completions"
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


# ── xAI Provider ────────────────────────────────────────────────────────────────

class xAIProvider(ReasoningContract):
    """xAI Grok API Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.x.ai/v1",
        model: str = "grok-2-1212",
    ) -> None:
        self._api_key = api_key or os.environ.get("XAI_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}/chat/completions"
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
        url = f"{self._base_url}/chat/completions"
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


# ── Google Gemini Provider ───────────────────────────────────────────────────

class GoogleGeminiProvider(ReasoningContract):
    """Google Gemini API Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/",
        model: str = "gemini-2.0-flash",
    ) -> None:
        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}chat/completions?key={self._api_key}"
        payload = {
            "model": request.metadata.get("model", self._model),
            "messages": [],
            "temperature": request.temperature,
            "max_output_tokens": request.max_tokens,
        }
        if request.system_prompt:
            payload["messages"].append({"role": "system", "content": request.system_prompt})
        payload["messages"].append({"role": "user", "content": request.prompt})

        t0 = time.monotonic()
        response = await self._client.post(url, json=payload)
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
        url = f"{self._base_url}chat/completions?key={self._api_key}"
        payload = {
            "model": request.metadata.get("model", self._model),
            "messages": [],
            "temperature": request.temperature,
            "max_output_tokens": request.max_tokens,
            "stream": True,
        }
        if request.system_prompt:
            payload["messages"].append({"role": "system", "content": request.system_prompt})
        payload["messages"].append({"role": "user", "content": request.prompt})

        async with self._client.stream("POST", url, json=payload) as response:
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


# ── Fireworks AI Provider ─────────────────────────────────────────────────
class FireworksProvider(ReasoningContract):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.fireworks.ai/v1",
        model: str = "fireworks-ai/firefunction-v2",
    ) -> None:
        self._api_key = api_key or os.environ.get("FIREWORKS_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        payload = {
            "model": request.metadata.get("model", self._model),
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.system_prompt:
            payload["messages"].insert(0, {"role": "system", "content": request.system_prompt})
        resp = await self._client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return ReasoningResponse(
            content=data["choices"][0]["message"]["content"],
            raw_response=data,
            usage=data.get("usage", {}),
            model_version=data.get("model", self._model),
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str, None]:
        url = f"{self._base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        payload = {
            "model": request.metadata.get("model", self._model),
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
        }
        if request.system_prompt:
            payload["messages"].insert(0, {"role": "system", "content": request.system_prompt})
        async with self._client.stream("POST", url, json=payload, headers=headers) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and line[6:] != "[DONE]":
                    try:
                        chunk = json.loads(line[6:])
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        continue


# ── NVIDIA Provider ───────────────────────────────────────────────────
class NVIDIAProvider(ReasoningContract):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        model: str = "nvidia/llama-3.1-nemotron-70b-instruct",
    ) -> None:
        self._api_key = api_key or os.environ.get("NVIDIA_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        payload = {
            "model": request.metadata.get("model", self._model),
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.system_prompt:
            payload["messages"].insert(0, {"role": "system", "content": request.system_prompt})
        resp = await self._client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return ReasoningResponse(
            content=data["choices"][0]["message"]["content"],
            raw_response=data,
            usage=data.get("usage", {}),
            model_version=data.get("model", self._model),
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str, None]:
        url = f"{self._base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        payload = {
            "model": request.metadata.get("model", self._model),
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
        }
        if request.system_prompt:
            payload["messages"].insert(0, {"role": "system", "content": request.system_prompt})
        async with self._client.stream("POST", url, json=payload, headers=headers) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and line[6:] != "[DONE]":
                    try:
                        chunk = json.loads(line[6:])
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        continue


# ── Venice AI Provider ─────────────────────────────────────────────
class VeniceProvider(ReasoningContract):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.venice.ai/api/v1",
        model: str = "venice-3-strong",
    ) -> None:
        self._api_key = api_key or os.environ.get("VENICE_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        payload = {
            "model": request.metadata.get("model", self._model),
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.system_prompt:
            payload["messages"].insert(0, {"role": "system", "content": request.system_prompt})
        resp = await self._client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return ReasoningResponse(
            content=data["choices"][0]["message"]["content"],
            raw_response=data,
            usage=data.get("usage", {}),
            model_version=data.get("model", self._model),
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str, None]:
        url = f"{self._base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        payload = {
            "model": request.metadata.get("model", self._model),
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
        }
        if request.system_prompt:
            payload["messages"].insert(0, {"role": "system", "content": request.system_prompt})
        async with self._client.stream("POST", url, json=payload, headers=headers) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and line[6:] != "[DONE]":
                    try:
                        chunk = json.loads(line[6:])
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        continue


# ── Qwen Provider ───────────────────────────────────────────────────
class QwenProvider(ReasoningContract):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/qwen",
        model: str = "qwen-plus",
    ) -> None:
        self._api_key = api_key or os.environ.get("DASHSCOPE_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        payload = {
            "model": request.metadata.get("model", self._model),
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.system_prompt:
            payload["messages"].insert(0, {"role": "system", "content": request.system_prompt})
        resp = await self._client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return ReasoningResponse(
            content=data["choices"][0]["message"]["content"],
            raw_response=data,
            usage=data.get("usage", {}),
            model_version=data.get("model", self._model),
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str, None]:
        url = f"{self._base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        payload = {
            "model": request.metadata.get("model", self._model),
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
        }
        if request.system_prompt:
            payload["messages"].insert(0, {"role": "system", "content": request.system_prompt})
        async with self._client.stream("POST", url, json=payload, headers=headers) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and line[6:] != "[DONE]":
                    try:
                        chunk = json.loads(line[6:])
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        continue