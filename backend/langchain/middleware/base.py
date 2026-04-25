"""Base middleware interface for Butler LangChain agents."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MiddlewareOrder(str, Enum):
    """Middleware execution order hooks."""

    PRE_MODEL = "pre_model"
    POST_MODEL = "post_model"
    PRE_TOOL = "pre_tool"
    POST_TOOL = "post_tool"


@dataclass
class ButlerMiddlewareContext:
    """Context passed to middleware during execution."""

    tenant_id: str
    account_id: str
    session_id: str
    trace_id: str
    user_id: str | None = None
    model: str | None = None
    tier: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class MiddlewareResult:
    """Result from middleware execution."""

    success: bool
    should_continue: bool = True  # If False, short-circuit execution
    modified_input: Any = None
    modified_output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ButlerBaseMiddleware(ABC):
    """Abstract base class for Butler middleware.

    All Butler middleware must inherit from this class and implement
    the appropriate hook methods based on their execution point.
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    async def pre_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Hook called before model inference. Override if needed."""
        return MiddlewareResult(success=True, should_continue=True)

    async def post_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Hook called after model inference. Override if needed."""
        return MiddlewareResult(success=True, should_continue=True)

    async def pre_tool(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Hook called before tool execution. Override if needed."""
        return MiddlewareResult(success=True, should_continue=True)

    async def post_tool(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Hook called after tool execution. Override if needed."""
        return MiddlewareResult(success=True, should_continue=True)

    async def process(
        self, context: ButlerMiddlewareContext, hook: MiddlewareOrder
    ) -> MiddlewareResult:
        """Route to appropriate hook based on middleware order."""
        if not self.enabled:
            return MiddlewareResult(success=True, should_continue=True)

        try:
            if hook == MiddlewareOrder.PRE_MODEL:
                return await self.pre_model(context)
            elif hook == MiddlewareOrder.POST_MODEL:
                return await self.post_model(context)
            elif hook == MiddlewareOrder.PRE_TOOL:
                return await self.pre_tool(context)
            elif hook == MiddlewareOrder.POST_TOOL:
                return await self.post_tool(context)
            else:
                logger.warning("unknown_middleware_hook", hook=hook)
                return MiddlewareResult(success=True, should_continue=True)
        except Exception as exc:
            logger.exception("middleware_execution_failed", hook=hook, exc=str(exc))
            return MiddlewareResult(
                success=False,
                should_continue=True,  # Fail open by default
                error=str(exc),
            )
