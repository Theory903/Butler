"""ToolResultEnvelope - canonical envelope for tool execution results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ToolStatus = Literal["success", "partial", "failed"]


class ToolResultError(Exception):
    """Raised when tool result envelope is invalid or missing required fields."""

    pass


@dataclass(frozen=True, slots=True)
class ToolResultEnvelope:
    """Canonical envelope for tool execution results.

    Rule: Raw tool output must never be returned directly to the user.
    All tool outputs must be wrapped in ToolResultEnvelope before being
    passed to the response composer.

    Example bad response (what we prevent):
    {
      "response": "Let me check the current date for you.\\n\\n{'current_time': '2026-04-25T10:02:32.978425+00:00', ...}"
    }

    Example good response (what we produce):
    Today is April 25, 2026.
    """

    tool_name: str
    status: ToolStatus
    summary: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    user_visible: bool = False
    safe_to_quote: bool = False
    error_code: str | None = None
    error_message: str | None = None
    latency_ms: int | None = None

    def is_success(self) -> bool:
        """Check if tool execution succeeded."""
        return self.status == "success"

    def is_partial(self) -> bool:
        """Check if tool execution partially succeeded."""
        return self.status == "partial"

    def is_failed(self) -> bool:
        """Check if tool execution failed."""
        return self.status == "failed"

    def require_success(self) -> None:
        """Ensure tool execution succeeded.

        Raises:
            ToolResultError: If tool execution did not succeed.
        """
        if not self.is_success():
            raise ToolResultError(
                f"Tool {self.tool_name} failed with status {self.status}: {self.error_message}"
            )

    def get_user_visible_summary(self) -> str:
        """Get user-visible summary of tool result.

        Returns:
            User-friendly summary string, or empty string if not user-visible.
        """
        if not self.user_visible:
            return ""
        return self.summary or f"{self.tool_name} completed."

    @classmethod
    def success(
        cls,
        tool_name: str,
        summary: str | None = None,
        data: dict[str, Any] | None = None,
        artifacts: list[dict[str, Any]] | None = None,
        user_visible: bool = False,
        safe_to_quote: bool = False,
        latency_ms: int | None = None,
    ) -> ToolResultEnvelope:
        """Create a successful tool result envelope.

        Args:
            tool_name: Name of the tool that was executed
            summary: Optional user-visible summary
            data: Optional structured data from tool output
            artifacts: Optional list of artifacts (files, images, etc.)
            user_visible: Whether this result should be shown to the user
            safe_to_quote: Whether the output is safe to quote directly
            latency_ms: Tool execution latency in milliseconds

        Returns:
            ToolResultEnvelope with status "success"
        """
        return cls(
            tool_name=tool_name,
            status="success",
            summary=summary,
            data=data or {},
            artifacts=artifacts or [],
            user_visible=user_visible,
            safe_to_quote=safe_to_quote,
            latency_ms=latency_ms,
        )

    @classmethod
    def partial(
        cls,
        tool_name: str,
        summary: str | None = None,
        data: dict[str, Any] | None = None,
        artifacts: list[dict[str, Any]] | None = None,
        user_visible: bool = False,
        safe_to_quote: bool = False,
        latency_ms: int | None = None,
    ) -> ToolResultEnvelope:
        """Create a partially successful tool result envelope.

        Args:
            tool_name: Name of the tool that was executed
            summary: Optional user-visible summary
            data: Optional structured data from tool output
            artifacts: Optional list of artifacts (files, images, etc.)
            user_visible: Whether this result should be shown to the user
            safe_to_quote: Whether the output is safe to quote directly
            latency_ms: Tool execution latency in milliseconds

        Returns:
            ToolResultEnvelope with status "partial"
        """
        return cls(
            tool_name=tool_name,
            status="partial",
            summary=summary,
            data=data or {},
            artifacts=artifacts or [],
            user_visible=user_visible,
            safe_to_quote=safe_to_quote,
            latency_ms=latency_ms,
        )

    @classmethod
    def failure(
        cls,
        tool_name: str,
        error_code: str | None = None,
        error_message: str | None = None,
        data: dict[str, Any] | None = None,
        latency_ms: int | None = None,
    ) -> ToolResultEnvelope:
        """Create a failed tool result envelope.

        Args:
            tool_name: Name of the tool that was executed
            error_code: Optional error code for categorization
            error_message: Optional error message
            data: Optional structured data from tool output
            latency_ms: Tool execution latency in milliseconds

        Returns:
            ToolResultEnvelope with status "failed"
        """
        return cls(
            tool_name=tool_name,
            status="failed",
            error_code=error_code,
            error_message=error_message,
            data=data or {},
            latency_ms=latency_ms,
        )
