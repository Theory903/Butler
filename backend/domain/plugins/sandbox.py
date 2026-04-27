import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class SandboxBackend(ABC):
    """Abstract base class for plugin sandbox backends."""

    @abstractmethod
    async def spawn(self, plugin_id: str, command: list[str], env: dict[str, str] = None) -> Any:
        """Spawn a new sandboxed process."""

    @abstractmethod
    async def terminate(self, plugin_id: str):
        """Terminate a sandboxed process."""


class SubprocessSandbox(SandboxBackend):
    """Subprocess-based isolation (Lane B).

    Lowest overhead, uses OS-level process isolation.
    """

    def __init__(self):
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    async def spawn(self, plugin_id: str, command: list[str], env: dict[str, str] = None) -> Any:
        if env is None:
            env = {}
        logger.info("sandbox_spawn_subprocess", plugin_id=plugin_id, command=command)
        process = await asyncio.create_subprocess_exec(
            *command, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        self._processes[plugin_id] = process
        return process

    async def terminate(self, plugin_id: str):
        if process := self._processes.pop(plugin_id, None):
            logger.info("sandbox_terminate_subprocess", plugin_id=plugin_id)
            process.terminate()
            await process.wait()


class DockerSandbox(SandboxBackend):
    """Docker-based isolation (Lane B).

    Higher isolation, requires Docker daemon.
    """

    def __init__(self, image: str):
        self.image = image
        self._containers: dict[str, str] = {}  # mapping plugin_id to container_id

    async def spawn(self, plugin_id: str, command: list[str], env: dict[str, str] = None) -> Any:
        if env is None:
            env = {}
        logger.info("sandbox_spawn_docker", plugin_id=plugin_id, image=self.image, command=command)
        # Mocking for now - in real implementation would use 'docker run' or docker-py
        # await asyncio.create_subprocess_exec("docker", "run", "-d", ...)
        return {"status": "started", "backend": "docker"}

    async def terminate(self, plugin_id: str):
        logger.info("sandbox_terminate_docker", plugin_id=plugin_id)
        # await asyncio.create_subprocess_exec("docker", "rm", "-f", ...)
