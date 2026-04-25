"""
WorkspaceManager - Tenant-Scoped Workspace Management

Production-grade workspace isolation for tenant file operations.
Ensures tenants cannot access each other's workspaces or escape to host system.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import structlog

from infrastructure.config import settings

logger = structlog.get_logger(__name__)


class WorkspaceManager:
    """
    Tenant-scoped workspace manager for file operations.

    All file operations must go through this manager.
    Never construct paths directly - always use WorkspaceManager.

    Workspace path pattern: /var/butler/tenants/{tenant_id}/executions/{execution_id}/
    """

    def __init__(self, base_dir: str = settings.BUTLER_DATA_DIR) -> None:
        """
        Initialize workspace manager.

        Args:
            base_dir: Base directory for Butler data
        """
        self._base_dir = Path(base_dir)
        self._tenants_dir = self._base_dir / "tenants"

    def get_workspace_path(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> Path:
        """
        Get tenant-scoped workspace path for an execution.

        Args:
            tenant_id: Tenant UUID
            execution_id: Execution UUID

        Returns:
            Path to tenant-scoped workspace directory

        Raises:
            ValueError: If tenant_id or execution_id contains path traversal attempts
        """
        # Validate inputs for path traversal
        self._validate_id(tenant_id, "tenant_id")
        self._validate_id(execution_id, "execution_id")

        return self._tenants_dir / tenant_id / "executions" / execution_id

    async def create_workspace(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> Path:
        """
        Create tenant-scoped workspace directory.

        Args:
            tenant_id: Tenant UUID
            execution_id: Execution UUID

        Returns:
            Path to created workspace directory

        Raises:
            OSError: If directory creation fails
            ValueError: If path traversal detected
        """
        workspace_path = self.get_workspace_path(tenant_id, execution_id)

        # Create directory with restricted permissions (owner only)
        workspace_path.mkdir(parents=True, exist_ok=True, mode=0o700)

        logger.info(
            "workspace_created",
            tenant_id=tenant_id,
            execution_id=execution_id,
            path=str(workspace_path),
        )

        return workspace_path

    async def cleanup_workspace(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> None:
        """
        Cleanup tenant-scoped workspace directory.

        Args:
            tenant_id: Tenant UUID
            execution_id: Execution UUID
        """
        workspace_path = self.get_workspace_path(tenant_id, execution_id)

        if workspace_path.exists():
            # Remove entire workspace tree
            shutil.rmtree(workspace_path)

            logger.info(
                "workspace_cleaned",
                tenant_id=tenant_id,
                execution_id=execution_id,
                path=str(workspace_path),
            )

    async def get_file_path(
        self,
        tenant_id: str,
        execution_id: str,
        filename: str,
    ) -> Path:
        """
        Get tenant-scoped file path within workspace.

        Args:
            tenant_id: Tenant UUID
            execution_id: Execution UUID
            filename: File name (relative to workspace)

        Returns:
            Full path to file within tenant workspace

        Raises:
            ValueError: If path traversal detected in filename
        """
        # Validate filename for path traversal
        self._validate_filename(filename)

        workspace_path = self.get_workspace_path(tenant_id, execution_id)
        file_path = workspace_path / filename

        # Ensure resolved path is within workspace
        resolved_path = file_path.resolve()
        if not str(resolved_path).startswith(str(workspace_path.resolve())):
            raise ValueError(f"Path traversal detected: {filename} resolves outside workspace")

        return file_path

    def _validate_id(self, value: str, param_name: str) -> None:
        """
        Validate ID for path traversal attempts.

        Args:
            value: ID value to validate
            param_name: Parameter name for error messages

        Raises:
            ValueError: If path traversal detected
        """
        # Check for path traversal patterns
        if ".." in value or "/" in value or "\\" in value:
            raise ValueError(f"Invalid {param_name}: path traversal detected")

        # Check for null bytes
        if "\x00" in value:
            raise ValueError(f"Invalid {param_name}: null byte detected")

    def _validate_filename(self, filename: str) -> None:
        """
        Validate filename for path traversal attempts.

        Args:
            filename: Filename to validate

        Raises:
            ValueError: If path traversal detected
        """
        # Check for absolute paths
        if os.path.isabs(filename):
            raise ValueError(f"Absolute paths not allowed: {filename}")

        # Check for path traversal
        if ".." in filename or filename.startswith("/"):
            raise ValueError(f"Path traversal detected in filename: {filename}")

        # Check for null bytes
        if "\x00" in filename:
            raise ValueError(f"Null byte detected in filename: {filename}")

    @classmethod
    def get_instance(cls) -> WorkspaceManager:
        """Return the global workspace manager instance."""
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance
