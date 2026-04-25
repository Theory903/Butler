"""
Error normalization for Hermes tool executions.

Converts Hermes-specific exceptions into Butler-standard error formats.
"""

from __future__ import annotations

from typing import Any


class HermesToolExecutionError(Exception):
    """Base exception for Hermes tool execution errors."""

    def __init__(self, message: str, tool_name: str, original_error: Exception | None = None):
        self.message = message
        self.tool_name = tool_name
        self.original_error = original_error
        super().__init__(message)


class HermesImportError(HermesToolExecutionError):
    """Raised when Hermes tool module cannot be imported safely."""


class HermesDependencyError(HermesToolExecutionError):
    """Raised when Hermes tool has unresolvable dependencies."""


class HermesExecutionError(HermesToolExecutionError):
    """Raised when Hermes tool execution fails."""


def normalize_hermes_exception(exc: Exception, tool_name: str = "unknown") -> Exception:
    """Normalize a Hermes exception into a Butler-standard format.

    Args:
        exc: The original exception from Hermes
        tool_name: Name of the tool that raised the exception

    Returns:
        A normalized exception in Butler format
    """
    if isinstance(exc, HermesToolExecutionError):
        return exc

    # Import-related errors
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return HermesImportError(
            f"Failed to import Hermes tool '{tool_name}': {exc}",
            tool_name=tool_name,
            original_error=exc,
        )

    # Filesystem-related errors
    if isinstance(exc, (FileNotFoundError, PermissionError, OSError)):
        return HermesExecutionError(
            f"Filesystem error in Hermes tool '{tool_name}': {exc}",
            tool_name=tool_name,
            original_error=exc,
        )

    # Network-related errors
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return HermesExecutionError(
            f"Network error in Hermes tool '{tool_name}': {exc}",
            tool_name=tool_name,
            original_error=exc,
        )

    # Generic execution error
    return HermesExecutionError(
        f"Hermes tool '{tool_name}' execution failed: {exc}",
        tool_name=tool_name,
        original_error=exc,
    )


def normalize_hermes_result(result: Any) -> dict[str, Any]:
    """Normalize a Hermes tool result into a stable Butler format.

    Hermes tools return JSON strings or dicts. This function normalizes
    them into a consistent dict format.

    Args:
        result: The raw result from Hermes tool execution

    Returns:
        A normalized dict with consistent structure
    """
    if isinstance(result, str):
        import json

        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"output": result}
    elif isinstance(result, dict):
        return result
    else:
        return {"output": str(result)}
