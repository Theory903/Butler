"""Cloud LLM Providers — normalized production provider layer.

Providers covered:
- Azure OpenAI
- Amazon Bedrock
- Alibaba Cloud / DashScope
- Moonshot / Kimi
- MiniMax
- Volcengine
- StepFun

Design goals:
- avoid duplicated provider logic
- prefer unified provider adapters where APIs are OpenAI-compatible
- isolate true non-compatible providers behind dedicated implementations
- avoid blocking the event loop on sync SDK calls
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import structlog

from domain.ml.contracts import ReasoningRequest, ReasoningResponse
from services.ml.providers.llm import (
    BaseReasoningHTTPProvider,
    OpenAICompatibleProvider,
    ProviderConfigurationError,
)

logger = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0)
_STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)


class AzureOpenAIProvider(BaseReasoningHTTPProvider):
    """Azure OpenAI provider using Azure deployment-based chat completions."""

    provider_name = "azure"

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        api_version: str | None = None,
        deployment_name: str | None = None,
    ) -> None:
        super().__init__()
        self._api_key = (
            api_key or os.environ.get("AZURE_OPENAI_KEY") or os.environ.get("AZURE_OPENAI_API_KEY")
        )
        self._endpoint = (endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT") or "").rstrip("/")
        self._api_version = (
            api_version or os.environ.get("AZURE_OPENAI_API_VERSION") or "2024-10-21"
        )
        self._deployment_name = (
            deployment_name
            or os.environ.get("AZURE_OPENAI_DEPLOYMENT")
            or os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT")
            or "gpt-4o"
        )

    def _headers(self) -> dict[str, str]:
        api_key = self._require_api_key(self._api_key)
        return {
            "api-key": api_key,
            "Content-Type": "application/json",
        }

    def _build_url(self) -> str:
        if not self._endpoint:
            raise ProviderConfigurationError("azure endpoint is not configured")
        return (
            f"{self._endpoint}/openai/deployments/{self._deployment_name}"
            f"/chat/completions?api-version={self._api_version}"
        )

    def _payload(self, request: ReasoningRequest, *, stream: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
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
        url = self._build_url()
        # SSRF protection check
        self._check_egress_policy(url)

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

        return self._make_response(
            content=content,
            raw_response=data,
            usage=usage,
            model_version=self._deployment_name,
            finish_reason=choice.get("finish_reason"),
            metadata={"api_version": self._api_version},
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str]:
        url = self._build_url()
        # SSRF protection check
        self._check_egress_policy(url)

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
                        import json

                        chunk = json.loads(data_line)
                    except Exception:
                        logger.debug("azure_stream_invalid_json_ignored")
                        continue

                    try:
                        delta = chunk["choices"][0]["delta"].get("content", "")
                    except (KeyError, IndexError, AttributeError):
                        continue

                    if delta:
                        yield delta

        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            logger.warning("azure_stream_fallback_to_buffered", error=str(exc))
            result = await self.generate(request)
            if result.content:
                yield result.content


class AmazonBedrockProvider(BaseReasoningHTTPProvider):
    """Amazon Bedrock provider using Converse / ConverseStream.

    Uses boto3 under the hood but isolates sync SDK calls behind asyncio.to_thread
    so the event loop does not get blocked by the AWS SDK.
    """

    provider_name = "bedrock"

    def __init__(
        self,
        region: str | None = None,
        model: str | None = None,
        aws_access_key: str | None = None,
        aws_secret_key: str | None = None,
        aws_session_token: str | None = None,
    ) -> None:
        super().__init__()
        import boto3

        self._region = (
            region
            or os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or "us-east-1"
        )
        self._model = (
            model
            or os.environ.get("BEDROCK_MODEL_ID")
            or "anthropic.claude-3-7-sonnet-20250219-v1:0"
        )

        client_kwargs: dict[str, Any] = {"region_name": self._region}

        access_key = aws_access_key or os.environ.get("AWS_ACCESS_KEY_ID")
        secret_key = aws_secret_key or os.environ.get("AWS_SECRET_ACCESS_KEY")
        session_token = aws_session_token or os.environ.get("AWS_SESSION_TOKEN")

        if access_key:
            client_kwargs["aws_access_key_id"] = access_key
        if secret_key:
            client_kwargs["aws_secret_access_key"] = secret_key
        if session_token:
            client_kwargs["aws_session_token"] = session_token

        self._bedrock = boto3.client("bedrock-runtime", **client_kwargs)

    def _system_payload(self, request: ReasoningRequest) -> list[dict[str, Any]] | None:
        if not request.system_prompt:
            return None
        return [{"text": request.system_prompt}]

    def _messages_payload(self, request: ReasoningRequest) -> list[dict[str, Any]]:
        return [
            {
                "role": "user",
                "content": [{"text": request.prompt}],
            }
        ]

    def _inference_config(self, request: ReasoningRequest) -> dict[str, Any]:
        config: dict[str, Any] = {
            "maxTokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.stop_sequences:
            config["stopSequences"] = request.stop_sequences
        return config

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        started_at = time.monotonic()

        def _call() -> dict[str, Any]:
            kwargs: dict[str, Any] = {
                "modelId": self._model,
                "messages": self._messages_payload(request),
                "inferenceConfig": self._inference_config(request),
            }
            system = self._system_payload(request)
            if system:
                kwargs["system"] = system
            return self._bedrock.converse(**kwargs)

        data = await asyncio.to_thread(_call)
        latency_ms = round((time.monotonic() - started_at) * 1000, 1)

        output = data.get("output", {})
        message = output.get("message", {})
        content_blocks = message.get("content", [])
        parts: list[str] = []

        for block in content_blocks:
            text = block.get("text")
            if text:
                parts.append(text)

        usage = dict(data.get("usage", {}) or {})
        usage.setdefault("duration_ms", latency_ms)

        return self._make_response(
            content="".join(parts),
            raw_response=data,
            usage=usage,
            model_version=self._model,
            finish_reason=data.get("stopReason"),
            metadata={"region": self._region},
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str]:
        def _start_stream():
            kwargs: dict[str, Any] = {
                "modelId": self._model,
                "messages": self._messages_payload(request),
                "inferenceConfig": self._inference_config(request),
            }
            system = self._system_payload(request)
            if system:
                kwargs["system"] = system
            return self._bedrock.converse_stream(**kwargs)

        try:
            response = await asyncio.to_thread(_start_stream)
            stream_body = response.get("stream")

            if stream_body is None:
                result = await self.generate(request)
                if result.content:
                    yield result.content
                return

            for event in stream_body:
                content_delta = event.get("contentBlockDelta")
                if content_delta:
                    delta = content_delta.get("delta", {})
                    text = delta.get("text", "")
                    if text:
                        yield text
                    continue

                message_stop = event.get("messageStop")
                if message_stop:
                    return

        except Exception as exc:
            logger.warning("bedrock_stream_fallback_to_buffered", error=str(exc))
            result = await self.generate(request)
            if result.content:
                yield result.content


class AlibabaProvider(OpenAICompatibleProvider):
    """Alibaba Cloud / DashScope provider using OpenAI-compatible surface."""

    provider_name = "alibaba"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        model: str = "qwen-plus",
    ) -> None:
        super().__init__(
            api_key=api_key or os.environ.get("DASHSCOPE_API_KEY"),
            base_url=base_url,
            default_model=model,
        )


class MoonshotProvider(OpenAICompatibleProvider):
    """Moonshot / Kimi provider using OpenAI-compatible surface."""

    provider_name = "moonshot"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.moonshot.ai/v1",
        model: str = "kimi-k2.5",
    ) -> None:
        super().__init__(
            api_key=api_key or os.environ.get("MOONSHOT_API_KEY"),
            base_url=base_url,
            default_model=model,
        )


class MiniMaxProvider(OpenAICompatibleProvider):
    """MiniMax provider using OpenAI-compatible surface.

    MiniMax also documents other compatible surfaces, but OpenAI-compatible
    chat completions keeps Butler's provider layer simpler.
    """

    provider_name = "minimax"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.minimaxi.com/v1",
        model: str = "MiniMax-M2.5",
    ) -> None:
        super().__init__(
            api_key=api_key or os.environ.get("MINIMAX_API_KEY"),
            base_url=base_url,
            default_model=model,
        )


class VolcengineProvider(OpenAICompatibleProvider):
    """Volcengine / Doubao provider using OpenAI-compatible chat surface."""

    provider_name = "volcengine"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
        model: str = "doubao-1.5-pro-32k",
    ) -> None:
        super().__init__(
            api_key=api_key or os.environ.get("VOLCENGINE_API_KEY"),
            base_url=base_url,
            default_model=model,
        )


class StepFunProvider(OpenAICompatibleProvider):
    """StepFun provider using OpenAI-compatible chat surface."""

    provider_name = "stepfun"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.stepfun.com/v1",
        model: str = "step-3.5",
    ) -> None:
        super().__init__(
            api_key=api_key or os.environ.get("STEPFUN_API_KEY"),
            base_url=base_url,
            default_model=model,
        )
