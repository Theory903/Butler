"""SandboxManager for code execution isolation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SandboxStatus(str, Enum):
    """Sandbox execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    KILLED = "killed"


@dataclass(frozen=True, slots=True)
class SandboxConfig:
    """Sandbox configuration for code execution.

    Rule: All L4 tools must run in sandbox.
    """

    enable_network: bool = False
    enable_filesystem: bool = False
    max_memory_mb: int = 256
    max_execution_time_seconds: int = 30
    enable_gpu: bool = False

    @classmethod
    def default(cls) -> SandboxConfig:
        """Default sandbox config for code execution."""
        return cls(
            enable_network=False,
            enable_filesystem=False,
            max_memory_mb=256,
            max_execution_time_seconds=30,
            enable_gpu=False,
        )

    @classmethod
    def permissive(cls) -> SandboxConfig:
        """Permissive sandbox config for trusted code."""
        return cls(
            enable_network=True,
            enable_filesystem=True,
            max_memory_mb=1024,
            max_execution_time_seconds=300,
            enable_gpu=False,
        )


@dataclass(frozen=True, slots=True)
class SandboxExecution:
    """Sandbox execution result."""

    execution_id: str
    status: SandboxStatus
    stdout: str
    stderr: str
    return_code: int | None
    execution_time_seconds: float

    def is_successful(self) -> bool:
        """Check if execution was successful."""
        return self.status == SandboxStatus.COMPLETED and self.return_code == 0


class SandboxManager:
    """Sandbox manager for code execution isolation.

    Rule: Never execute user code outside sandbox.
    """

    def __init__(self, config: SandboxConfig) -> None:
        self.config = config

    def execute_python(
        self,
        code: str,
        execution_id: str,
    ) -> SandboxExecution:
        """Execute Python code in sandbox.

        TODO: Integrate with actual sandbox (e.g., Docker, Firecracker).
        For now, return a stub execution.
        """
        return SandboxExecution(
            execution_id=execution_id,
            status=SandboxStatus.COMPLETED,
            stdout="",
            stderr="",
            return_code=0,
            execution_time_seconds=0.0,
        )

    def execute_shell(
        self,
        command: str,
        execution_id: str,
    ) -> SandboxExecution:
        """Execute shell command in sandbox.

        Rule: Shell execution requires explicit approval.
        """
        return SandboxExecution(
            execution_id=execution_id,
            status=SandboxStatus.FAILED,
            stdout="",
            stderr="Shell execution not allowed in current configuration",
            return_code=1,
            execution_time_seconds=0.0,
        )
