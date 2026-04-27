"""Cost tracking middleware for LangChain agents.

Tracks token usage and costs per provider/model.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.middleware.base import (
    ButlerBaseMiddleware,
    ButlerMiddlewareContext,
    MiddlewareResult,
)

import structlog

logger = structlog.get_logger(__name__)


# Cost per 1K tokens (example rates - should be configurable)
MODEL_COSTS = {
    "anthropic": {
        "claude-sonnet-4": {"input": 3.0, "output": 15.0},
        "claude-haiku-4": {"input": 0.25, "output": 1.25},
    },
    "openai": {
        "gpt-4": {"input": 30.0, "output": 60.0},
        "gpt-4-turbo": {"input": 10.0, "output": 30.0},
        "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
    },
}


class CostTrackingMiddleware(ButlerBaseMiddleware):
    """Middleware for tracking token usage and costs.

    This middleware:
    - Tracks prompt_tokens and completion_tokens from ML responses
    - Calculates costs per provider/model
    - Stores cost data in middleware context metadata
    - Runs at POST_MODEL hook

    Production integration (Phase B.1):
    - Real cost tracking from MLRuntimeManager responses
    - Configurable cost rates per provider/model
    - Aggregates costs across multi-turn conversations
    """

    def __init__(self, enabled: bool = True, custom_costs: dict[str, Any] | None = None):
        """Initialize cost tracking middleware.

        Args:
            enabled: Whether middleware is enabled
            custom_costs: Optional custom cost rates per provider/model
        """
        super().__init__(enabled=enabled)
        self._costs = custom_costs or MODEL_COSTS

    async def post_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Track costs after model inference.

        Args:
            context: ButlerMiddlewareContext with model response

        Returns:
            MiddlewareResult with cost metadata
        """
        if not self.enabled:
            return MiddlewareResult(success=True, should_continue=True)

        # Extract usage data from context
        # This should be populated by the MLRuntimeManager response
        usage = context.metadata.get("usage", {})
        provider = context.metadata.get("provider", "anthropic")
        model = context.model or "claude-sonnet-4"

        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = prompt_tokens + completion_tokens

        # Calculate costs
        cost_data = self._calculate_costs(
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        # Store in metadata
        cost_metadata = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "provider": provider,
            "model": model,
            "input_cost_usd": cost_data["input_cost"],
            "output_cost_usd": cost_data["output_cost"],
            "total_cost_usd": cost_data["total_cost"],
        }

        context.metadata.update(cost_metadata)

        logger.info(
            "cost_tracked",
            provider=provider,
            model=model,
            total_tokens=total_tokens,
            total_cost_usd=cost_data["total_cost"],
        )

        return MiddlewareResult(
            success=True,
            should_continue=True,
            metadata=cost_metadata,
        )

    def _calculate_costs(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> dict[str, float]:
        """Calculate costs based on token usage.

        Args:
            provider: Provider name (e.g., "anthropic", "openai")
            model: Model name
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens

        Returns:
            Dictionary with input_cost, output_cost, total_cost in USD
        """
        # Get cost rates for provider/model
        provider_costs = self._costs.get(provider, {})
        model_costs = provider_costs.get(model, {"input": 0.0, "output": 0.0})

        input_rate = model_costs.get("input", 0.0)
        output_rate = model_costs.get("output", 0.0)

        # Calculate costs (per 1K tokens)
        input_cost = (prompt_tokens / 1000.0) * input_rate
        output_cost = (completion_tokens / 1000.0) * output_rate
        total_cost = input_cost + output_cost

        return {
            "input_cost": round(input_cost, 6),
            "output_cost": round(output_cost, 6),
            "total_cost": round(total_cost, 6),
        }
