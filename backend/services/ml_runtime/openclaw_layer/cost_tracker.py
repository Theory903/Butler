"""Cost tracking per provider, key, and request."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from collections import defaultdict

# Approximate pricing per 1M tokens (in USD)
# These are placeholder values - should be updated with actual pricing
PRICING = {
    "openai": {
        "gpt-5.4": {"input": 15.0, "output": 60.0},
        "gpt-5.2": {"input": 10.0, "output": 40.0},
        "gpt-5": {"input": 5.0, "output": 15.0},
        "gpt-4": {"input": 2.5, "output": 10.0},
    },
    "anthropic": {
        "claude-opus-4-7": {"input": 15.0, "output": 75.0},
        "claude-opus-4-6": {"input": 15.0, "output": 75.0},
        "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
        "claude-sonnet-4-0": {"input": 3.0, "output": 15.0},
    },
    "groq": {
        "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
        "mixtral-8x7b": {"input": 0.27, "output": 0.27},
    },
    "vertex-ai": {
        "gemini-2.5-flash": {"input": 0.075, "output": 0.3},
    },
}


@dataclass
class RequestCost:
    """Cost breakdown for a single request."""
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    timestamp: float = field(default_factory=time.time)
    credential_id: str | None = None
    
    @classmethod
    def from_tokens(
        cls,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        credential_id: str | None = None,
    ) -> "RequestCost":
        """Calculate cost from token counts."""
        provider_pricing = PRICING.get(provider.lower(), {})
        model_pricing = provider_pricing.get(model, {"input": 0.0, "output": 0.0})
        
        input_cost = (input_tokens / 1_000_000) * model_pricing["input"]
        output_cost = (output_tokens / 1_000_000) * model_pricing["output"]
        total_cost = input_cost + output_cost
        
        return cls(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            total_cost_usd=total_cost,
            credential_id=credential_id,
        )


@dataclass
class CostSummary:
    """Aggregated cost summary."""
    provider: str
    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    avg_cost_per_request: float = 0.0
    avg_tokens_per_request: int = 0
    
    def update(self, cost: RequestCost) -> None:
        """Update summary with a request cost."""
        self.total_requests += 1
        self.total_input_tokens += cost.input_tokens
        self.total_output_tokens += cost.output_tokens
        self.total_cost_usd += cost.total_cost_usd
        
        if self.total_requests > 0:
            self.avg_cost_per_request = self.total_cost_usd / self.total_requests
            self.avg_tokens_per_request = (
                self.total_input_tokens + self.total_output_tokens
            ) // self.total_requests


@dataclass
class CredentialCostSummary:
    """Cost summary per credential."""
    credential_id: str
    provider: str
    total_requests: int = 0
    total_cost_usd: float = 0.0
    avg_cost_per_request: float = 0.0
    
    def update(self, cost: RequestCost) -> None:
        """Update summary with a request cost."""
        self.total_requests += 1
        self.total_cost_usd += cost.total_cost_usd
        
        if self.total_requests > 0:
            self.avg_cost_per_request = self.total_cost_usd / self.total_requests


class CostTracker:
    """Cost tracker for provider operations."""
    
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._provider_costs: dict[str, CostSummary] = defaultdict(
            lambda: CostSummary(provider="")
        )
        self._credential_costs: dict[str, CredentialCostSummary] = defaultdict(
            lambda: CredentialCostSummary(credential_id="", provider="")
        )
        self._request_costs: list[RequestCost] = []
    
    def track_request(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        credential_id: str | None = None,
    ) -> RequestCost:
        """Track cost for a request."""
        cost = RequestCost.from_tokens(
            provider, model, input_tokens, output_tokens, credential_id
        )
        
        if not self.enabled:
            return cost
        
        self._request_costs.append(cost)
        
        # Update provider summary
        provider_summary = self._provider_costs[provider]
        provider_summary.provider = provider
        provider_summary.update(cost)
        
        # Update credential summary
        if credential_id:
            credential_summary = self._credential_costs[credential_id]
            credential_summary.credential_id = credential_id
            credential_summary.provider = provider
            credential_summary.update(cost)
        
        return cost
    
    def get_provider_cost(self, provider: str) -> CostSummary:
        """Get cost summary for a provider."""
        return self._provider_costs.get(provider, CostSummary(provider=provider))
    
    def get_credential_cost(self, credential_id: str) -> CredentialCostSummary:
        """Get cost summary for a credential."""
        return self._credential_costs.get(
            credential_id,
            CredentialCostSummary(credential_id=credential_id, provider=""),
        )
    
    def get_total_cost(self) -> float:
        """Get total cost across all providers."""
        return sum(summary.total_cost_usd for summary in self._provider_costs.values())
    
    def get_all_provider_costs(self) -> dict[str, CostSummary]:
        """Get cost summaries for all providers."""
        return dict(self._provider_costs)
    
    def get_all_credential_costs(self) -> dict[str, CredentialCostSummary]:
        """Get cost summaries for all credentials."""
        return dict(self._credential_costs)
    
    def get_recent_costs(self, limit: int = 100) -> list[RequestCost]:
        """Get recent request costs."""
        return self._request_costs[-limit:]
    
    def clear_costs(self) -> None:
        """Clear all cost tracking."""
        self._provider_costs.clear()
        self._credential_costs.clear()
        self._request_costs.clear()
    
    def check_budget(self, budget_usd: float) -> bool:
        """Check if total cost is within budget."""
        return self.get_total_cost() <= budget_usd


# Global cost tracker instance
_default_cost_tracker = CostTracker()


def get_default_cost_tracker() -> CostTracker:
    """Get the default cost tracker instance."""
    return _default_cost_tracker
