from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field, replace
from enum import StrEnum
from functools import lru_cache
from threading import RLock
from typing import Any

import structlog

from domain.ml.contracts import IModelRegistry, ReasoningContract, ReasoningTier

# Import settings for environment-based configuration
from infrastructure.config import settings

logger = structlog.get_logger(__name__)


class ProviderKind(StrEnum):
    """High-level provider category."""

    LLM = "llm"
    GATEWAY = "gateway"
    CLOUD = "cloud"
    STT = "stt"
    TTS = "tts"
    EMBEDDING = "embedding"
    SEARCH = "search"
    INTERNAL = "internal"


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    """Stable provider adapter metadata."""

    name: str
    tier: ReasoningTier
    kind: ProviderKind
    module: str
    class_name: str
    default_model: str
    max_context: int = 0
    cost_per_1k_tokens: float = 0.0
    dimensions: int = 0
    tri_attention: bool = False
    api_key_env: str | None = None


@dataclass(frozen=True, slots=True)
class ModelEntry:
    """Resolved runtime model profile."""

    name: str
    tier: ReasoningTier
    kind: ProviderKind
    version: str
    status: str
    provider: str
    max_context: int = 0
    cost_per_1k_tokens: float = 0.0
    dimensions: int = 0
    rollout_percentage: int = 100
    tri_attention: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


PROVIDER_SPECS: dict[str, ProviderSpec] = {
    "openai": ProviderSpec(
        name="openai",
        tier=ReasoningTier.T3,
        kind=ProviderKind.LLM,
        module="services.ml.providers",
        class_name="OpenAIProvider",
        default_model="gpt-4o",
        max_context=128000,
        cost_per_1k_tokens=0.010,
        api_key_env="OPENAI_API_KEY",
    ),
    "anthropic": ProviderSpec(
        name="anthropic",
        tier=ReasoningTier.T3,
        kind=ProviderKind.LLM,
        module="services.ml.providers",
        class_name="AnthropicProvider",
        default_model="claude-sonnet-4.6",
        max_context=200000,
        cost_per_1k_tokens=0.003,
        api_key_env="ANTHROPIC_API_KEY",
    ),
    "groq": ProviderSpec(
        name="groq",
        tier=ReasoningTier.T3,
        kind=ProviderKind.LLM,
        module="services.ml.providers.llm",
        class_name="GroqProvider",
        default_model=settings.DEFAULT_MODEL,
        max_context=131072,
        cost_per_1k_tokens=0.0006,
        api_key_env="GROQ_API_KEY",
    ),
    "google": ProviderSpec(
        name="google",
        tier=ReasoningTier.T3,
        kind=ProviderKind.LLM,
        module="services.ml.providers.llm",
        class_name="GoogleGeminiProvider",
        default_model="gemma-4-26b-a4b-it",
        max_context=1000000,
        cost_per_1k_tokens=0.0035,
        api_key_env="GEMINI_API_KEY",
    ),
    "ollama": ProviderSpec(
        name="ollama",
        tier=ReasoningTier.T2,
        kind=ProviderKind.LLM,
        module="services.ml.providers.llm",
        class_name="OllamaProvider",
        default_model="llama3.1:latest",
        max_context=8192,
        cost_per_1k_tokens=0.0,
        api_key_env=None,
    ),
    "vllm": ProviderSpec(
        name="vllm",
        tier=ReasoningTier.T2,
        kind=ProviderKind.LLM,
        module="services.ml.providers",
        class_name="VLLMProvider",
        default_model="meta-llama-3.1-8b",
        max_context=32768,
        cost_per_1k_tokens=0.0,
        tri_attention=True,
        api_key_env=None,
    ),
    "openrouter": ProviderSpec(
        name="openrouter",
        tier=ReasoningTier.T3,
        kind=ProviderKind.GATEWAY,
        module="services.ml.providers.gateway",
        class_name="OpenRouterProvider",
        default_model="anthropic/claude-sonnet-4.5",
        max_context=200000,
        cost_per_1k_tokens=0.003,
        api_key_env="OPENROUTER_API_KEY",
    ),
    "deepgram": ProviderSpec(
        name="deepgram",
        tier=ReasoningTier.T3,
        kind=ProviderKind.STT,
        module="services.ml.providers.stt",
        class_name="DeepgramProvider",
        default_model="nova-2",
        api_key_env="DEEPGRAM_API_KEY",
    ),
    "elevenlabs": ProviderSpec(
        name="elevenlabs",
        tier=ReasoningTier.T3,
        kind=ProviderKind.TTS,
        module="services.ml.providers.tts",
        class_name="ElevenLabsProvider",
        default_model="eleven_turbo",
        api_key_env="ELEVENLABS_API_KEY",
    ),
    "voyage": ProviderSpec(
        name="voyage",
        tier=ReasoningTier.T3,
        kind=ProviderKind.EMBEDDING,
        module="services.ml.providers.embeddings",
        class_name="VoyageProvider",
        default_model="voyage-3",
        dimensions=1024,
        api_key_env="VOYAGE_API_KEY",
    ),
    "cohere": ProviderSpec(
        name="cohere",
        tier=ReasoningTier.T3,
        kind=ProviderKind.EMBEDDING,
        module="services.ml.providers.embeddings",
        class_name="CohereProvider",
        default_model="embed-english-v3",
        dimensions=1024,
        api_key_env="COHERE_API_KEY",
    ),
    "serper": ProviderSpec(
        name="serper",
        tier=ReasoningTier.T3,
        kind=ProviderKind.SEARCH,
        module="services.ml.providers.search",
        class_name="SerperProvider",
        default_model="default",
        api_key_env="SERPER_API_KEY",
    ),
    "internal": ProviderSpec(
        name="internal",
        tier=ReasoningTier.T0,
        kind=ProviderKind.INTERNAL,
        module="services.ml.providers",
        class_name="InternalProvider",
        default_model="1.0",
        api_key_env=None,
    ),
}


class ModelSelector:
    """Resolve preferred provider/model using config-first policy."""

    @classmethod
    def get_available_providers(cls) -> list[ProviderSpec]:
        available: list[ProviderSpec] = []
        for spec in PROVIDER_SPECS.values():
            if cls._provider_is_available(spec):
                available.append(spec)
        return available

    @classmethod
    def resolve(cls, user_model: str | None = None) -> tuple[str, str]:
        requested = (user_model or "").strip()

        if requested:
            resolved = cls._resolve_explicit_request(requested)
            if resolved is not None:
                return resolved

        env_default = os.environ.get("DEFAULT_MODEL", "").strip()
        if env_default:
            resolved = cls._resolve_explicit_request(env_default)
            if resolved is not None:
                return resolved

        available = cls.get_available_providers()
        if available:
            available.sort(key=lambda spec: (cls._tier_rank(spec.tier), spec.cost_per_1k_tokens))
            selected = available[0]
            return (selected.name, cls._model_override(selected) or selected.default_model)

        groq_spec = PROVIDER_SPECS.get("groq")
        if groq_spec is not None:
            return ("groq", groq_spec.default_model)

        raise RuntimeError("No model providers are available")

    @classmethod
    def _resolve_explicit_request(cls, value: str) -> tuple[str, str] | None:
        if "/" in value:
            provider_name, model_name = value.split("/", 1)
            provider_name = provider_name.strip().lower()
            model_name = model_name.strip()
            spec = PROVIDER_SPECS.get(provider_name)
            if spec and cls._provider_is_available(spec):
                return (provider_name, model_name)
            return None

        provider_name = value.strip().lower()
        spec = PROVIDER_SPECS.get(provider_name)
        if spec and cls._provider_is_available(spec):
            return (provider_name, cls._model_override(spec) or spec.default_model)
        return None

    @classmethod
    def _provider_is_available(cls, spec: ProviderSpec) -> bool:
        from infrastructure.config import settings

        if spec.api_key_env is None:
            return True

        # Check settings object first as it loads from .env
        val = getattr(settings, spec.api_key_env, None)
        if val:
            # Handle SecretStr
            if hasattr(val, "get_secret_value"):
                return bool(val.get_secret_value().strip())
            return bool(str(val).strip())

        # Fallback to os.environ
        return bool(os.environ.get(spec.api_key_env, "").strip())

    @classmethod
    def _model_override(cls, spec: ProviderSpec) -> str | None:
        env_key = f"{spec.name.upper()}_DEFAULT_MODEL"

        # Try os.environ for overrides
        override = os.environ.get(env_key, "").strip()
        if override:
            return override

        return None

    @staticmethod
    def _tier_rank(tier: ReasoningTier) -> int:
        mapping = {
            ReasoningTier.T0: 0,
            ReasoningTier.T1: 1,
            ReasoningTier.T2: 2,
            ReasoningTier.T3: 3,
        }
        return mapping[tier]


class ModelProviderFactory:
    """Lazy provider factory with instance reuse."""

    _instances: dict[str, ReasoningContract] = {}
    _lock = RLock()

    @classmethod
    def get_provider(cls, provider_type: str) -> ReasoningContract:
        key = provider_type.strip().lower()

        with cls._lock:
            if key in cls._instances:
                return cls._instances[key]

            spec = PROVIDER_SPECS.get(key)
            if spec is None:
                raise ValueError(f"Unknown provider type: {provider_type}")

            module = importlib.import_module(spec.module)
            provider_class: type = getattr(module, spec.class_name)
            instance = provider_class()
            cls._instances[key] = instance
            return instance

    @classmethod
    def list_providers(cls) -> list[str]:
        return list(PROVIDER_SPECS.keys())

    @classmethod
    def get_meta(cls, provider_type: str) -> dict[str, Any] | None:
        spec = PROVIDER_SPECS.get(provider_type.strip().lower())
        if spec is None:
            return None
        return {
            "name": spec.name,
            "tier": spec.tier.value,
            "kind": spec.kind.value,
            "default_model": spec.default_model,
            "max_context": spec.max_context,
            "cost_per_1k_tokens": spec.cost_per_1k_tokens,
            "dimensions": spec.dimensions,
            "tri_attention": spec.tri_attention,
            "api_key_env": spec.api_key_env,
        }

    @classmethod
    def get_available_types(cls, provider_type: str) -> list[str]:
        key = provider_type.strip().lower()
        spec = PROVIDER_SPECS.get(key)
        if spec is None:
            return []
        return [item.name for item in PROVIDER_SPECS.values() if item.kind == spec.kind]

    @classmethod
    def clear_cache(cls) -> None:
        with cls._lock:
            cls._instances.clear()


class ModelRegistry(IModelRegistry):
    """Resolved model registry built from stable provider specs and runtime policy."""

    def __init__(self) -> None:
        self._models: dict[str, ModelEntry] = {}
        self._lock = RLock()
        self._build_models()

    @property
    def models(self) -> dict[str, ModelEntry]:
        """Compatibility surface for legacy callers."""
        return self._models

    def _build_models(self) -> None:
        with self._lock:
            if self._models:
                return

            built: dict[str, ModelEntry] = {}
            for spec in PROVIDER_SPECS.values():
                prefix = "cloud" if spec.tier == ReasoningTier.T3 else "local"
                entry_name = f"{prefix}-{spec.name}"

                built[entry_name] = ModelEntry(
                    name=entry_name,
                    tier=spec.tier,
                    kind=spec.kind,
                    version=ModelSelector._model_override(spec) or spec.default_model,
                    status="active" if ModelSelector._provider_is_available(spec) else "inactive",
                    provider=spec.name,
                    max_context=spec.max_context,
                    cost_per_1k_tokens=spec.cost_per_1k_tokens,
                    dimensions=spec.dimensions,
                    tri_attention=spec.tri_attention,
                    metadata={
                        "module": spec.module,
                        "class_name": spec.class_name,
                    },
                )

            self._models = built

    def refresh(self, *, clear_provider_cache: bool = False) -> None:
        """Rebuild the registry from current environment and provider specs."""
        with self._lock:
            self._models = {}

        self._build_models()

        if clear_provider_cache:
            ModelProviderFactory.clear_cache()

    def get_active_model(self, name: str) -> ModelEntry | None:
        normalized = name.strip()
        normalized_lower = normalized.lower()

        # Check if it's a model ID that matches a provider's default model
        for item in self._models.values():
            if item.version == normalized and item.status == "active":
                return item

        # Handle model IDs in format "provider/model"
        if "/" in normalized:
            # First try to match against provider default models
            for item in self._models.values():
                if item.version == normalized and item.status == "active":
                    return item

            # If not found, try treating first part as provider name
            provider_name, _ = normalized.split("/", 1)
            normalized_provider = provider_name.strip().lower()
            for item in self._models.values():
                if item.provider == normalized_provider and item.status == "active":
                    return item
            return None

        entry = self._models.get(normalized)
        if entry and entry.status == "active":
            return entry

        if normalized_lower.startswith("gemini-") or normalized_lower.startswith("gemma-"):
            google_entry = self._active_provider_entry("google")
            if google_entry is not None:
                return replace(google_entry, version=normalized)
            groq_entry = self._active_provider_entry("groq")
            if groq_entry is not None:
                return replace(groq_entry, version="qwen/qwen3-32b")

        provider_entry = self._active_provider_entry(normalized_lower)
        if provider_entry is not None:
            return provider_entry

        return None

    def _active_provider_entry(self, provider_name: str) -> ModelEntry | None:
        normalized_provider = provider_name.strip().lower()
        for item in self._models.values():
            if item.provider == normalized_provider and item.status == "active":
                return item
        return None

    def get_active_by_tier(self, tier: ReasoningTier) -> list[ModelEntry]:
        entries = [
            entry
            for entry in self._models.values()
            if entry.tier == tier and entry.status == "active"
        ]
        entries.sort(key=lambda entry: entry.cost_per_1k_tokens)
        return entries

    def get_provider(
        self,
        tier: ReasoningTier,
        provider_name: str | None = None,
    ) -> ReasoningContract:
        """Return a provider instance for a tier or explicit provider name."""
        if provider_name:
            entry = self.get_active_model(provider_name)
            if entry is None:
                raise RuntimeError(f"No active provider available for {provider_name}")
            return ModelProviderFactory.get_provider(entry.provider)

        active_entries = self.get_active_by_tier(tier)
        if active_entries:
            return ModelProviderFactory.get_provider(active_entries[0].provider)

        fallback_entries = self.get_active_by_tier(ReasoningTier.T3)
        if fallback_entries:
            return ModelProviderFactory.get_provider(fallback_entries[0].provider)

        raise RuntimeError(f"No active providers available for tier {tier.value}")

    def get_entry_for_tier(
        self,
        tier: ReasoningTier,
        provider_name: str | None = None,
    ) -> ModelEntry:
        """Return the primary model entry for a tier or explicit provider."""
        if provider_name:
            entry = self.get_active_model(provider_name)
            if entry is not None:
                return entry
            raise RuntimeError(f"No active provider entry available for {provider_name}")

        active = self.get_active_by_tier(tier)
        if active:
            return active[0]

        fallback = self.get_active_by_tier(ReasoningTier.T3)
        if fallback:
            return fallback[0]

        raise RuntimeError(f"No active model entry available for tier {tier.value}")

    def get_fallback_profiles(
        self,
        tier: ReasoningTier,
        exclude_name: str,
    ) -> list[ModelEntry]:
        candidates = [
            entry
            for entry in self._models.values()
            if entry.tier == tier and entry.name != exclude_name and entry.status == "active"
        ]
        candidates.sort(key=lambda entry: entry.cost_per_1k_tokens)
        return candidates

    def list_entries(self) -> list[dict[str, Any]]:
        return [
            {
                "name": entry.name,
                "tier": entry.tier.value,
                "kind": entry.kind.value,
                "version": entry.version,
                "status": entry.status,
                "provider": entry.provider,
                "max_context": entry.max_context,
                "cost_per_1k_tokens": entry.cost_per_1k_tokens,
            }
            for entry in self._models.values()
        ]


@lru_cache(maxsize=1)
def get_model_registry() -> ModelRegistry:
    """Return a process-wide cached model registry."""
    return ModelRegistry()
