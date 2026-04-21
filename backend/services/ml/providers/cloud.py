"""Cloud LLM Providers — Azure, Amazon Bedrock, Alibaba, Kimi, Moonshot, Qwen, StepFun, MiniMax, Volcengine."""

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


# ── Azure OpenAI Provider ───────────────────────────────────────────────────

class AzureOpenAIProvider(ReasoningContract):
    """Microsoft Azure OpenAI API Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: str = "",
        api_version: str = "2024-02-15-preview",
        deployment_name: str = "gpt-4o",
    ) -> None:
        self._api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY")
        self._endpoint = endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        self._api_version = api_version
        self._deployment_name = deployment_name
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._endpoint}/openai/deployments/{self._deployment_name}/chat/completions?api-version={self._api_version}"
        headers = {
            "api-key": self._api_key,
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

        content = data["choices"][0]["message"]["content"]
        return ReasoningResponse(
            content=content,
            raw_response=data,
            usage=data.get("usage", {}),
            model_version=self._deployment_name,
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str, None]:
        url = f"{self._endpoint}/openai/deployments/{self._deployment_name}/chat/completions?api-version={self._api_version}"
        headers = {
            "api-key": self._api_key,
            "Content-Type": "application/json",
        }
        payload = {
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


# ── Amazon Bedrock Provider ────────────────────────────────────────────────

class AmazonBedrockProvider(ReasoningContract):
    """Amazon Bedrock API Provider (Claude, Llama, Mistral, Titan)."""

    def __init__(
        self,
        aws_access_key: Optional[str] = None,
        aws_secret_key: Optional[str] = None,
        region: str = "us-east-1",
        model: str = "anthropic.claude-3-sonnet-20240229-v1:0",
    ) -> None:
        import boto3
        self._client = boto3.client(
            "bedrock-runtime",
            aws_access_key_id=aws_access_key or os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=aws_secret_key or os.environ.get("AWS_SECRET_ACCESS_KEY"),
            region_name=region,
        )
        self._model = model

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": request.max_tokens,
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": request.temperature,
        }
        if request.system_prompt:
            body["system"] = [{"text": request.system_prompt}]

        import json
        response = self._client.invoke_model(
            modelId=self._model,
            body=json.dumps(body),
            accept="application/json",
            contentType="application/json",
        )
        import json
        data = json.loads(response["body"].read())

        content = data.get("content", [{}])[0].get("text", "")
        return ReasoningResponse(
            content=content,
            raw_response=data,
            usage={"input_tokens": data.get("usage", {}).get("input_tokens", 0), "output_tokens": data.get("usage", {}).get("output_tokens", 0)},
            model_version=self._model,
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str, None]:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": request.max_tokens,
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": request.temperature,
            "stream": True,
        }
        if request.system_prompt:
            body["system"] = [{"text": request.system_prompt}]

        import json
        response = self._client.invoke_model_with_response_stream(
            modelId=self._model,
            body=json.dumps(body),
            accept="application/json",
            contentType="application/json",
        )
        for event in response.get("body"):
            chunk = json.loads(event["chunk"]["bytes"])
            if chunk.get("type") == "content_block_delta":
                delta = chunk.get("delta", {}).get("text", "")
                if delta:
                    yield delta


# ── Alibaba (Qwen) Provider ─────────────────────────────────────────────────

class AlibabaProvider(ReasoningContract):
    """Alibaba Cloud Qwen API Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://dashscope.aliyuncs.com/api/v1",
        model: str = "qwen-turbo",
    ) -> None:
        self._api_key = api_key or os.environ.get("DASHSCOPE_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}/services/aigc/text-generation/generation"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": request.metadata.get("model", self._model),
            "input": {"prompt": request.prompt},
            "parameters": {
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
            }
        }

        t0 = time.monotonic()
        response = await self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        latency = (time.monotonic() - t0) * 1000

        content = data["output"]["text"]
        return ReasoningResponse(
            content=content,
            raw_response=data,
            usage=data.get("usage", {}),
            model_version=self._model,
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str, None]:
        url = f"{self._base_url}/services/aigc/text-generation/generation"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": request.metadata.get("model", self._model),
            "input": {"prompt": request.prompt},
            "parameters": {
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "incremental_output": True,
            }
        }

        async with self._client.stream("POST", url, json=payload, headers=headers) as response:
            async for line in response.aiter_lines():
                if line.strip():
                    try:
                        chunk = json.loads(line)
                        if chunk.get("output", {}).get("text"):
                            yield chunk["output"]["text"]
                    except Exception:
                        continue


# ── Moonshot (Kimi) Provider ───────────────────────────────────────────────

class MoonshotProvider(ReasoningContract):
    """Moonshot AI Kimi API Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.moonshot.cn/v1",
        model: str = "moonshot-v1-8k",
    ) -> None:
        self._api_key = api_key or os.environ.get("MOONSHOT_API_KEY")
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


# ── MiniMax Provider ────────────────────────────────────────────────────────

class MiniMaxProvider(ReasoningContract):
    """MiniMax API Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.minimax.chat/v1",
        model: str = "abab6.5s-chat",
    ) -> None:
        self._api_key = api_key or os.environ.get("MINIMAX_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        url = f"{self._base_url}/text/chatcompletion_v2"
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

        content = data["choices"][0]["message"]["content"]
        return ReasoningResponse(
            content=content,
            raw_response=data,
            usage=data.get("usage", {}),
            model_version=data.get("model", self._model),
        )

    async def generate_stream(self, request: ReasoningRequest) -> AsyncGenerator[str, None]:
        url = f"{self._base_url}/text/chatcompletion_v2"
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


# ── Volcengine (ByteDance) Provider ────────────────────────────────────────

class VolcengineProvider(ReasoningContract):
    """Volcengine (ByteDance) API Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
        model: str = "doubao-pro-32k",
    ) -> None:
        self._api_key = api_key or os.environ.get("VOLCENGINE_API_KEY")
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


# ── StepFun Provider ────────────────────────────────────────────────────────

class StepFunProvider(ReasoningContract):
    """StepFun API Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.stepfun.com/v1",
        model: str = "step-1v-8k",
    ) -> None:
        self._api_key = api_key or os.environ.get("STEPFUN_API_KEY")
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
