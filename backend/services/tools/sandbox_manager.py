"""SandboxManager — Phase 8d.

Manages the lifecycle of containerized tool execution environments.
Ensures high-risk tools (Terminal, Code Execution, File I/O) are isolated
within Docker containers.

Governed by: docs/rules/SYSTEM_RULES.md v2.0 §Security.6 (Perimeter)
"""

from __future__ import annotations

import os

import structlog

from infrastructure.config import settings
from integrations.hermes.tools.environments.docker import DockerEnvironment

logger = structlog.get_logger(__name__)


class SandboxManager:
    """Manages Docker sandboxes for tool execution.

    Provides container reusability within a session to preserve state
    (e.g., installed packages, local files) while maintaining isolation.
    """

    def __init__(self, data_dir: str = settings.BUTLER_DATA_DIR):
        self._data_dir = data_dir
        # key: session_id, value: DockerEnvironment
        self._active_sandboxes: dict[str, DockerEnvironment] = {}

    async def get_sandbox(
        self,
        session_id: str,
        tenant_id: str,  # Required for multi-tenant isolation
        profile: str = "docker",
        image: str | None = None,
    ) -> DockerEnvironment:
        """Get or create an isolated environment for the given session.

        Args:
            tenant_id: Required tenant UUID for multi-tenant isolation
        """
        # Use tenant_id + session_id as key for tenant isolation
        sandbox_key = f"{tenant_id}:{session_id}"

        if sandbox_key in self._active_sandboxes:
            logger.debug("sandbox_reused", session_id=session_id, tenant_id=tenant_id)
            return self._active_sandboxes[sandbox_key]

        if profile != "docker":
            # For now, we only manage Docker here. Others handled by Hermes legacy.
            raise ValueError(f"Unsupported sandbox profile: {profile}")

        # Choose image (fallback to default)
        target_image = image or os.getenv(
            "TERMINAL_DOCKER_IMAGE", "nikolaik/python-nodejs:python3.11-nodejs20"
        )

        logger.info(
            "sandbox_creating",
            session_id=session_id,
            tenant_id=tenant_id,
            profile=profile,
            image=target_image,
        )

        env = DockerEnvironment(
            image=target_image,
            task_id=session_id,
            persistent_filesystem=True,  # Preserve state within the session
            cpu=1.0,
            memory=2048,  # 2GB default
            disk=10240,  # 10GB default
        )

        self._active_sandboxes[sandbox_key] = env
        return env

    async def close_sandbox(self, session_id: str, tenant_id: str) -> None:
        """Cleanup a sandbox when the session ends or is purged.

        Args:
            tenant_id: Required tenant UUID for multi-tenant isolation
        """
        sandbox_key = f"{tenant_id}:{session_id}"
        env = self._active_sandboxes.pop(sandbox_key, None)
        if env:
            logger.info("sandbox_closing", session_id=session_id, tenant_id=tenant_id)
            env.cleanup()

    async def reap_all(self) -> None:
        """Emergency cleanup of all active sandboxes."""
        for sandbox_key in list(self._active_sandboxes.keys()):
            # Parse tenant_id:session_id from key
            parts = sandbox_key.split(":", 1)
            if len(parts) == 2:
                tenant_id, session_id = parts
                await self.close_sandbox(session_id, tenant_id)
            else:
                # Legacy key format (session_id only)
                await self.close_sandbox(sandbox_key, "")

    @classmethod
    def get_instance(cls) -> SandboxManager:
        """Return the global sandbox manager instance."""
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance
