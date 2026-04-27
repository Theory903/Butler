"""Butler Audit Middleware.

Emits audit events for every agent step for compliance and observability.
"""

import logging

from langchain.middleware.base import (
    ButlerBaseMiddleware,
    ButlerMiddlewareContext,
    MiddlewareResult,
)

import structlog

logger = structlog.get_logger(__name__)


class ButlerAuditMiddleware(ButlerBaseMiddleware):
    """Middleware for audit logging on every agent step.

    Runs on all hooks to log execution lifecycle.
    """

    def __init__(self, enabled: bool = True):
        super().__init__(enabled=enabled)

    async def pre_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Log model inference start."""
        logger.info(
            "agent_model_inference_start",
            tenant_id=context.tenant_id,
            account_id=context.account_id,
            session_id=context.session_id,
            trace_id=context.trace_id,
            model=context.model,
            tier=context.tier,
            message_count=len(context.messages),
        )
        return MiddlewareResult(success=True, should_continue=True)

    async def post_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Log model inference completion."""
        logger.info(
            "agent_model_inference_complete",
            tenant_id=context.tenant_id,
            account_id=context.account_id,
            session_id=context.session_id,
            trace_id=context.trace_id,
            duration_ms=context.duration_ms,
            tool_call_count=len(context.tool_calls),
        )
        return MiddlewareResult(success=True, should_continue=True)

    async def pre_tool(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Log tool execution start."""
        logger.info(
            "agent_tool_execution_start",
            tenant_id=context.tenant_id,
            account_id=context.account_id,
            session_id=context.session_id,
            trace_id=context.trace_id,
            tool_count=len(context.tool_calls),
        )
        return MiddlewareResult(success=True, should_continue=True)

    async def post_tool(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Log tool execution completion."""
        logger.info(
            "agent_tool_execution_complete",
            tenant_id=context.tenant_id,
            account_id=context.account_id,
            session_id=context.session_id,
            trace_id=context.trace_id,
            tool_result_count=len(context.tool_results),
            duration_ms=context.duration_ms,
        )
        return MiddlewareResult(success=True, should_continue=True)
