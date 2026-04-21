"""Code — Codex, GitHub Copilot, KiloCode."""

from __future__ import annotations
import os
import json
from typing import Optional, AsyncGenerator
from abc import ABC, abstractmethod

import httpx
import structlog

logger = structlog.get_logger(__name__)
_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0)


class CodeExecutionRequest:
    def __init__(
        self,
        code: str,
        language: str = "python",
        stdin: str = "",
        timeout: int = 30,
        metadata: dict = None,
    ):
        self.code = code
        self.language = language
        self.stdin = stdin
        self.timeout = timeout
        self.metadata = metadata or {}


class CodeExecutionResponse:
    def __init__(
        self,
        stdout: str = "",
        stderr: str = "",
        exit_code: int = 0,
        execution_time: float = 0.0,
        metadata: dict = None,
    ):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.execution_time = execution_time
        self.metadata = metadata or {}


class BaseCodeProvider(ABC):
    @abstractmethod
    async def execute(self, request: CodeExecutionRequest) -> CodeExecutionResponse:
        pass

    @abstractmethod
    async def chat(self, prompt: str, context: dict = None) -> str:
        pass


class CodexProvider(BaseCodeProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.openai.com/v1",
    ):
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=_TIMEOUT)

    async def execute(self, request: CodeExecutionRequest) -> CodeExecutionResponse:
        logger.warning("codex_execute_not_supported")
        return CodeExecutionResponse(stderr="Codex does not support direct execution")

    async def chat(self, prompt: str, context: dict = None) -> str:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        messages = [{"role": "user", "content": prompt}]
        if context:
            messages.insert(0, {"role": "system", "content": json.dumps(context)})
        payload = {"model": "computer-use-preview", "messages": messages, "stream": False}
        resp = await self._client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


class GitHubCopilotProvider(BaseCodeProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.github.com",
    ):
        self._api_key = api_key or os.environ.get("GITHUB_TOKEN")
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=_TIMEOUT)

    async def execute(self, request: CodeExecutionRequest) -> CodeExecutionResponse:
        url = f"{self._base_url}/copilot/code/execute"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {"code": request.code, "language": request.language}
        resp = await self._client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return CodeExecutionResponse(
            stdout=data.get("output", ""),
            stderr=data.get("error", ""),
            exit_code=data.get("exit_code", 0),
        )

    async def chat(self, prompt: str, context: dict = None) -> str:
        url = f"{self._base_url}/copilot/chat"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {"prompt": prompt}
        resp = await self._client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data.get("completion", "")


class KiloCodeProvider(BaseCodeProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.kilocode.ai/v1",
    ):
        self._api_key = api_key or os.environ.get("KILOCODE_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=_TIMEOUT)

    async def execute(self, request: CodeExecutionRequest) -> CodeExecutionResponse:
        url = f"{self._base_url}/execute"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        payload = {"code": request.code, "language": request.language}
        resp = await self._client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return CodeExecutionResponse(
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            exit_code=data.get("exit_code", 0),
        )

    async def chat(self, prompt: str, context: dict = None) -> str:
        url = f"{self._base_url}/chat"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        payload = {"prompt": prompt}
        resp = await self._client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")


class CodeProviderFactory:
    _instances: dict = {}

    @classmethod
    def get_provider(cls, provider_type: str):
        if provider_type in cls._instances:
            return cls._instances[provider_type]
        provider = {
            "codex": lambda: CodexProvider(),
            "github-copilot": lambda: GitHubCopilotProvider(),
            "kilocode": lambda: KiloCodeProvider(),
        }.get(provider_type)()
        cls._instances[provider_type] = provider
        return provider