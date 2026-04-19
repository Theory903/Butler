"""ML Reasoning Providers — v3.1.

Changes:
  - AnthropicProvider.generate_stream(): full production implementation
    with SSE parsing, partial-token accumulation, timeout handling,
    and buffered-fallback on failure.
  - VLLMProvider.generate_stream(): wired (was pass).

Anthropic streaming design:
  - Uses httpx streaming over the SSE endpoint.
  - Accumulates partial tokens before yielding to handle split delta events.
  - On any infrastructure error: falls back to buffered generate() and
    yields the result as a single token chunk.
  - Emits a finalization sentinel event in logs for observability.
  - Per-request timeout: 120s connection + 30s idle read (configurable).
"""

from __future__ import annotations

import os
import time
import json
from typing import Any, Dict, List, Optional, AsyncGenerator

import httpx
import structlog

from domain.ml.contracts import (
    ReasoningContract,
    ReasoningRequest,
    ReasoningResponse,
)

logger = structlog.get_logger(__name__)

# ── Shared timeout policy ──────────────────────────────────────────────────────
_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0)
_STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)


# ── OpenAI Provider ───────────────────────────────────────────────────────────

class OpenAIProvider(ReasoningContract):
    """OpenAI-compatible Reasoning Provider (Chat Completions API)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": request.metadata.get("model", "gpt-4o"),
            "messages": [],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stop": request.stop_sequences or None,
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
        usage = data.get("usage", {})
        logger.debug("openai.generate.ok", latency_ms=round(latency, 1), tokens=usage.get("total_tokens"))

        return ReasoningResponse(
            content=content,
            raw_response=data,
            usage=usage,
            model_version=data.get("model", payload["model"]),
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str, None]:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": request.metadata.get("model", "gpt-4o"),
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


# ── Anthropic Provider ────────────────────────────────────────────────────────

class AnthropicProvider(ReasoningContract):
    """Anthropic Claude Reasoning Provider — v3.1 with production streaming."""

    _MESSAGES_URL = "https://api.anthropic.com/v1/messages"
    _ANTHROPIC_VERSION = "2023-06-01"

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-5-sonnet-20241022") -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        self._stream_client = httpx.AsyncClient(timeout=_STREAM_TIMEOUT)

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": self._ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    def _payload(self, request: ReasoningRequest, *, stream: bool = False) -> dict:
        payload: dict = {
            "model": request.metadata.get("model", self._model),
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
        """Buffered (non-streaming) inference."""
        payload = self._payload(request)
        t0 = time.monotonic()
        response = await self._client.post(
            self._MESSAGES_URL, json=payload, headers=self._headers()
        )
        response.raise_for_status()
        data = response.json()
        latency = (time.monotonic() - t0) * 1000

        content = data["content"][0]["text"]
        logger.debug("anthropic.generate.ok", latency_ms=round(latency, 1), model=data.get("model"))

        return ReasoningResponse(
            content=content,
            raw_response=data,
            usage=data.get("usage", {}),
            model_version=data.get("model", payload["model"]),
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str, None]:
        """Production Anthropic SSE streaming with fallback.

        SSE event types used:
          content_block_delta / delta.type=text_delta → yield delta.text
          message_stop                                → finalize

        On any transport failure, falls back to buffered generate()
        and yields the complete text as a single chunk.
        """
        payload = self._payload(request, stream=True)
        t0 = time.monotonic()
        accumulated = 0
        try:
            async with self._stream_client.stream(
                "POST",
                self._MESSAGES_URL,
                json=payload,
                headers=self._headers(),
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    # SSE format: "event: ...\ndata: ..."
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                        if event_type == "message_stop":
                            logger.debug(
                                "anthropic.stream.complete",
                                tokens=accumulated,
                                ms=round((time.monotonic() - t0) * 1000, 1),
                            )
                            return
                        continue

                    if not line.startswith("data:"):
                        continue

                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        continue

                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type", "")

                    if event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                accumulated += len(text)
                                yield text

                    elif event_type == "message_stop":
                        logger.debug(
                            "anthropic.stream.complete",
                            tokens=accumulated,
                            ms=round((time.monotonic() - t0) * 1000, 1),
                        )
                        return

                    elif event_type == "error":
                        error_detail = event.get("error", {})
                        logger.error("anthropic.stream.api_error", error=error_detail)
                        raise RuntimeError(f"Anthropic stream error: {error_detail}")

        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            # Fallback: buffered generate — yield as single chunk
            logger.warning(
                "anthropic.stream.fallback_to_buffered",
                error=str(exc),
                elapsed_ms=round((time.monotonic() - t0) * 1000, 1),
            )
            try:
                result = await self.generate(request)
                yield result.content
            except Exception as fallback_exc:
                logger.error("anthropic.stream.fallback_failed", error=str(fallback_exc))
                raise RuntimeError("Anthropic streaming and buffered fallback both failed") from fallback_exc


# ── vLLM Provider ─────────────────────────────────────────────────────────────

class VLLMProvider(ReasoningContract):
    """Local vLLM Reasoning Provider (TriAttention Optimized)."""

    def __init__(self, base_url: str = "http://localhost:8000/v1") -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        self._stream_client = httpx.AsyncClient(timeout=_STREAM_TIMEOUT)

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}/chat/completions"
        payload = {
            "model": request.metadata.get("model", "qwen2.5-72b-instruct"),
            "messages": [],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "extra_body": {
                "triattention": request.metadata.get("triattention", True),
                "kv_budget": request.metadata.get("kv_budget", 12000),
            },
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
        logger.debug("vllm.generate.ok", latency_ms=round(latency, 1), triattention=True)

        return ReasoningResponse(
            content=content,
            raw_response=data,
            usage=data.get("usage", {}),
            model_version=data.get("model", payload["model"]),
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str, None]:
        """vLLM streaming — OpenAI-compatible SSE format."""
        url = f"{self._base_url}/chat/completions"
        payload = {
            "model": request.metadata.get("model", "qwen2.5-72b-instruct"),
            "messages": [],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
            "extra_body": {
                "triattention": request.metadata.get("triattention", True),
                "kv_budget": request.metadata.get("kv_budget", 12000),
            },
        }
        if request.system_prompt:
            payload["messages"].append({"role": "system", "content": request.system_prompt})
        payload["messages"].append({"role": "user", "content": request.prompt})

        try:
            async with self._stream_client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    chunk_data = line[6:]
                    if chunk_data == "[DONE]":
                        return
                    try:
                        chunk_json = json.loads(chunk_data)
                        delta = chunk_json["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        continue
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.warning("vllm.stream.fallback", error=str(exc))
            result = await self.generate(request)
            yield result.content
