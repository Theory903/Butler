from __future__ import annotations

from abc import abstractmethod
from collections.abc import AsyncGenerator, Sequence
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from domain.base import DomainService


class ButlerMLBaseModel(BaseModel):
    """Shared strict base model for Butler ML contracts."""

    model_config = ConfigDict(extra="forbid")


class ComplexityLevel(StrEnum):
    """Complexity classification for a request."""

    SIMPLE = "simple"
    COMPLEX = "complex"


class ReasoningTier(StrEnum):
    """Abstract reasoning tier for model/runtime routing."""

    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


class ResponseFormat(StrEnum):
    """Preferred response-format hint for model/runtime generation."""

    TEXT = "text"
    JSON = "json"
    MARKDOWN = "markdown"


class EntityReference(ButlerMLBaseModel):
    """Structured entity extracted from a user request."""

    type: str = Field(min_length=1)
    value: str = Field(min_length=1)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type", "value")
    @classmethod
    def validate_non_empty_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Field must not be empty")
        return normalized


class IntentAlternative(ButlerMLBaseModel):
    """Alternative intent hypothesis for a request."""

    label: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("Intent label must not be empty")
        return normalized


class IntentResult(ButlerMLBaseModel):
    """Canonical intent classification output."""

    label: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    complexity: ComplexityLevel
    requires_tools: bool = False
    requires_memory: bool = False
    requires_approval: bool = False
    estimated_duration: int = Field(default=1, ge=0)

    # Expanded routing/planning fields
    tier: ReasoningTier | None = None
    entities: list[EntityReference] = Field(default_factory=list)
    alternatives: list[IntentAlternative] = Field(default_factory=list)
    requires_clarification: bool = False
    multi_intent: bool = False
    requires_research: bool = False
    calibration_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("Intent label must not be empty")
        return normalized


class RetrievalCandidate(ButlerMLBaseModel):
    """A generic candidate retrieved from any intelligence source."""

    source: str = Field(min_length=1)
    content: str = Field(min_length=1)
    score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source", "content")
    @classmethod
    def validate_non_empty_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Field must not be empty")
        return normalized


class RerankResult(ButlerMLBaseModel):
    """Ranking result for one candidate."""

    index: int = Field(ge=0)
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeatureVector(ButlerMLBaseModel):
    """Online or offline feature vector."""

    features: dict[str, float] = Field(default_factory=dict)
    timestamp: float
    version: str = Field(min_length=1)

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Version must not be empty")
        return normalized


class ReasoningRequest(ButlerMLBaseModel):
    """Canonical request contract for reasoning/model generation."""

    prompt: str = Field(min_length=1)
    system_prompt: str | None = None
    max_tokens: int = Field(default=4096, ge=1, le=32768)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    stop_sequences: list[str] = Field(default_factory=list)

    # Execution/routing hints
    preferred_model: str | None = None
    preferred_tier: ReasoningTier | None = None
    response_format: ResponseFormat | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Tool calling support
    tools: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Prompt must not be empty")
        return normalized

    @field_validator("system_prompt")
    @classmethod
    def validate_system_prompt(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("preferred_model")
    @classmethod
    def validate_preferred_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("stop_sequences")
    @classmethod
    def validate_stop_sequences(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = item.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(normalized)
        return cleaned


class ReasoningResponse(ButlerMLBaseModel):
    """Canonical reasoning/model response."""

    content: str
    raw_response: dict[str, Any] | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    model_version: str = Field(default="unknown")
    provider_name: str | None = None
    finish_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("model_version")
    @classmethod
    def validate_model_version(cls, value: str) -> str:
        normalized = value.strip()
        return normalized or "unknown"

    @field_validator("provider_name", "finish_reason")
    @classmethod
    def validate_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class RoutingDecision(ButlerMLBaseModel):
    """Structured routing decision for AI runtime/model selection."""

    tier: ReasoningTier
    provider_name: str | None = None
    model_name: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider_name", "model_name", "rationale")
    @classmethod
    def validate_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class IntentClassifierContract(DomainService):
    """Contract for intent classification."""

    @abstractmethod
    async def classify(self, message: str) -> IntentResult:
        """Classify a user message into a structured intent result."""
        raise NotImplementedError


class EmbeddingContract(DomainService):
    """Contract for embedding generation."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Embed one text input."""
        raise NotImplementedError

    @abstractmethod
    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed multiple text inputs."""
        raise NotImplementedError


class RankingContract(DomainService):
    """Contract for candidate ranking/reranking."""

    @abstractmethod
    async def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievalCandidate],
        user_id: str | None = None,
    ) -> list[RerankResult]:
        """Rerank candidates for a query."""
        raise NotImplementedError


class FeatureStoreContract(DomainService):
    """Contract for online feature retrieval."""

    @abstractmethod
    async def get_online_features(
        self,
        entity_id: str,
        feature_names: Sequence[str],
    ) -> FeatureVector:
        """Fetch an online feature vector."""
        raise NotImplementedError


class ReasoningContract(DomainService):
    """Contract for direct model/provider interactions."""

    @abstractmethod
    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        """Generate a full response."""
        raise NotImplementedError

    @abstractmethod
    async def generate_stream(
        self,
        request: ReasoningRequest,
    ) -> AsyncGenerator[str]:
        """Generate a streaming response as text chunks."""
        raise NotImplementedError


class IReasoningRuntime(DomainService):
    """Contract for Butler's reasoning runtime abstraction."""

    @abstractmethod
    async def generate(
        self,
        request: ReasoningRequest,
        tenant_id: str,  # Required for multi-tenant isolation
        *,
        preferred_tier: ReasoningTier | None = None,
    ) -> ReasoningResponse:
        """Generate a response using the selected reasoning tier.

        Args:
            tenant_id: Required tenant UUID for multi-tenant isolation
        """
        raise NotImplementedError

    @abstractmethod
    async def generate_stream(
        self,
        request: ReasoningRequest,
        *,
        preferred_tier: ReasoningTier | None = None,
    ) -> AsyncGenerator[str]:
        """Stream a response using the selected reasoning tier."""
        raise NotImplementedError


class IModelRegistry(DomainService):
    """Contract for model/provider registry lookups."""

    @abstractmethod
    def get_provider(
        self,
        tier: ReasoningTier,
        provider_name: str | None = None,
    ) -> ReasoningContract:
        """Return the configured provider for a given reasoning tier."""
        raise NotImplementedError

    @abstractmethod
    def get_active_model(self, name: str) -> Any | None:
        """Return an active model entry by entry name or provider alias."""
        raise NotImplementedError

    @abstractmethod
    def get_active_by_tier(self, tier: ReasoningTier) -> list[Any]:
        """Return active model entries for a reasoning tier."""
        raise NotImplementedError

    @abstractmethod
    def get_entry_for_tier(
        self,
        tier: ReasoningTier,
        provider_name: str | None = None,
    ) -> Any:
        """Return the primary model entry for a reasoning tier or provider."""
        raise NotImplementedError

    @abstractmethod
    def list_entries(self) -> list[dict[str, Any]]:
        """Return registered model entries."""
        raise NotImplementedError

    @abstractmethod
    def get_fallback_profiles(
        self,
        tier: ReasoningTier,
        exclude_name: str,
    ) -> list[Any]:
        """Return fallback model profiles for the given tier."""
        raise NotImplementedError
