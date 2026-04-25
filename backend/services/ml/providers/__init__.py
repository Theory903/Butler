"""ML Reasoning Providers — Butler production provider layer.

Design goals:
- typed provider boundary for runtime-facing reasoning calls
- shared HTTP/retry/stream parsing helpers where reasonable
- provider-specific payload builders only where APIs differ
- robust streaming behavior with graceful degradation
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

logger = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0)
_STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)


class ProviderConfigurationError(RuntimeError):
    """Raised when a provider is missing required configuration."""


class BaseHTTPReasoningProvider(ReasoningContract):
    """Small shared base for HTTP-backed reasoning providers."""

    def __init__(
        self,
        *,
        timeout: httpx.Timeout = _DEFAULT_TIMEOUT,
        stream_timeout: httpx.Timeout = _STREAM_TIMEOUT,
    ) -> None:
        self._client = httpx.AsyncClient(timeout=timeout)
        self._stream_client = httpx.AsyncClient(timeout=stream_timeout)

    async def close(self) -> None:
        await self._client.aclose()
        await self._stream_client.aclose()

    def _require_api_key(self, api_key: str | None, provider_name: str) -> str:
        if not api_key or not api_key.strip():
            raise ProviderConfigurationError(f"{provider_name} API key is not configured")
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

    def _base_response(
        self,
        *,
        content: str,
        raw_response: dict[str, Any] | None,
        usage: dict[str, Any],
        model_version: str,
        provider_name: str,
        finish_reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ReasoningResponse:
        return ReasoningResponse(
            content=content,
            raw_response=raw_response,
            usage=usage,
            model_version=model_version,
            provider_name=provider_name,
            finish_reason=finish_reason,
            metadata=metadata or {},
        )

    async def _iter_sse_data_lines(
        self,
        response: httpx.Response,
    ) -> AsyncGenerator[tuple[str | None, str]]:
        """Yield (event_name, data_line) pairs from an SSE response.

        Handles standard SSE framing:
        - event: ...
        - data: ...
        - blank line terminates an event block
        """
        current_event: str | None = None
        data_lines: list[str] = []

        async for line in response.aiter_lines():
            if line == "":
                if data_lines:
                    yield current_event, "\n".join(data_lines)
                current_event = None
                data_lines = []
                continue

            if line.startswith(":"):
                continue

            if line.startswith("event:"):
                current_event = line[6:].strip()
                continue

            if line.startswith("data:"):
                data_lines.append(line[5:].strip())
                continue

        if data_lines:
            yield current_event, "\n".join(data_lines)


class OpenAIProvider(BaseHTTPReasoningProvider):
    """OpenAI-compatible reasoning provider."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        super().__init__()
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._base_url = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        api_key = self._require_api_key(self._api_key, "OpenAI")
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _payload(self, request: ReasoningRequest, *, stream: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._extract_model(request, "gpt-4o"),
            "messages": [],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.stop_sequences:
            payload["stop"] = request.stop_sequences
        if stream:
            payload["stream"] = True

        if request.system_prompt:
            payload["messages"].append({"role": "system", "content": request.system_prompt})
        payload["messages"].append({"role": "user", "content": request.prompt})
        return payload

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}/chat/completions"
        payload = self._payload(request)
        started_at = time.monotonic()

        response = await self._client.post(url, json=payload, headers=self._headers())
        response.raise_for_status()
        data = response.json()

        latency_ms = round((time.monotonic() - started_at) * 1000, 1)
        choice = data["choices"][0]
        content = choice["message"]["content"]
        usage = self._normalize_usage(data.get("usage", {}))
        usage.setdefault("duration_ms", latency_ms)

        logger.debug(
            "openai_generate_ok",
            latency_ms=latency_ms,
            model=data.get("model", payload["model"]),
            total_tokens=usage.get("total_tokens"),
        )

        return self._base_response(
            content=content,
            raw_response=data,
            usage=usage,
            model_version=data.get("model", payload["model"]),
            provider_name="openai",
            finish_reason=choice.get("finish_reason"),
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str]:
        url = f"{self._base_url}/chat/completions"
        payload = self._payload(request, stream=True)

        async with self._stream_client.stream(
            "POST",
            url,
            json=payload,
            headers=self._headers(),
        ) as response:
            response.raise_for_status()

            async for _, data_line in self._iter_sse_data_lines(response):
                if data_line == "[DONE]":
                    return

                try:
                    chunk = json.loads(data_line)
                except json.JSONDecodeError:
                    logger.debug("openai_stream_invalid_json_ignored")
                    continue

                try:
                    delta = chunk["choices"][0]["delta"].get("content", "")
                except (KeyError, IndexError, AttributeError):
                    continue

                if delta:
                    yield delta


class AnthropicProvider(BaseHTTPReasoningProvider):
    """Anthropic Claude reasoning provider with robust SSE streaming."""

    _MESSAGES_URL = "https://api.anthropic.com/v1/messages"
    _ANTHROPIC_VERSION = "2023-06-01"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4.6",
    ) -> None:
        super().__init__()
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._model = model

    def _headers(self) -> dict[str, str]:
        api_key = self._require_api_key(self._api_key, "Anthropic")
        return {
            "x-api-key": api_key,
            "anthropic-version": self._ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    def _payload(self, request: ReasoningRequest, *, stream: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._extract_model(request, self._model),
            "max_tokens": request.max_tokens,
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": request.temperature,
        }
        if request.system_prompt:
            payload["system"] = request.system_prompt
        if request.stop_sequences:
            payload["stop_sequences"] = request.stop_sequences
        if stream:
            payload["stream"] = True
        return payload

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        payload = self._payload(request)
        started_at = time.monotonic()

        response = await self._client.post(
            self._MESSAGES_URL,
            json=payload,
            headers=self._headers(),
        )
        response.raise_for_status()
        data = response.json()

        latency_ms = round((time.monotonic() - started_at) * 1000, 1)

        text_parts: list[str] = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    text_parts.append(text)

        content = "".join(text_parts)
        usage = self._normalize_usage(data.get("usage", {}))
        usage.setdefault("duration_ms", latency_ms)

        logger.debug(
            "anthropic_generate_ok",
            latency_ms=latency_ms,
            model=data.get("model", payload["model"]),
        )

        return self._base_response(
            content=content,
            raw_response=data,
            usage=usage,
            model_version=data.get("model", payload["model"]),
            provider_name="anthropic",
            finish_reason=data.get("stop_reason"),
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str]:
        """Anthropic SSE streaming with buffered fallback.

        Anthropic documents these stream events:
        - message_start
        - content_block_start
        - content_block_delta
        - content_block_stop
        - message_delta
        - message_stop
        plus ping/error/unknown future events. We handle unknown events
        gracefully and only emit text deltas outward.
        """
        payload = self._payload(request, stream=True)
        started_at = time.monotonic()
        emitted_chars = 0

        try:
            async with self._stream_client.stream(
                "POST",
                self._MESSAGES_URL,
                json=payload,
                headers=self._headers(),
            ) as response:
                response.raise_for_status()

                async for event_name, data_line in self._iter_sse_data_lines(response):
                    if not data_line or data_line == "[DONE]":
                        continue

                    try:
                        event = json.loads(data_line)
                    except json.JSONDecodeError:
                        logger.debug("anthropic_stream_invalid_json_ignored")
                        continue

                    event_type = event.get("type") or event_name or ""

                    if event_type == "ping":
                        continue

                    if event_type == "error":
                        logger.error("anthropic_stream_api_error", error=event.get("error"))
                        raise RuntimeError(f"Anthropic stream error: {event.get('error')}")

                    if event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        delta_type = delta.get("type")

                        if delta_type == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                emitted_chars += len(text)
                                yield text
                            continue

                        # Ignore input_json_delta / thinking_delta / signature_delta
                        continue

                    if event_type == "message_stop":
                        logger.debug(
                            "anthropic_stream_complete",
                            emitted_chars=emitted_chars,
                            elapsed_ms=round((time.monotonic() - started_at) * 1000, 1),
                        )
                        return

                    # message_start / content_block_start / content_block_stop /
                    # message_delta / unknown future events are intentionally ignored

        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            logger.warning(
                "anthropic_stream_fallback_to_buffered",
                error=str(exc),
                elapsed_ms=round((time.monotonic() - started_at) * 1000, 1),
            )
            try:
                result = await self.generate(request)
                if result.content:
                    yield result.content
                return
            except Exception as fallback_exc:
                logger.error("anthropic_stream_fallback_failed", error=str(fallback_exc))
                raise RuntimeError(
                    "Anthropic streaming failed and buffered fallback also failed"
                ) from fallback_exc


class VLLMProvider(BaseHTTPReasoningProvider):
    """Local vLLM provider using the OpenAI-compatible server surface."""

    def __init__(self, base_url: str = "http://localhost:8000/v1") -> None:
        super().__init__()
        self._base_url = base_url.rstrip("/")

    def _payload(self, request: ReasoningRequest, *, stream: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._extract_model(request, "meta-llama-3.1-8b"),
            "messages": [],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "extra_body": {
                "triattention": request.metadata.get("triattention", True),
                "kv_budget": request.metadata.get("kv_budget", 12000),
            },
        }
        if stream:
            payload["stream"] = True
        if request.system_prompt:
            payload["messages"].append({"role": "system", "content": request.system_prompt})
        payload["messages"].append({"role": "user", "content": request.prompt})
        return payload

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}/chat/completions"
        payload = self._payload(request)
        started_at = time.monotonic()

        response = await self._client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

        latency_ms = round((time.monotonic() - started_at) * 1000, 1)
        choice = data["choices"][0]
        content = choice["message"]["content"]
        usage = self._normalize_usage(data.get("usage", {}))
        usage.setdefault("duration_ms", latency_ms)

        logger.debug(
            "vllm_generate_ok",
            latency_ms=latency_ms,
            model=data.get("model", payload["model"]),
            triattention=payload["extra_body"]["triattention"],
        )

        return self._base_response(
            content=content,
            raw_response=data,
            usage=usage,
            model_version=data.get("model", payload["model"]),
            provider_name="vllm",
            finish_reason=choice.get("finish_reason"),
            metadata={"triattention": payload["extra_body"]["triattention"]},
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str]:
        """vLLM streaming via the OpenAI-compatible SSE surface."""
        url = f"{self._base_url}/chat/completions"
        payload = self._payload(request, stream=True)

        try:
            async with self._stream_client.stream("POST", url, json=payload) as response:
                response.raise_for_status()

                async for _, data_line in self._iter_sse_data_lines(response):
                    if data_line == "[DONE]":
                        return

                    try:
                        chunk = json.loads(data_line)
                    except json.JSONDecodeError:
                        logger.debug("vllm_stream_invalid_json_ignored")
                        continue

                    try:
                        delta = chunk["choices"][0]["delta"].get("content", "")
                    except (KeyError, IndexError, AttributeError):
                        continue

                    if delta:
                        yield delta
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            logger.warning("vllm_stream_fallback_to_buffered", error=str(exc))
            result = await self.generate(request)
            if result.content:
                yield result.content
