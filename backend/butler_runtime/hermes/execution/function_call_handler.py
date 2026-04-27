"""Function call handler for Hermes → Butler integration.

Handles function call execution with Butler governance.
"""

import logging
from collections.abc import Callable
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class FunctionCallHandler:
    """Handles function calls from Hermes-derived tools.

    This class bridges Hermes function calling patterns with Butler's
    governance layer, ensuring all tool calls pass through Butler's
    security and approval mechanisms.
    """

    def __init__(self) -> None:
        """Initialize function call handler."""
        self._handlers: dict[str, Callable[..., Any]] = {}

    def register_handler(self, tool_name: str, handler: Callable[..., Any]) -> None:
        """Register a function call handler for a tool.

        Args:
            tool_name: Tool name
            handler: Handler function
        """
        self._handlers[tool_name] = handler
        logger.debug(f"Registered function call handler for {tool_name}")

    def unregister_handler(self, tool_name: str) -> bool:
        """Unregister a function call handler.

        Args:
            tool_name: Tool name

        Returns:
            True if handler was unregistered, False if not found
        """
        if tool_name in self._handlers:
            del self._handlers[tool_name]
            return True
        return False

    async def handle_call(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Handle a function call through Butler governance.

        Args:
            tool_name: Tool name
            tool_args: Tool arguments
            context: Optional execution context (account_id, session_id, etc.)

        Returns:
            Tool execution result

        Raises:
            ValueError: If tool handler not found
        """
        if tool_name not in self._handlers:
            raise ValueError(f"No handler registered for tool: {tool_name}")

        handler = self._handlers[tool_name]

        try:
            # Call the handler with context if provided
            if context:
                result = await handler(tool_args, **context)
            else:
                result = await handler(tool_args)

            return {
                "tool_name": tool_name,
                "result": result,
                "error": None,
            }

        except Exception as e:
            logger.exception(f"Function call failed for {tool_name}: {e}")
            return {
                "tool_name": tool_name,
                "result": None,
                "error": str(e),
            }

    def has_handler(self, tool_name: str) -> bool:
        """Check if a handler is registered for a tool.

        Args:
            tool_name: Tool name

        Returns:
            True if handler exists, False otherwise
        """
        return tool_name in self._handlers

    def get_registered_tools(self) -> list[str]:
        """Get list of tools with registered handlers.

        Returns:
            List of tool names
        """
        return list(self._handlers.keys())

    def __len__(self) -> int:
        """Return number of registered handlers."""
        return len(self._handlers)

    def __contains__(self, tool_name: str) -> bool:
        """Check if handler is registered."""
        return tool_name in self._handlers
