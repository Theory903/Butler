"""Comprehensive tests for SandboxManager.

Tests cover:
- SandboxStatus enum
- SandboxConfig dataclass and factory methods
- SandboxExecution dataclass and methods
- SandboxManager initialization and methods
- Edge cases and error handling
"""

import dataclasses

import pytest

from domain.sandbox.manager import (
    SandboxConfig,
    SandboxExecution,
    SandboxManager,
    SandboxStatus,
)


class TestSandboxStatus:
    """Test SandboxStatus enum."""

    def test_status_values(self):
        """Test all status values exist."""
        assert SandboxStatus.PENDING.value == "pending"
        assert SandboxStatus.RUNNING.value == "running"
        assert SandboxStatus.COMPLETED.value == "completed"
        assert SandboxStatus.FAILED.value == "failed"
        assert SandboxStatus.TIMEOUT.value == "timeout"
        assert SandboxStatus.KILLED.value == "killed"

    def test_status_comparison(self):
        """Test status comparison."""
        assert SandboxStatus.RUNNING == SandboxStatus.RUNNING
        assert SandboxStatus.RUNNING != SandboxStatus.COMPLETED


class TestSandboxConfig:
    """Test SandboxConfig dataclass."""

    def test_default_config(self):
        """Test default sandbox config."""
        config = SandboxConfig.default()
        assert config.enable_network is False
        assert config.enable_filesystem is False
        assert config.max_memory_mb == 256
        assert config.max_execution_time_seconds == 30
        assert config.enable_gpu is False

    def test_permissive_config(self):
        """Test permissive sandbox config."""
        config = SandboxConfig.permissive()
        assert config.enable_network is True
        assert config.enable_filesystem is True
        assert config.max_memory_mb == 1024
        assert config.max_execution_time_seconds == 300
        assert config.enable_gpu is False

    def test_custom_config(self):
        """Test custom sandbox config."""
        config = SandboxConfig(
            enable_network=True,
            enable_filesystem=False,
            max_memory_mb=512,
            max_execution_time_seconds=60,
            enable_gpu=True,
        )
        assert config.enable_network is True
        assert config.enable_filesystem is False
        assert config.max_memory_mb == 512
        assert config.max_execution_time_seconds == 60
        assert config.enable_gpu is True

    def test_config_frozen(self):
        """Test SandboxConfig is frozen (immutable)."""
        config = SandboxConfig.default()
        with pytest.raises(dataclasses.FrozenInstanceError):
            config.enable_network = True  # type: ignore

    def test_config_with_zero_values(self):
        """Test config with zero values."""
        config = SandboxConfig(
            enable_network=False,
            enable_filesystem=False,
            max_memory_mb=0,
            max_execution_time_seconds=0,
            enable_gpu=False,
        )
        assert config.max_memory_mb == 0
        assert config.max_execution_time_seconds == 0

    def test_config_with_negative_values(self):
        """Test config with negative values (should be allowed)."""
        config = SandboxConfig(
            enable_network=False,
            enable_filesystem=False,
            max_memory_mb=-1,
            max_execution_time_seconds=-1,
            enable_gpu=False,
        )
        assert config.max_memory_mb == -1
        assert config.max_execution_time_seconds == -1


class TestSandboxExecution:
    """Test SandboxExecution dataclass."""

    def test_successful_execution(self):
        """Test successful execution result."""
        execution = SandboxExecution(
            execution_id="exec_1",
            status=SandboxStatus.COMPLETED,
            stdout="output",
            stderr="",
            return_code=0,
            execution_time_seconds=1.0,
        )
        assert execution.execution_id == "exec_1"
        assert execution.status == SandboxStatus.COMPLETED
        assert execution.stdout == "output"
        assert execution.stderr == ""
        assert execution.return_code == 0
        assert execution.execution_time_seconds == 1.0

    def test_failed_execution(self):
        """Test failed execution result."""
        execution = SandboxExecution(
            execution_id="exec_1",
            status=SandboxStatus.FAILED,
            stdout="",
            stderr="error",
            return_code=1,
            execution_time_seconds=1.0,
        )
        assert execution.status == SandboxStatus.FAILED
        assert execution.return_code == 1

    def test_is_successful_true(self):
        """Test is_successful returns True."""
        execution = SandboxExecution(
            execution_id="exec_1",
            status=SandboxStatus.COMPLETED,
            stdout="output",
            stderr="",
            return_code=0,
            execution_time_seconds=1.0,
        )
        assert execution.is_successful() is True

    def test_is_successful_false_non_zero_return(self):
        """Test is_successful returns False with non-zero return code."""
        execution = SandboxExecution(
            execution_id="exec_1",
            status=SandboxStatus.COMPLETED,
            stdout="output",
            stderr="error",
            return_code=1,
            execution_time_seconds=1.0,
        )
        assert execution.is_successful() is False

    def test_is_successful_false_failed_status(self):
        """Test is_successful returns False with failed status."""
        execution = SandboxExecution(
            execution_id="exec_1",
            status=SandboxStatus.FAILED,
            stdout="",
            stderr="error",
            return_code=0,
            execution_time_seconds=1.0,
        )
        assert execution.is_successful() is False

    def test_is_successful_false_timeout_status(self):
        """Test is_successful returns False with timeout status."""
        execution = SandboxExecution(
            execution_id="exec_1",
            status=SandboxStatus.TIMEOUT,
            stdout="",
            stderr="timeout",
            return_code=None,
            execution_time_seconds=30.0,
        )
        assert execution.is_successful() is False

    def test_execution_frozen(self):
        """Test SandboxExecution is frozen (immutable)."""
        execution = SandboxExecution(
            execution_id="exec_1",
            status=SandboxStatus.RUNNING,
            stdout="",
            stderr="",
            return_code=None,
            execution_time_seconds=0.0,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            execution.status = SandboxStatus.COMPLETED  # type: ignore

    def test_execution_with_none_return_code(self):
        """Test execution with None return code."""
        execution = SandboxExecution(
            execution_id="exec_1",
            status=SandboxStatus.RUNNING,
            stdout="",
            stderr="",
            return_code=None,
            execution_time_seconds=0.0,
        )
        assert execution.return_code is None

    def test_execution_with_large_output(self):
        """Test execution with large output."""
        large_output = "output " * 10000
        execution = SandboxExecution(
            execution_id="exec_1",
            status=SandboxStatus.COMPLETED,
            stdout=large_output,
            stderr="",
            return_code=0,
            execution_time_seconds=1.0,
        )
        assert len(execution.stdout) == len(large_output)


class TestSandboxManager:
    """Test SandboxManager class."""

    def test_init_with_config(self):
        """Test SandboxManager initialization."""
        config = SandboxConfig.default()
        manager = SandboxManager(config)
        assert manager.config is config

    def test_init_with_permissive_config(self):
        """Test SandboxManager initialization with permissive config."""
        config = SandboxConfig.permissive()
        manager = SandboxManager(config)
        assert manager.config.enable_network is True

    def test_execute_python_stub(self):
        """Test execute_python returns stub execution."""
        config = SandboxConfig.default()
        manager = SandboxManager(config)
        execution = manager.execute_python("print('hello')", "exec_1")

        assert execution.execution_id == "exec_1"
        assert execution.status == SandboxStatus.COMPLETED
        assert execution.stdout == ""
        assert execution.stderr == ""
        assert execution.return_code == 0
        assert execution.execution_time_seconds == 0.0

    def test_execute_shell_stub(self):
        """Test execute_shell returns failed execution (not allowed)."""
        config = SandboxConfig.default()
        manager = SandboxManager(config)
        execution = manager.execute_shell("ls -la", "exec_1")

        assert execution.execution_id == "exec_1"
        assert execution.status == SandboxStatus.FAILED
        assert execution.stdout == ""
        assert execution.stderr == "Shell execution not allowed in current configuration"
        assert execution.return_code == 1
        assert execution.execution_time_seconds == 0.0

    def test_execute_python_with_different_ids(self):
        """Test execute_python with different execution IDs."""
        config = SandboxConfig.default()
        manager = SandboxManager(config)

        execution1 = manager.execute_python("code", "exec_1")
        execution2 = manager.execute_python("code", "exec_2")

        assert execution1.execution_id == "exec_1"
        assert execution2.execution_id == "exec_2"

    def test_execute_shell_with_different_ids(self):
        """Test execute_shell with different execution IDs."""
        config = SandboxConfig.default()
        manager = SandboxManager(config)

        execution1 = manager.execute_shell("cmd", "exec_1")
        execution2 = manager.execute_shell("cmd", "exec_2")

        assert execution1.execution_id == "exec_1"
        assert execution2.execution_id == "exec_2"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_config_with_large_memory(self):
        """Test config with very large memory limit."""
        config = SandboxConfig(
            enable_network=False,
            enable_filesystem=False,
            max_memory_mb=1000000,
            max_execution_time_seconds=30,
            enable_gpu=False,
        )
        assert config.max_memory_mb == 1000000

    def test_config_with_large_timeout(self):
        """Test config with very large timeout."""
        config = SandboxConfig(
            enable_network=False,
            enable_filesystem=False,
            max_memory_mb=256,
            max_execution_time_seconds=1000000,
            enable_gpu=False,
        )
        assert config.max_execution_time_seconds == 1000000

    def test_execution_with_empty_outputs(self):
        """Test execution with empty stdout/stderr."""
        execution = SandboxExecution(
            execution_id="exec_1",
            status=SandboxStatus.COMPLETED,
            stdout="",
            stderr="",
            return_code=0,
            execution_time_seconds=0.0,
        )
        assert execution.stdout == ""
        assert execution.stderr == ""

    def test_execution_with_unicode_output(self):
        """Test execution with unicode output."""
        execution = SandboxExecution(
            execution_id="exec_1",
            status=SandboxStatus.COMPLETED,
            stdout="日本語 中文 العربية",
            stderr="русский",
            return_code=0,
            execution_time_seconds=1.0,
        )
        assert "日本語" in execution.stdout
        assert "русский" in execution.stderr

    def test_execution_with_special_characters(self):
        """Test execution with special characters in output."""
        execution = SandboxExecution(
            execution_id="exec_1",
            status=SandboxStatus.COMPLETED,
            stdout="output with <script> and & symbols",
            stderr="error with \n\t\r",
            return_code=0,
            execution_time_seconds=1.0,
        )
        assert "<script>" in execution.stdout
        assert "\n" in execution.stderr

    def test_execute_python_with_empty_code(self):
        """Test execute_python with empty code."""
        config = SandboxConfig.default()
        manager = SandboxManager(config)
        execution = manager.execute_python("", "exec_1")

        assert execution.execution_id == "exec_1"
        assert execution.status == SandboxStatus.COMPLETED

    def test_execute_python_with_very_long_code(self):
        """Test execute_python with very long code."""
        config = SandboxConfig.default()
        manager = SandboxManager(config)
        long_code = "print('x')\n" * 10000
        execution = manager.execute_python(long_code, "exec_1")

        assert execution.execution_id == "exec_1"
        assert execution.status == SandboxStatus.COMPLETED

    def test_execute_shell_with_empty_command(self):
        """Test execute_shell with empty command."""
        config = SandboxConfig.default()
        manager = SandboxManager(config)
        execution = manager.execute_shell("", "exec_1")

        assert execution.execution_id == "exec_1"
        assert execution.status == SandboxStatus.FAILED


class TestIntegrationScenarios:
    """Test integration scenarios."""

    def test_default_config_execution(self):
        """Test execution with default config."""
        config = SandboxConfig.default()
        manager = SandboxManager(config)

        python_exec = manager.execute_python("code", "exec_python")
        shell_exec = manager.execute_shell("cmd", "exec_shell")

        assert python_exec.is_successful() is True
        assert shell_exec.is_successful() is False

    def test_permissive_config_execution(self):
        """Test execution with permissive config."""
        config = SandboxConfig.permissive()
        manager = SandboxManager(config)

        python_exec = manager.execute_python("code", "exec_python")
        shell_exec = manager.execute_shell("cmd", "exec_shell")

        assert python_exec.is_successful() is True
        assert shell_exec.is_successful() is False  # Still stub implementation

    def test_multiple_python_executions(self):
        """Test multiple Python executions."""
        config = SandboxConfig.default()
        manager = SandboxManager(config)

        executions = []
        for i in range(10):
            exec = manager.execute_python(f"code_{i}", f"exec_{i}")
            executions.append(exec)

        assert len(executions) == 10
        assert all(e.is_successful() for e in executions)

    def test_execution_status_transitions(self):
        """Test execution status transitions (simulated)."""
        # Simulate status transitions
        pending = SandboxExecution(
            execution_id="exec_1",
            status=SandboxStatus.PENDING,
            stdout="",
            stderr="",
            return_code=None,
            execution_time_seconds=0.0,
        )

        running = SandboxExecution(
            execution_id="exec_1",
            status=SandboxStatus.RUNNING,
            stdout="",
            stderr="",
            return_code=None,
            execution_time_seconds=0.5,
        )

        completed = SandboxExecution(
            execution_id="exec_1",
            status=SandboxStatus.COMPLETED,
            stdout="output",
            stderr="",
            return_code=0,
            execution_time_seconds=1.0,
        )

        assert pending.status == SandboxStatus.PENDING
        assert running.status == SandboxStatus.RUNNING
        assert completed.is_successful() is True

    def test_custom_config_with_gpu(self):
        """Test custom config with GPU enabled."""
        config = SandboxConfig(
            enable_network=True,
            enable_filesystem=True,
            max_memory_mb=2048,
            max_execution_time_seconds=120,
            enable_gpu=True,
        )
        manager = SandboxManager(config)

        assert manager.config.enable_gpu is True
        assert manager.config.max_memory_mb == 2048

        python_exec = manager.execute_python("code", "exec_1")
        assert python_exec.is_successful() is True
