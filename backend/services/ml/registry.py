"""Model Registry — Auto-discovery SOLID pattern.

PROVIDER_META → SINGLE SOURCE OF TRUTH for all provider metadata
ModelRegistry.MODELS → Generated from PROVIDER_META
ModelProviderFactory → Lazy-loads provider classes by convention

DRY Principle: All provider metadata in ONE place.
SOLID Principle: Open/Closed - Add new providers without modifying factory.
"""

from dataclasses import dataclass
from typing import Any, Optional
import importlib
import os

import structlog

from domain.ml.contracts import ReasoningContract, IModelRegistry

logger = structlog.get_logger(__name__)

# =============================================================================
# SINGLE SOURCE OF TRUTH - All provider metadata in ONE place
# Format: "provider_name": {"module": "relative.to.services", "class": "ClassName", ...}
# =============================================================================
PROVIDER_META: dict[str, dict[str, Any]] = {
    # --- LLM Providers ---
    "openai": {"tier": 3, "type": "llm", "default_model": "gpt-4o", "cost": 0.010, "max_context": 128000, "module": "services.ml.providers", "class": "OpenAIProvider"},
    "anthropic": {"tier": 3, "type": "llm", "default_model": "claude-sonnet-4", "cost": 0.010, "max_context": 200000, "module": "services.ml.providers", "class": "AnthropicProvider"},
    "deepseek": {"tier": 3, "type": "llm", "default_model": "deepseek-chat", "cost": 0.001, "max_context": 64000, "module": "services.ml.providers.llm", "class": "DeepSeekProvider"},
    "groq": {"tier": 3, "type": "llm", "default_model": "llama-3.3-70b-versatile", "cost": 0.0006, "max_context": 8192, "module": "services.ml.providers.llm", "class": "GroqProvider"},
    "ollama": {"tier": 2, "type": "llm", "default_model": "llama3.1:latest", "cost": 0.0, "max_context": 8192, "module": "services.ml.providers.llm", "class": "OllamaProvider"},
    "mistral": {"tier": 3, "type": "llm", "default_model": "mistral-large", "cost": 0.002, "max_context": 128000, "module": "services.ml.providers.llm", "class": "MistralProvider"},
    "perplexity": {"tier": 3, "type": "llm", "default_model": "sonar-pro", "cost": 0.005, "max_context": 200000, "module": "services.ml.providers.llm", "class": "PerplexityProvider"},
    "together": {"tier": 3, "type": "llm", "default_model": "meta-llama-3.1-70b", "cost": 0.0008, "max_context": 125000, "module": "services.ml.providers.llm", "class": "TogetherProvider"},
    "xai": {"tier": 3, "type": "llm", "default_model": "grok-2", "cost": 0.005, "max_context": 131000, "module": "services.ml.providers.llm", "class": "xAIProvider"},
    "google": {"tier": 3, "type": "llm", "default_model": "gemini-2.5-pro", "cost": 0.0035, "max_context": 1000000, "module": "services.ml.providers.llm", "class": "GoogleGeminiProvider"},
    # Gateway Providers
    "openrouter": {"tier": 3, "type": "gateway", "default_model": "anthropic/claude-3.5-sonnet", "cost": 0.003, "max_context": 200000, "module": "services.ml.providers.gateway", "class": "OpenRouterProvider"},
    "cloudflare": {"tier": 3, "type": "gateway", "default_model": "@cf/meta/llama-3.1-8b-instruct", "cost": 0.0, "max_context": 128000, "module": "services.ml.providers.gateway", "class": "CloudflareAIGatewayProvider"},
    "vercel": {"tier": 3, "type": "gateway", "default_model": "ai", "cost": 0.0, "max_context": 1000000, "module": "services.ml.providers.gateway", "class": "VercelAIGatewayProvider"},
    # Cloud Providers - Extended
    "alibaba": {"tier": 3, "type": "cloud", "default_model": "qwen-turbo", "cost": 0.001, "max_context": 32000, "module": "services.ml.providers.cloud", "class": "AlibabaProvider"},
    "fireworks": {"tier": 3, "type": "llm", "default_model": "firefunction-v2", "cost": 0.0009, "max_context": 128000, "module": "services.ml.providers.llm", "class": "FireworksProvider"},
    "nvidia": {"tier": 3, "type": "llm", "default_model": "nemotron-70b", "cost": 0.001, "max_context": 128000, "module": "services.ml.providers.llm", "class": "NVIDIAProvider"},
    "venice": {"tier": 3, "type": "llm", "default_model": "venice-3-strong", "cost": 0.0, "max_context": 32000, "module": "services.ml.providers.llm", "class": "VeniceProvider"},
    "qwen": {"tier": 3, "type": "llm", "default_model": "qwen-plus", "cost": 0.001, "max_context": 131000, "module": "services.ml.providers.llm", "class": "QwenProvider"},
    "vllm": {"tier": 2, "type": "llm", "default_model": "meta-llama-3.1-8b", "cost": 0.0, "max_context": 32768, "triattention": True, "module": "services.ml.providers", "class": "VLLMProvider"},
    # --- Cloud Providers ---
    "azure": {"tier": 3, "type": "cloud", "default_model": "gpt-4o", "cost": 0.015, "max_context": 128000, "module": "services.ml.providers.cloud", "class": "AzureOpenAIProvider"},
    "bedrock": {"tier": 3, "type": "cloud", "default_model": "claude-3-sonnet", "cost": 0.012, "max_context": 200000, "module": "services.ml.providers.cloud", "class": "AmazonBedrockProvider"},
    "moonshot": {"tier": 3, "type": "cloud", "default_model": "moonshot-v1-128k", "cost": 0.001, "max_context": 128000, "module": "services.ml.providers.cloud", "class": "MoonshotProvider"},
    "minimax": {"tier": 3, "type": "cloud", "default_model": "MiniMax-Text-01", "cost": 0.0005, "max_context": 1000000, "module": "services.ml.providers.cloud", "class": "MiniMaxProvider"},
    "volcengine": {"tier": 3, "type": "cloud", "default_model": "doubao-pro", "cost": 0.0008, "max_context": 32000, "module": "services.ml.providers.cloud", "class": "VolcengineProvider"},
    "stepfun": {"tier": 3, "type": "cloud", "default_model": "step-1-8k", "cost": 0.001, "max_context": 8000, "module": "services.ml.providers.cloud", "class": "StepFunProvider"},
    # --- STT Providers ---
    "deepgram": {"tier": 3, "type": "stt", "default_model": "nova-2", "cost": 0.001, "max_context": 0, "module": "services.ml.providers.stt", "class": "DeepgramProvider"},
    "whisper": {"tier": 3, "type": "stt", "default_model": "base", "cost": 0.0, "max_context": 0, "module": "services.ml.providers.stt", "class": "WhisperProvider"},
    # --- TTS Providers ---
    "elevenlabs": {"tier": 3, "type": "tts", "default_model": "eleven_turbo", "cost": 0.001, "max_context": 0, "module": "services.ml.providers.tts", "class": "ElevenLabsProvider"},
    "coqui": {"tier": 3, "type": "tts", "default_model": "tts-1", "cost": 0.0, "max_context": 0, "module": "services.ml.providers.tts", "class": "CoquiProvider"},
    # --- Embedding Providers ---
    "voyage": {"tier": 3, "type": "embedding", "default_model": "voyage-3", "cost": 0.0005, "max_context": 0, "dimensions": 1024, "module": "services.ml.providers.embeddings", "class": "VoyageProvider"},
    "cohere": {"tier": 3, "type": "embedding", "default_model": "embed-english-v3", "cost": 0.0001, "max_context": 0, "dimensions": 1024, "module": "services.ml.providers.embeddings", "class": "CohereProvider"},
    # --- Search Providers ---
    "serper": {"tier": 3, "type": "search", "default_model": "default", "cost": 0.001, "max_context": 0, "module": "services.ml.providers.search", "class": "SerperProvider"},
    # --- Internal ---
    "internal": {"tier": 0, "type": "pattern", "default_model": "1.0", "cost": 0, "max_context": 0, "module": "services.ml.providers", "class": "InternalProvider"},
}


def _discover_provider_classes() -> dict[str, tuple[str, str]]:
    class_map: dict[str, tuple[str, str]] = {}
    for provider, meta in PROVIDER_META.items():
        module = meta.get("module", "services.ml.providers")
        class_name = meta.get("class", f"{provider.title()}Provider")
        class_map[provider] = (module, class_name)
    return class_map


_PROVIDER_CLASS_MAP: dict[str, tuple[str, str]] = _discover_provider_classes()


# Provider → Env Var mapping for API key discovery
PROVIDER_API_KEYS: dict[str, str | None] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "together": "TOGETHER_API_KEY",
    "xai": "XAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
    "venice": "VENICE_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "azure": "AZURE_OPENAI_KEY",
    "bedrock": "AWS_ACCESS_KEY_ID",
    "moonshot": "MOONSHOT_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "volcengine": "VOLCENGINE_API_KEY",
    "stepfun": "STEPFUN_API_KEY",
    "ollama": None,
    "vllm": None,
}


class ModelSelector:
    """Smart model selection with fallback hierarchy.
    
    Priority:
    1. User's explicit model param (e.g., "groq/llama-3.3-70b")
    2. DEFAULT_MODEL env var (if key exists)
    3. Auto-detected available provider (cheapest/fastest with key)
    """
    
    @classmethod
    def get_available_providers(cls) -> list[tuple[str, dict]]:
        available = []
        for provider, env_key in PROVIDER_API_KEYS.items():
            if env_key is None:
                continue
            api_key = os.environ.get(env_key, "").strip()
            if api_key:
                meta = PROVIDER_META.get(provider, {})
                available.append((provider, meta))
        return available
    
    @classmethod
    def _provider_has_key(cls, provider: str) -> bool:
        env_key = PROVIDER_API_KEYS.get(provider)
        if env_key is None:
            return True
        return bool(os.environ.get(env_key, "").strip())
    
    @classmethod
    def resolve(cls, user_model: str | None = None) -> tuple[str, str]:
        user_model = (user_model or "").strip()
        
        # 1. User explicit model
        if user_model:
            if "/" in user_model:
                provider, model = user_model.split("/", 1)
                provider = provider.lower()
                # Special: qwen via groq
                if provider == "qwen" and cls._provider_has_key("groq"):
                    return ("groq", f"qwen/{model}")
                if provider in PROVIDER_META:
                    return (provider, model)
            else:
                provider = user_model.lower()
                if provider in PROVIDER_META:
                    meta = PROVIDER_META[provider]
                    return (provider, meta.get("default_model", provider))
        
        # 2. DEFAULT_MODEL from env (only if provider has key)
        default = os.environ.get("DEFAULT_MODEL", "").strip()
        if default and "/" in default:
            provider, model = default.split("/", 1)
            provider = provider.lower()
            if provider in PROVIDER_META and cls._provider_has_key(provider):
                return (provider, model)
        
        # 3. Auto-select from available providers (cheapest first)
        available = cls.get_available_providers()
        if available:
            available.sort(key=lambda x: x[1].get("cost", 0))
            provider, meta = available[0]
            return (provider, meta.get("default_model", provider))
        
        # 4. Hard fallback (groq has free tier)
        return ("groq", "llama-3.3-70b-versatile")


@dataclass
class ModelEntry:
    name: str
    tier: int
    type: str
    version: str
    status: str
    provider: str
    max_context: int = 128000
    cost_per_1k_tokens: float = 0.0
    dimensions: int = 0
    rollout_percentage: int = 100
    tri_attention: bool = False


class ModelProviderFactory:
    _instances: dict[str, ReasoningContract] = {}

    @classmethod
    def get_provider(cls, provider_type: str) -> ReasoningContract:
        key = provider_type.lower()
        if key in cls._instances:
            return cls._instances[key]

        if key not in _PROVIDER_CLASS_MAP:
            raise ValueError(f"Unknown provider type: {provider_type}")

        module_path, class_name = _PROVIDER_CLASS_MAP[key]
        module = importlib.import_module(module_path)
        provider_class: type = getattr(module, class_name)
        instance = provider_class()
        cls._instances[key] = instance
        return instance

    @classmethod
    def list_providers(cls) -> list[str]:
        return list(PROVIDER_META.keys())

    @classmethod
    def get_meta(cls, provider_type: str) -> Optional[dict[str, Any]]:
        return PROVIDER_META.get(provider_type.lower())

    @classmethod
    def get_available_types(cls, provider_type: str) -> list[str]:
        meta = PROVIDER_META.get(provider_type.lower())
        if not meta:
            return []
        ptype = meta.get("type", "llm")
        return [k for k, v in PROVIDER_META.items() if v.get("type") == ptype]


class ModelRegistry(IModelRegistry):
    MODELS: dict[str, ModelEntry] = {}

    def __init__(self) -> None:
        self._build_models()

    def _build_models(self) -> None:
        if self.MODELS:
            return
        for provider_type, meta in PROVIDER_META.items():
            name = f"cloud-{provider_type}" if meta.get("tier", 0) == 3 else f"local-{provider_type}"
            self.MODELS[name] = ModelEntry(
                name=name,
                tier=meta.get("tier", 0),
                type=meta.get("type", "llm"),
                version=meta.get("default_model", "1.0.0"),
                status="active",
                provider=provider_type,
                max_context=meta.get("max_context", 128000),
                cost_per_1k_tokens=meta.get("cost", 0.0),
                dimensions=meta.get("dimensions", 0),
                tri_attention=meta.get("triattention", False),
            )

    def get_active_model(self, name: str) -> Optional[ModelEntry]:
        entry = self.MODELS.get(name)
        if entry and entry.status == "active":
            return entry
        return None

    def get_active_by_tier(self, tier: int) -> list[ModelEntry]:
        return [m for m in self.MODELS.values() if m.tier == tier and m.status == "active"]

    def get_provider(self, tier: int, provider_name: Optional[str] = None) -> ReasoningContract:
        if provider_name:
            return ModelProviderFactory.get_provider(provider_name)
        active = self.get_active_by_tier(tier)
        if active:
            return ModelProviderFactory.get_provider(active[0].provider)
        return ModelProviderFactory.get_provider("openai")

    def get_fallback_profiles(self, tier: int, exclude_name: str) -> list[ModelEntry]:
        """Return potential fallback models for a given tier."""
        candidates = [
            m for m in self.MODELS.values()
            if m.tier == tier and m.name != exclude_name and m.status == "active"
        ]
        # Sort by cost (cheapest fallback first)
        candidates.sort(key=lambda x: x.cost_per_1k_tokens)
        return candidates

    def list_entries(self) -> list[dict[str, Any]]:
        return [
            {
                "name": m.name,
                "tier": m.tier,
                "type": m.type,
                "version": m.version,
                "status": m.status,
                "provider": m.provider,
            }
            for m in self.MODELS.values()
        ]