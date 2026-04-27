"""Provider registry with normalization for ML runtime orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
from urllib.parse import urlparse

from .config import APIMode, ProviderConfig


class ProviderCapability(str, Enum):
    """Capabilities that providers can support."""
    TOOLS = "tools"
    STREAMING = "streaming"
    IMAGES = "images"
    STRUCTURED_OUTPUT = "structured_output"
    FUNCTION_CALLING = "function_calling"


@dataclass(frozen=True)
class ProviderSpec:
    """Specification for a provider."""
    name: str
    base_url: str | None
    api_mode: APIMode
    default_model: str | None
    capabilities: frozenset[ProviderCapability]
    max_tokens: int
    timeout_seconds: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderRegistry:
    """Registry for managing provider specifications."""
    _providers: dict[str, ProviderSpec] = field(default_factory=dict)
    _aliases: dict[str, str] = field(default_factory=dict)
    
    def register_provider(self, spec: ProviderSpec) -> None:
        """Register a provider specification."""
        self._providers[spec.name.lower()] = spec
        
        # Register common aliases
        if "openai" in spec.name.lower():
            self._aliases["gpt"] = spec.name.lower()
            self._aliases["openai"] = spec.name.lower()
        elif "anthropic" in spec.name.lower():
            self._aliases["claude"] = spec.name.lower()
            self._aliases["anthropic"] = spec.name.lower()
        elif "groq" in spec.name.lower():
            self._aliases["groq"] = spec.name.lower()
        elif "vertex" in spec.name.lower() or "gemini" in spec.name.lower():
            self._aliases["vertex"] = spec.name.lower()
            self._aliases["gemini"] = spec.name.lower()
    
    def get_provider(self, name: str) -> ProviderSpec | None:
        """Get a provider by name or alias."""
        normalized = name.lower()
        
        # Check direct name
        if normalized in self._providers:
            return self._providers[normalized]
        
        # Check aliases
        if normalized in self._aliases:
            return self._providers[self._aliases[normalized]]
        
        return None
    
    def list_providers(self) -> list[ProviderSpec]:
        """List all registered providers."""
        return list(self._providers.values())
    
    def normalize_request(self, provider_name: str, request: dict[str, Any]) -> dict[str, Any]:
        """Normalize a request for the specified provider."""
        provider = self.get_provider(provider_name)
        if not provider:
            raise ValueError(f"Unknown provider: {provider_name}")
        
        normalized = request.copy()
        
        # Normalize based on API mode
        if provider.api_mode == APIMode.ANTHROPIC_MESSAGES:
            normalized = self._normalize_for_anthropic(normalized)
        elif provider.api_mode == APIMode.CHAT_COMPLETIONS:
            normalized = self._normalize_for_chat_completions(normalized)
        elif provider.api_mode == APIMode.CODEX_RESPONSES:
            normalized = self._normalize_for_codex(normalized)
        
        return normalized
    
    def _normalize_for_anthropic(self, request: dict[str, Any]) -> dict[str, Any]:
        """Normalize request for Anthropic Messages API."""
        # Convert messages format if needed
        if "messages" not in request and "prompt" in request:
            request["messages"] = [{"role": "user", "content": request["prompt"]}]
        
        # Ensure system instruction is properly formatted
        if "system" in request and not isinstance(request["system"], str):
            request["system"] = str(request["system"])
        
        return request
    
    def _normalize_for_chat_completions(self, request: dict[str, Any]) -> dict[str, Any]:
        """Normalize request for OpenAI Chat Completions API."""
        # Ensure messages format
        if "messages" not in request and "prompt" in request:
            request["messages"] = [{"role": "user", "content": request["prompt"]}]
        
        return request
    
    def _normalize_for_codex(self, request: dict[str, Any]) -> dict[str, Any]:
        """Normalize request for Codex responses API."""
        # Codex-specific normalization
        return request
    
    def detect_api_mode(self, base_url: str | None) -> APIMode:
        """Auto-detect API mode from base URL."""
        if not base_url:
            return APIMode.AUTO_DETECT
        
        parsed = urlparse(base_url)
        
        # Anthropic patterns
        if "anthropic" in parsed.netloc or parsed.netloc.endswith(".anthropic.com"):
            return APIMode.ANTHROPIC_MESSAGES
        
        # OpenAI patterns
        if "openai" in parsed.netloc or parsed.netloc.endswith(".openai.com"):
            return APIMode.CHAT_COMPLETIONS
        
        # Groq patterns
        if "groq" in parsed.netloc:
            return APIMode.CHAT_COMPLETIONS
        
        # Vertex AI patterns
        if "vertex" in parsed.netloc or "googleapis.com" in parsed.netloc:
            return APIMode.CHAT_COMPLETIONS
        
        return APIMode.AUTO_DETECT
    
    def has_capability(self, provider_name: str, capability: ProviderCapability) -> bool:
        """Check if a provider supports a specific capability."""
        provider = self.get_provider(provider_name)
        if not provider:
            return False
        return capability in provider.capabilities


def register_builtin_providers(registry: ProviderRegistry) -> None:
    """Register built-in provider specifications."""
    
    # OpenAI
    registry.register_provider(ProviderSpec(
        name="openai",
        base_url="https://api.openai.com/v1",
        api_mode=APIMode.CHAT_COMPLETIONS,
        default_model="gpt-5.2",
        capabilities=frozenset([
            ProviderCapability.TOOLS,
            ProviderCapability.STREAMING,
            ProviderCapability.IMAGES,
            ProviderCapability.STRUCTURED_OUTPUT,
            ProviderCapability.FUNCTION_CALLING,
        ]),
        max_tokens=8192,
        timeout_seconds=120,
    ))
    
    # Anthropic
    registry.register_provider(ProviderSpec(
        name="anthropic",
        base_url="https://api.anthropic.com/v1",
        api_mode=APIMode.ANTHROPIC_MESSAGES,
        default_model="claude-opus-4-6",
        capabilities=frozenset([
            ProviderCapability.TOOLS,
            ProviderCapability.STREAMING,
            ProviderCapability.STRUCTURED_OUTPUT,
            ProviderCapability.FUNCTION_CALLING,
        ]),
        max_tokens=8192,
        timeout_seconds=120,
    ))
    
    # Groq
    registry.register_provider(ProviderSpec(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_mode=APIMode.CHAT_COMPLETIONS,
        default_model="llama-3.3-70b-versatile",
        capabilities=frozenset([
            ProviderCapability.TOOLS,
            ProviderCapability.STREAMING,
            ProviderCapability.FUNCTION_CALLING,
        ]),
        max_tokens=8192,
        timeout_seconds=120,
    ))
    
    # Vertex AI
    registry.register_provider(ProviderSpec(
        name="vertex-ai",
        base_url=None,  # Uses Google Cloud client
        api_mode=APIMode.CHAT_COMPLETIONS,
        default_model="gemini-2.5-flash",
        capabilities=frozenset([
            ProviderCapability.TOOLS,
            ProviderCapability.STREAMING,
            ProviderCapability.STRUCTURED_OUTPUT,
            ProviderCapability.FUNCTION_CALLING,
        ]),
        max_tokens=8192,
        timeout_seconds=120,
    ))
    
    # OpenRouter
    registry.register_provider(ProviderSpec(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_mode=APIMode.CHAT_COMPLETIONS,
        default_model="anthropic/claude-opus-4-6",
        capabilities=frozenset([
            ProviderCapability.TOOLS,
            ProviderCapability.STREAMING,
            ProviderCapability.FUNCTION_CALLING,
        ]),
        max_tokens=8192,
        timeout_seconds=120,
    ))


def create_default_registry() -> ProviderRegistry:
    """Create a provider registry with built-in providers."""
    registry = ProviderRegistry()
    register_builtin_providers(registry)
    return registry
