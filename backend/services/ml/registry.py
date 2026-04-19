"""Model Registry — Phase 5.

Extended with T2 (local vLLM) and T3 (cloud frontier) model entries.
Aligned with ButlerSmartRouter tier definitions.

Tier mapping:
  T0  → intent-classifier-pattern   (zero-cost, no model)
  T1  → intent-classifier-keyword   (heuristic, no model)
  T2  → local-reasoning-qwen3       (vLLM + TriAttention)
  T3  → cloud-frontier-{provider}   (Anthropic / OpenAI / Gemini)
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Type

import structlog

from domain.ml.contracts import ReasoningContract
from domain.ml.contracts import IModelRegistry

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ModelEntry:
    name: str
    tier: int            # 0-3
    type: str            # pattern | keyword | vllm | external_api
    version: str
    status: str          # active | shadow | deprecated
    provider: str        # vllm | anthropic | openai | google | internal
    dimensions: int = 0  # for embedding models
    max_context: int = 0
    tri_attention: bool = False
    cost_per_1k_tokens: float = 0.0  # USD; 0 for local
    rollout_percentage: int = 100    # 0-100; for canary rollout


class ModelRegistry(IModelRegistry):
    """Track available models, versions, and configurations.

    Phase 5: Extended to support T2/T3 routing via ButlerSmartRouter.
    """

    MODELS: dict[str, ModelEntry] = {
        # ── T0: Pattern match ───────────────────────────────────────────────
        "intent-classifier-pattern": ModelEntry(
            name="intent-classifier-pattern",
            tier=0, type="pattern", version="1.0.0",
            status="active", provider="internal",
        ),

        # ── T1: Keyword classifier ──────────────────────────────────────────
        "intent-classifier-keyword": ModelEntry(
            name="intent-classifier-keyword",
            tier=1, type="keyword", version="1.0.0",
            status="active", provider="internal",
        ),

        # ── Embeddings ──────────────────────────────────────────────────────
        "embeddings-minilm": ModelEntry(
            name="embeddings-minilm",
            tier=1, type="sentence-transformer", version="1.0.0",
            status="active", provider="internal",
            dimensions=384, max_context=512,
        ),

        # ── T2: Local LLM (vLLM + TriAttention) ────────────────────────────
        "local-reasoning-qwen3": ModelEntry(
            name="local-reasoning-qwen3",
            tier=2, type="vllm", version="qwen3-7b-instruct",
            status="active", provider="vllm",
            max_context=32768, tri_attention=True,
            cost_per_1k_tokens=0.0,
        ),
        "local-general-qwen3-mini": ModelEntry(
            name="local-general-qwen3-mini",
            tier=2, type="vllm", version="qwen3-1.7b-instruct",
            status="shadow", provider="vllm",
            max_context=16384, tri_attention=True,
            cost_per_1k_tokens=0.0,
        ),

        # ── T3: Cloud frontier ──────────────────────────────────────────────
        "cloud-frontier-anthropic": ModelEntry(
            name="cloud-frontier-anthropic",
            tier=3, type="external_api", version="claude-opus-4-5",
            status="active", provider="anthropic",
            max_context=200_000,
            cost_per_1k_tokens=0.015,
        ),
        "cloud-frontier-openai": ModelEntry(
            name="cloud-frontier-openai",
            tier=3, type="external_api", version="gpt-4.1",
            status="active", provider="openai",
            max_context=128_000,
            cost_per_1k_tokens=0.010,
        ),
        "cloud-frontier-gemini": ModelEntry(
            name="cloud-frontier-gemini",
            tier=3, type="external_api", version="gemini-2.5-pro",
            status="active", provider="google",
            max_context=1_000_000,
            cost_per_1k_tokens=0.0035,
        ),
    }

    def get_active_model(self, name: str) -> ModelEntry | None:
        import random
        entry = self.MODELS.get(name)
        if not entry or entry.status == "deprecated":
            return None
            
        # Canary rollout logic
        if entry.rollout_percentage < 100:
            if random.randint(1, 100) > entry.rollout_percentage:
                logger.info("model_rollout_excluded", name=name, percentage=entry.rollout_percentage)
                return None
                
        return entry

    def get_active_by_tier(self, tier: int) -> list[ModelEntry]:
        """Return all active (non-deprecated) models at a given tier."""
        return [
            m for m in self.MODELS.values()
            if m.tier == tier and m.status == "active"
        ]

    def list_models(self) -> list[dict]:
        return [
            {
                "name": m.name,
                "tier": m.tier,
                "type": m.type,
                "version": m.version,
                "status": m.status,
                "provider": m.provider,
                "max_context": m.max_context,
                "tri_attention": m.tri_attention,
                "cost_per_1k_tokens": m.cost_per_1k_tokens,
            }
            for m in self.MODELS.values()
        ]

    def preferred_t3_provider(self) -> str:
        """Return the preferred T3 provider name (lowest cost active model)."""
        t3_active = self.get_active_by_tier(3)
        if not t3_active:
            return "anthropic"
        cheapest = min(t3_active, key=lambda m: m.cost_per_1k_tokens)
        return cheapest.provider

    def get_provider(self, tier: int, provider_name: Optional[str] = None) -> ReasoningContract:
        """IModelRegistry interface implementation.
        Delegates to ModelProviderFactory. 
        """
        if provider_name:
            return ModelProviderFactory.get_provider(provider_name)
        
        # Determine default provider for tier
        if tier == 3:
            return ModelProviderFactory.get_provider(self.preferred_t3_provider())
        elif tier == 2:
            return ModelProviderFactory.get_provider("vllm")
        else:
            raise ValueError(f"No configured provider for tier {tier}")

    def list_entries(self) -> list[Dict[str, Any]]:
        """IModelRegistry interface implementation."""
        return self.list_models()

class ModelProviderFactory:
    """Manages the lifecycle and instantiation of Reasoning Providers."""
    
    _instances: Dict[str, ReasoningContract] = {}

    @classmethod
    def get_provider(cls, provider_type: str) -> ReasoningContract:
        """Return a singleton instance of the requested provider."""
        if provider_type in cls._instances:
            return cls._instances[provider_type]

        provider: ReasoningContract
        if provider_type == "openai":
            from services.ml.providers import OpenAIProvider
            provider = OpenAIProvider()
        elif provider_type == "anthropic":
            from services.ml.providers import AnthropicProvider
            provider = AnthropicProvider()
        elif provider_type == "vllm":
            from services.ml.providers import VLLMProvider
            provider = VLLMProvider()
        elif provider_type == "google":
            from services.ml.providers import OpenAIProvider
            provider = OpenAIProvider(base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
        else:
            raise ValueError(f"Unsupported model provider: {provider_type}")
        
        cls._instances[provider_type] = provider
        return provider
