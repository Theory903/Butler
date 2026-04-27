"""Tool calling handler for Butler Unified Agent Runtime.

Adapted from Hermes tool calling patterns with Butler governance integration.
"""

import logging
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ToolCallingHandler:
    """Handles tool call formatting and result conversion.

    This class bridges between model tool call outputs and Butler's tool executor,
    ensuring proper format conversion and governance compliance.
    """

    def __init__(self) -> None:
        """Initialize tool calling handler."""

    def to_tool_message(
        self,
        tool_name: str,
        tool_call_id: str,
        result: Any,
        is_error: bool = False,
    ) -> dict[str, Any]:
        """Convert a tool result into a tool message format.

        Args:
            tool_name: Name of the tool that was called
            tool_call_id: ID of the tool call from the model
            result: Result from tool execution
            is_error: Whether the result is an error

        Returns:
            Dictionary in tool message format
        """
        content = str(result) if result else ""

        if is_error:
            content = f"Error: {content}"

        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "content": content,
        }

    def extract_tool_calls(self, model_response: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract tool calls from model response.

        Args:
            model_response: Raw response from model

        Returns:
            List of tool call dictionaries
        """
        tool_calls = []

        # Handle OpenAI-style tool_calls
        if "tool_calls" in model_response:
            for tc in model_response["tool_calls"]:
                tool_calls.append(
                    {
                        "id": tc.get("id", ""),
                        "type": tc.get("type", "function"),
                        "function": {
                            "name": tc.get("function", {}).get("name", ""),
                            "arguments": tc.get("function", {}).get("arguments", "{}"),
                        },
                    }
                )

        # Handle Anthropic-style tool_use blocks
        elif "content" in model_response:
            for block in model_response["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_calls.append(
                        {
                            "id": block.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": block.get("input", {}),
                            },
                        }
                    )

        return tool_calls

    def normalize_tool_args(self, args: Any, tool_name: str) -> dict[str, Any]:
        """Normalize tool arguments to a consistent format.

        Args:
            args: Raw arguments from model (string, dict, etc.)
            tool_name: Name of the tool (for error messages)

        Returns:
            Normalized arguments dictionary
        """
        if isinstance(args, dict):
            return args

        if isinstance(args, str):
            try:
                import json

                return json.loads(args)
            except json.JSONDecodeError:
                logger.warning(
                    f"Failed to parse tool args as JSON for {tool_name}: {args[:100]}..."
                )
                return {}

        logger.warning(f"Unexpected tool args type for {tool_name}: {type(args)}")
        return {}

    def format_tool_result(
        self,
        tool_name: str,
        result: Any,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Format tool result for model consumption.

        Args:
            tool_name: Name of the tool
            result: Raw result from tool execution
            metadata: Optional metadata (tokens, cost, etc.)

        Returns:
            Formatted result string
        """
        if isinstance(result, str):
            return result

        if isinstance(result, dict):
            if "error" in result:
                return f"Error: {result['error']}"
            if "content" in result:
                return str(result["content"])
            return str(result)

        if isinstance(result, (list, tuple)):
            return "\n".join(str(item) for item in result)

        return str(result)

    def should_stop_on_tool_error(self, tool_name: str, error: str) -> bool:
        """Determine if agent should stop on tool error.

        Args:
            tool_name: Name of the tool that failed
            error: Error message

        Returns:
            True if agent should stop, False if it should continue
        """
        # Critical errors that should stop the agent
        critical_errors = [
            "permission denied",
            "authentication failed",
            "rate limit exceeded",
            "quota exceeded",
            "invalid api key",
        ]

        error_lower = error.lower()
        return any(critical in error_lower for critical in critical_errors)
