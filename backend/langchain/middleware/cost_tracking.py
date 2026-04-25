"""Butler Cost Tracking Middleware.

Tracks per-tenant cost ledger for model inference and tool execution.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from langchain.middleware.base import (
    ButlerBaseMiddleware,
    ButlerMiddlewareContext,
    MiddlewareOrder,
    MiddlewareResult,
)

logger = logging.getLogger(__name__)


@dataclass
class CostEntry:
    """Single cost entry."""

    tenant_id: str
    account_id: str
    session_id: str
    category: str  # "model" or "tool"
    model: str | None = None
    tool_name: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class ButlerCostTrackingMiddleware(ButlerBaseMiddleware):
    """Middleware for per-tenant cost tracking.

    Runs on POST_MODEL and POST_TOOL hooks to track costs.
    """

    def __init__(self, enabled: bool = True):
        super().__init__(enabled=enabled)
        self._cost_ledger: list[CostEntry] = []

    async def post_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Track model inference cost."""
        # Extract token counts from context metadata if available
        input_tokens = context.metadata.get("input_tokens", 0)
        output_tokens = context.metadata.get("output_tokens", 0)
        cost_usd = context.metadata.get("cost_usd", 0.0)

        entry = CostEntry(
            tenant_id=context.tenant_id,
            account_id=context.account_id,
            session_id=context.session_id,
            category="model",
            model=context.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            duration_ms=context.duration_ms,
            metadata={"trace_id": context.trace_id},
        )

        self._cost_ledger.append(entry)

        logger.info(
            "cost_tracked_model",
            tenant_id=context.tenant_id,
            account_id=context.account_id,
            model=context.model,
            cost_usd=cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        return MiddlewareResult(success=True, should_continue=True)

    async def post_tool(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Track tool execution cost."""
        # Extract tool costs from context
        for tool_result in context.tool_results:
            tool_name = tool_result.get("name", "unknown")
            cost_usd = tool_result.get("cost_usd", 0.0)

            entry = CostEntry(
                tenant_id=context.tenant_id,
                account_id=context.account_id,
                session_id=context.session_id,
                category="tool",
                tool_name=tool_name,
                cost_usd=cost_usd,
                duration_ms=context.duration_ms,
                metadata={"trace_id": context.trace_id},
            )

            self._cost_ledger.append(entry)

            logger.info(
                "cost_tracked_tool",
                tenant_id=context.tenant_id,
                account_id=context.account_id,
                tool_name=tool_name,
                cost_usd=cost_usd,
            )

        return MiddlewareResult(success=True, should_continue=True)

    def get_cost_ledger(self) -> list[CostEntry]:
        """Get the current cost ledger."""
        return self._cost_ledger.copy()

    def get_tenant_cost(self, tenant_id: str) -> float:
        """Get total cost for a tenant."""
        return sum(
            entry.cost_usd for entry in self._cost_ledger if entry.tenant_id == tenant_id
        )

    def get_account_cost(self, account_id: str) -> float:
        """Get total cost for an account."""
        return sum(
            entry.cost_usd for entry in self._cost_ledger if entry.account_id == account_id
        )

    def clear_ledger(self):
        """Clear the cost ledger."""
        self._cost_ledger.clear()
