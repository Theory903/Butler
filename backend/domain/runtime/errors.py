"""Runtime spine errors."""

from __future__ import annotations


class ResponseLeakError(Exception):
    """Raised when internal implementation details leak into user-facing responses."""

    pass


class ResponseValidationError(Exception):
    """Raised when response validation fails due to unsafe patterns."""

    pass


class ToolResultError(Exception):
    """Raised when tool result envelope is invalid or missing required fields."""

    pass
