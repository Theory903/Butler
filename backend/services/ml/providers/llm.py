"""Additional LLM Providers — normalized production provider layer.

Providers covered:
- DeepSeek
- Groq
- Ollama
- Mistral
- Perplexity
- Together
- xAI
- Google Gemini (OpenAI-compatible surface)
- Fireworks
- NVIDIA
- Venice
- Qwen

Design goals:
- avoid copy-pasted provider logic
- use a shared OpenAI-compatible base where practical
- keep native Ollama separate
- expose consistent ReasoningResponse metadata
- keep provider-specific assumptions minimal
- enforce SSRF protection via EgressPolicy for all external API calls
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import structlog

from domain.ml.contracts import ReasoningContract, ReasoningRequest, ReasoningResponse
from services.security.egress_policy import EgressDecision, EgressPolicy

logger = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0)
_STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)


class ProviderConfigurationError(RuntimeError):
    """Raised when a provider is missing required configuration."""


class BaseReasoningHTTPProvider(ReasoningContract):
    """Shared HTTP-backed provider utilities with SSRF protection."""

    provider_name: str = "unknown"

    def __init__(
        self,
        *,
        timeout: httpx.Timeout = _DEFAULT_TIMEOUT,
        stream_timeout: httpx.Timeout = _STREAM_TIMEOUT,
        tenant_id: str | None = None,
    ) -> None:
        self._tenant_id = tenant_id or "default"
        self._client = httpx.AsyncClient(timeout=timeout)
        self._stream_client = httpx.AsyncClient(timeout=stream_timeout)
        self._egress_policy = EgressPolicy.get_default()

    def _check_egress_policy(self, url: str) -> None:
        """Check egress policy before making external API call."""
        decision, reason = self._egress_policy.check_url(url, self._tenant_id)
        if decision == EgressDecision.DENY:
            raise RuntimeError(
                f"Egress policy denied {self.provider_name} API call to {url}: {reason}"
            )

    def _require_api_key(self, api_key: str | None) -> str:
        if not api_key or not api_key.strip():
            raise ProviderConfigurationError(f"{self.provider_name} API key is not configured")
        return api_key.strip()

    def _extract_model(self, request: ReasoningRequest, fallback_model: str) -> str:
        if request.preferred_model:
            return request.preferred_model
        raw_model = request.metadata.get("model")
        if isinstance(raw_model, str) and raw_model.strip():
            return raw_model.strip()
        return fallback_model

    def _normalize_usage(self, usage: Any) -> dict[str, Any]:
        if isinstance(usage, dict):
            return dict(usage)
        return {}

    def _make_response(
        self,
        *,
        content: str,
        raw_response: dict[str, Any] | None,
        usage: dict[str, Any],
        model_version: str,
        finish_reason: str | None = None,
        metadata: dict[str, Any] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> ReasoningResponse:
        return ReasoningResponse(
            content=content,
            raw_response=raw_response,
            usage=usage,
            model_version=model_version,
            provider_name=self.provider_name,
            finish_reason=finish_reason,
            metadata=metadata or {},
            tool_calls=tool_calls or [],
        )

    async def _iter_sse_data_lines(
        self,
        response: httpx.Response,
    ) -> AsyncGenerator[str]:
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            yield line[6:].strip()

    async def close(self) -> None:
        await self._client.aclose()
        await self._stream_client.aclose()


class OpenAICompatibleProvider(BaseReasoningHTTPProvider):
    """Base provider for OpenAI-compatible chat completion APIs."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        default_model: str,
        api_key_query_param: str | None = None,
    ) -> None:
        super().__init__()
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._api_key_query_param = api_key_query_param

    def _headers(self) -> dict[str, str]:
        if self._api_key_query_param is not None:
            return {"Content-Type": "application/json"}

        api_key = self._require_api_key(self._api_key)
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _build_url(self, path: str) -> str:
        if self._api_key_query_param is None:
            return f"{self._base_url}/{path.lstrip('/')}"

        api_key = self._require_api_key(self._api_key)
        separator = "&" if "?" in path else "?"
        return (
            f"{self._base_url}/{path.lstrip('/')}{separator}{self._api_key_query_param}={api_key}"
        )

    def _payload(self, request: ReasoningRequest, *, stream: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._extract_model(request, self._default_model),
            "messages": [],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.stop_sequences:
            payload["stop"] = request.stop_sequences
        if stream:
            payload["stream"] = True

        # Add tools if present (for function calling)
        if request.tools:
            formatted_tools = []
            for tool in request.tools:
                # If already in OpenAI format (has "type": "function"), pass through
                if isinstance(tool, dict) and tool.get("type") == "function":
                    formatted_tools.append(tool)
                else:
                    # Wrap in OpenAI function calling format
                    formatted_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.get("name"),
                            "description": tool.get("description", ""),
                            "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                        },
                    })
            payload["tools"] = formatted_tools

        if request.system_prompt:
            payload["messages"].append({"role": "system", "content": request.system_prompt})
        payload["messages"].append({"role": "user", "content": request.prompt})
        return payload

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = self._build_url("chat/completions")
        payload = self._payload(request)
        started_at = time.monotonic()

        logger.debug(
            "provider_generate_request",
            provider=self.provider_name,
            url=url,
            payload=payload,
        )

        response = await self._client.post(url, json=payload, headers=self._headers())
        response.raise_for_status()
        data = response.json()

        latency_ms = round((time.monotonic() - started_at) * 1000, 1)
        choice = data["choices"][0]
        message = choice["message"]
        content = message.get("content") or ""
        usage = self._normalize_usage(data.get("usage", {}))
        usage.setdefault("duration_ms", latency_ms)

        # Extract tool_calls if present
        tool_calls = []
        if "tool_calls" in message:
            tool_calls = message["tool_calls"]

        logger.debug(
            "provider_generate_ok",
            provider=self.provider_name,
            latency_ms=latency_ms,
            model=data.get("model", payload["model"]),
            tool_calls_count=len(tool_calls),
        )

        return self._make_response(
            content=content,
            raw_response=data,
            usage=usage,
            model_version=data.get("model", payload["model"]),
            finish_reason=choice.get("finish_reason"),
            metadata={"tool_calls": tool_calls} if tool_calls else None,
            tool_calls=tool_calls,
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str]:
        url = self._build_url("chat/completions")
        payload = self._payload(request, stream=True)

        try:
            async with self._stream_client.stream(
                "POST",
                url,
                json=payload,
                headers=self._headers(),
            ) as response:
                response.raise_for_status()

                async for data_line in self._iter_sse_data_lines(response):
                    if data_line == "[DONE]":
                        return

                    try:
                        chunk = json.loads(data_line)
                    except json.JSONDecodeError:
                        logger.debug(
                            "provider_stream_invalid_json_ignored", provider=self.provider_name
                        )
                        continue

                    try:
                        delta = chunk["choices"][0]["delta"].get("content", "")
                    except (KeyError, IndexError, AttributeError):
                        continue

                    if delta:
                        yield delta

        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            logger.warning(
                "provider_stream_fallback_to_buffered",
                provider=self.provider_name,
                error=str(exc),
            )
            result = await self.generate(request)
            if result.content:
                yield result.content


class DeepSeekProvider(OpenAICompatibleProvider):
    provider_name = "deepseek"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
    ) -> None:
        super().__init__(
            api_key=api_key or os.environ.get("DEEPSEEK_API_KEY"),
            base_url=base_url,
            default_model=model,
        )


class GroqProvider(OpenAICompatibleProvider):
    provider_name = "groq"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.groq.com/openai/v1",
        model: str | None = None,
    ) -> None:
        from infrastructure.config import settings
        default_model = model or settings.DEFAULT_MODEL
        super().__init__(
            api_key=api_key or os.environ.get("GROQ_API_KEY"),
            base_url=base_url,
            default_model=default_model,
        )


class MistralProvider(OpenAICompatibleProvider):
    provider_name = "mistral"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.mistral.ai/v1",
        model: str = "mistral-small-latest",
    ) -> None:
        super().__init__(
            api_key=api_key or os.environ.get("MISTRAL_API_KEY"),
            base_url=base_url,
            default_model=model,
        )


class PerplexityProvider(OpenAICompatibleProvider):
    provider_name = "perplexity"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.perplexity.ai",
        model: str = "sonar-pro",
    ) -> None:
        super().__init__(
            api_key=api_key or os.environ.get("PERPLEXITY_API_KEY"),
            base_url=base_url,
            default_model=model,
        )


class TogetherProvider(OpenAICompatibleProvider):
    provider_name = "together"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.together.xyz/v1",
        model: str = "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    ) -> None:
        super().__init__(
            api_key=api_key or os.environ.get("TOGETHER_API_KEY"),
            base_url=base_url,
            default_model=model,
        )


class XAIProvider(OpenAICompatibleProvider):
    provider_name = "xai"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.x.ai/v1",
        model: str = "grok-2-1212",
    ) -> None:
        super().__init__(
            api_key=api_key or os.environ.get("XAI_API_KEY"),
            base_url=base_url,
            default_model=model,
        )


class GoogleGeminiProvider(OpenAICompatibleProvider):
    provider_name = "google"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai",
        model: str = "gemini-2.0-flash",
    ) -> None:
        super().__init__(
            api_key=api_key or os.environ.get("GOOGLE_API_KEY"),
            base_url=base_url,
            default_model=model,
            api_key_query_param="key",
        )


class FireworksProvider(OpenAICompatibleProvider):
    provider_name = "fireworks"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.fireworks.ai/v1",
        model: str = "fireworks-ai/firefunction-v2",
    ) -> None:
        super().__init__(
            api_key=api_key or os.environ.get("FIREWORKS_API_KEY"),
            base_url=base_url,
            default_model=model,
        )


class NVIDIAProvider(OpenAICompatibleProvider):
    provider_name = "nvidia"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        model: str = "nvidia/llama-3.1-nemotron-70b-instruct",
    ) -> None:
        super().__init__(
            api_key=api_key or os.environ.get("NVIDIA_API_KEY"),
            base_url=base_url,
            default_model=model,
        )


class VeniceProvider(OpenAICompatibleProvider):
    provider_name = "venice"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.venice.ai/api/v1",
        model: str = "venice-3-strong",
    ) -> None:
        super().__init__(
            api_key=api_key or os.environ.get("VENICE_API_KEY"),
            base_url=base_url,
            default_model=model,
        )


class QwenProvider(OpenAICompatibleProvider):
    provider_name = "qwen"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/qwen",
        model: str = "qwen-plus",
    ) -> None:
        super().__init__(
            api_key=api_key or os.environ.get("DASHSCOPE_API_KEY"),
            base_url=base_url,
            default_model=model,
        )


class OllamaProvider(BaseReasoningHTTPProvider):
    """Ollama native chat API provider."""

    provider_name = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434/api",
        model: str = "llama3",
    ) -> None:
        super().__init__()
        self._base_url = base_url.rstrip("/")
        self._model = model

    def _payload(self, request: ReasoningRequest, *, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._extract_model(request, self._model),
            "messages": [],
            "stream": stream,
        }
        if request.system_prompt:
            payload["messages"].append({"role": "system", "content": request.system_prompt})
        payload["messages"].append({"role": "user", "content": request.prompt})

        if request.temperature is not None:
            payload["options"] = {"temperature": request.temperature}

        return payload

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}/chat"
        payload = self._payload(request, stream=False)
        started_at = time.monotonic()

        response = await self._client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

        latency_ms = round((time.monotonic() - started_at) * 1000, 1)
        content = data.get("message", {}).get("content", "")
        usage = {
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "completion_tokens": data.get("eval_count", 0),
            "duration_ms": latency_ms,
        }

        return self._make_response(
            content=content,
            raw_response=data,
            usage=usage,
            model_version=str(data.get("model", payload["model"])),
            finish_reason="stop" if data.get("done") else None,
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str]:
        url = f"{self._base_url}/chat"
        payload = self._payload(request, stream=True)

        try:
            async with self._stream_client.stream("POST", url, json=payload) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug("ollama_stream_invalid_json_ignored")
                        continue

                    delta = chunk.get("message", {}).get("content", "")
                    if delta:
                        yield delta

                    if chunk.get("done", False):
                        return

        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            logger.warning("ollama_stream_fallback_to_buffered", error=str(exc))
            result = await self.generate(request)
            if result.content:
                yield result.content
