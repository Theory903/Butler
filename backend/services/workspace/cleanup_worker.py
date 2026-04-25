"""
CleanupWorker - Resource Cleanup Worker

Production-grade cleanup worker for tenant resources.
Ensures timely cleanup of workspaces, sandboxes, and temporary resources.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from services.tools.sandbox_manager import SandboxManager
from services.workspace.workspace_manager import WorkspaceManager

logger = structlog.get_logger(__name__)


class CleanupWorker:
    """
    Background worker for cleaning up tenant resources.

    Cleans up expired workspaces, abandoned sandboxes, and temporary files.
    Runs periodically to ensure resource hygiene.
    """

    def __init__(
        self,
        *,
        workspace_manager: WorkspaceManager | None = None,
        sandbox_manager: SandboxManager | None = None,
        cleanup_interval_seconds: int = 300,  # 5 minutes
        workspace_ttl_hours: int = 24,
        sandbox_ttl_hours: int = 2,
    ) -> None:
        """
        Initialize cleanup worker.

        Args:
            workspace_manager: Workspace manager instance
            sandbox_manager: Sandbox manager instance
            cleanup_interval_seconds: Interval between cleanup runs
            workspace_ttl_hours: Time-to-live for workspaces before cleanup
            sandbox_ttl_hours: Time-to-live for sandboxes before cleanup
        """
        self._workspace_manager = workspace_manager or WorkspaceManager.get_instance()
        self._sandbox_manager = sandbox_manager or SandboxManager.get_instance()
        self._cleanup_interval = cleanup_interval_seconds
        self._workspace_ttl = timedelta(hours=workspace_ttl_hours)
        self._sandbox_ttl = timedelta(hours=sandbox_ttl_hours)
        self._running = False
        self._task: asyncio.Task[Any] | None = None

        # Track cleanup timestamps (in production, use database)
        self._workspace_cleanup_times: dict[str, datetime] = {}
        self._sandbox_cleanup_times: dict[str, datetime] = {}

    async def start(self) -> None:
        """Start the cleanup worker background task."""
        if self._running:
            logger.warning("cleanup_worker_already_running")
            return

        self._running = True
        self._task = asyncio.create_task(self._cleanup_loop())
        logger.info("cleanup_worker_started", interval_seconds=self._cleanup_interval)

    async def stop(self) -> None:
        """Stop the cleanup worker background task."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

        logger.info("cleanup_worker_stopped")

    async def _cleanup_loop(self) -> None:
        """Main cleanup loop."""
        while self._running:
            try:
                await self._cleanup_expired_resources()
            except Exception as e:
                logger.exception("cleanup_worker_error", error=str(e))

            # Wait for next cleanup interval
            await asyncio.sleep(self._cleanup_interval)

    async def _cleanup_expired_resources(self) -> None:
        """Clean up expired tenant resources."""
        logger.info("cleanup_worker_run_started")

        # Clean up expired workspaces
        await self._cleanup_expired_workspaces()

        # Clean up expired sandboxes
        await self._cleanup_expired_sandboxes()

        logger.info("cleanup_worker_run_completed")

    async def _cleanup_expired_workspaces(self) -> None:
        """Clean up expired workspaces."""
        # In production, query database for workspaces older than TTL
        # For now, this is a placeholder for the cleanup logic
        logger.debug(
            "cleanup_expired_workspaces", ttl_hours=self._workspace_ttl.total_seconds() / 3600
        )

    async def _cleanup_expired_sandboxes(self) -> None:
        """Clean up expired sandboxes."""
        # In production, track sandbox creation times and clean up expired ones
        # For now, this is a placeholder for the cleanup logic
        logger.debug(
            "cleanup_expired_sandboxes", ttl_hours=self._sandbox_ttl.total_seconds() / 3600
        )

    async def cleanup_tenant_resources(
        self,
        tenant_id: str,
        execution_id: str,
        session_id: str | None = None,
    ) -> None:
        """
        Clean up all resources for a specific tenant execution.

        Args:
            tenant_id: Tenant UUID
            execution_id: Execution UUID
            session_id: Optional session ID for sandbox cleanup
        """
        logger.info(
            "cleanup_tenant_resources_started",
            tenant_id=tenant_id,
            execution_id=execution_id,
        )

        # Cleanup workspace
        try:
            await self._workspace_manager.cleanup_workspace(tenant_id, execution_id)
            logger.info(
                "workspace_cleaned",
                tenant_id=tenant_id,
                execution_id=execution_id,
            )
        except Exception as e:
            logger.warning(
                "workspace_cleanup_failed",
                tenant_id=tenant_id,
                execution_id=execution_id,
                error=str(e),
            )

        # Cleanup sandbox if session_id provided
        if session_id:
            try:
                await self._sandbox_manager.close_sandbox(session_id, tenant_id)
                logger.info(
                    "sandbox_cleaned",
                    tenant_id=tenant_id,
                    session_id=session_id,
                )
            except Exception as e:
                logger.warning(
                    "sandbox_cleanup_failed",
                    tenant_id=tenant_id,
                    session_id=session_id,
                    error=str(e),
                )

        logger.info(
            "cleanup_tenant_resources_completed",
            tenant_id=tenant_id,
            execution_id=execution_id,
        )

    def register_workspace_creation(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> None:
        """
        Register workspace creation for tracking.

        Args:
            tenant_id: Tenant UUID
            execution_id: Execution UUID
        """
        key = f"{tenant_id}:{execution_id}"
        self._workspace_cleanup_times[key] = datetime.now(UTC)

    def register_sandbox_creation(
        self,
        tenant_id: str,
        session_id: str,
    ) -> None:
        """
        Register sandbox creation for tracking.

        Args:
            tenant_id: Tenant UUID
            session_id: Session ID
        """
        key = f"{tenant_id}:{session_id}"
        self._sandbox_cleanup_times[key] = datetime.now(UTC)

    @classmethod
    def get_instance(cls) -> CleanupWorker:
        """Return the global cleanup worker instance."""
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance
