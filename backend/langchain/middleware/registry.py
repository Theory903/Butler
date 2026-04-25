"""Butler Middleware Registry.

Manages middleware registration, ordering, and execution hooks.
"""

import logging
from collections import OrderedDict
from enum import Enum
from typing import Any, Callable

from langchain.middleware.base import (
    ButlerBaseMiddleware,
    ButlerMiddlewareContext,
    MiddlewareOrder,
    MiddlewareResult,
)

logger = logging.getLogger(__name__)


class MiddlewareHook(str, Enum):
    """Hook points for middleware execution."""

    PRE_MODEL = "pre_model"
    POST_MODEL = "post_model"
    PRE_TOOL = "pre_tool"
    POST_TOOL = "post_tool"


class ButlerMiddlewareRegistry:
    """Registry for managing Butler middleware.

    Middleware can be registered with specific hooks and order.
    """

    def __init__(self):
        self._middleware: dict[MiddlewareOrder, list[tuple[int, ButlerBaseMiddleware]]] = {
            MiddlewareOrder.PRE_MODEL: [],
            MiddlewareOrder.POST_MODEL: [],
            MiddlewareOrder.PRE_TOOL: [],
            MiddlewareOrder.POST_TOOL: [],
        }
        self._next_order = 0

    def register(
        self,
        middleware: ButlerBaseMiddleware,
        hook: MiddlewareOrder | MiddlewareHook,
        order: int | None = None,
    ) -> "ButlerMiddlewareRegistry":
        """Register middleware for a specific hook.

        Args:
            middleware: The middleware instance to register
            hook: The hook point to attach to
            order: Optional order for execution (lower = earlier)

        Returns:
            Self for chaining
        """
        if order is None:
            order = self._next_order
            self._next_order += 1

        # Normalize hook type
        if isinstance(hook, MiddlewareHook):
            hook = MiddlewareOrder(hook.value)

        if hook not in self._middleware:
            logger.warning("unknown_hook", hook=hook)
            return self

        self._middleware[hook].append((order, middleware))
        # Sort by order
        self._middleware[hook].sort(key=lambda x: x[0])

        logger.info(
            "middleware_registered",
            middleware=middleware.__class__.__name__,
            hook=hook,
            order=order,
        )

        return self

    def register_pre_model(
        self, middleware: ButlerBaseMiddleware, order: int | None = None
    ) -> "ButlerMiddlewareRegistry":
        """Register middleware for PRE_MODEL hook."""
        return self.register(middleware, MiddlewareOrder.PRE_MODEL, order)

    def register_post_model(
        self, middleware: ButlerBaseMiddleware, order: int | None = None
    ) -> "ButlerMiddlewareRegistry":
        """Register middleware for POST_MODEL hook."""
        return self.register(middleware, MiddlewareOrder.POST_MODEL, order)

    def register_pre_tool(
        self, middleware: ButlerBaseMiddleware, order: int | None = None
    ) -> "ButlerMiddlewareRegistry":
        """Register middleware for PRE_TOOL hook."""
        return self.register(middleware, MiddlewareOrder.PRE_TOOL, order)

    def register_post_tool(
        self, middleware: ButlerBaseMiddleware, order: int | None = None
    ) -> "ButlerMiddlewareRegistry":
        """Register middleware for POST_TOOL hook."""
        return self.register(middleware, MiddlewareOrder.POST_TOOL, order)

    async def execute(
        self, context: ButlerMiddlewareContext, hook: MiddlewareOrder | MiddlewareHook
    ) -> MiddlewareResult:
        """Execute all middleware for a hook.

        Args:
            context: Butler execution context
            hook: The hook to execute

        Returns:
            Combined middleware result
        """
        # Normalize hook type
        if isinstance(hook, MiddlewareHook):
            hook = MiddlewareOrder(hook.value)

        if hook not in self._middleware:
            return MiddlewareResult(success=True, should_continue=True)

        combined_metadata = {}

        for order, middleware in self._middleware[hook]:
            result = await middleware.process(context, hook)

            # Short-circuit if middleware requests it
            if not result.should_continue:
                logger.warning(
                    "middleware_short_circuit",
                    middleware=middleware.__class__.__name__,
                    hook=hook,
                    reason=result.error,
                )
                return result

            # Apply modifications
            if result.modified_input:
                if "messages" in result.modified_input:
                    context.messages = result.modified_input["messages"]
                context.metadata.update(result.modified_input.get("metadata", {}))

            if result.modified_output:
                if "messages" in result.modified_output:
                    context.messages = result.modified_output["messages"]
                context.metadata.update(result.modified_output.get("metadata", {}))

            # Combine metadata
            combined_metadata.update(result.metadata)

        return MiddlewareResult(
            success=True,
            should_continue=True,
            metadata=combined_metadata,
        )

    def get_middleware_for_hook(
        self, hook: MiddlewareOrder | MiddlewareHook
    ) -> list[ButlerBaseMiddleware]:
        """Get all middleware registered for a hook."""
        if isinstance(hook, MiddlewareHook):
            hook = MiddlewareOrder(hook.value)

        return [mw for _, mw in self._middleware.get(hook, [])]

    def clear(self):
        """Clear all middleware."""
        self._middleware = {
            MiddlewareOrder.PRE_MODEL: [],
            MiddlewareOrder.POST_MODEL: [],
            MiddlewareOrder.PRE_TOOL: [],
            MiddlewareOrder.POST_TOOL: [],
        }
        self._next_order = 0
        logger.info("middleware_registry_cleared")
