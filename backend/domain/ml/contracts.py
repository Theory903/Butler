from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from abc import abstractmethod
from domain.base import DomainService

class IntentResult(BaseModel):
    label: str
    confidence: float
    complexity: str  # simple, complex
    requires_tools: bool = False
    requires_memory: bool = False
    requires_approval: bool = False
    estimated_duration: int = 1  # seconds
    
    # Expanded v2.0 fields
    tier: Optional[str] = None  # T0, T1, T2, T3
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    alternatives: List[Dict[str, Any]] = Field(default_factory=list)
    requires_clarification: bool = False
    multi_intent: bool = False
    calibration_metadata: Dict[str, Any] = Field(default_factory=dict)

class RetrievalCandidate(BaseModel):
    """A generic candidate retrieved from any intelligence source."""
    source: str
    content: str
    score: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)

class RerankResult(BaseModel):
    index: int
    score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)

class FeatureVector(BaseModel):
    features: Dict[str, float]
    timestamp: float
    version: str

class ReasoningRequest(BaseModel):
    prompt: str
    system_prompt: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.0
    stop_sequences: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ReasoningResponse(BaseModel):
    content: str
    raw_response: Optional[Dict[str, Any]] = None
    usage: Dict[str, Any] = Field(default_factory=dict) # prompt_tokens, completion_tokens, timing (can be float)
    model_version: str

class IntentClassifierContract(DomainService):
    @abstractmethod
    async def classify(self, message: str) -> IntentResult:
        pass

class EmbeddingContract(DomainService):
    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        pass

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        pass

class RankingContract(DomainService):
    @abstractmethod
    async def rerank(self, query: str, candidates: List[Any], user_id: Optional[str] = None) -> List[RerankResult]:
        pass

class FeatureStoreContract(DomainService):
    @abstractmethod
    async def get_online_features(self, entity_id: str, feature_names: List[str]) -> FeatureVector:
        pass

class ReasoningContract(DomainService):
    """Protocol for LLM interactions (Frontier or Local)."""
    @abstractmethod
    async def generate(self, request: ReasoningRequest) -> ReasoningResponse:
        pass

    @abstractmethod
    async def generate_stream(self, request: ReasoningRequest):
        """Returns an async generator of string chunks."""
        pass


class IReasoningRuntime(DomainService):
    """Abstraction over MLRuntimeManager.

    Consumers (memory engines, search, deep_research) should depend on this
    interface, not on the concrete MLRuntimeManager, keeping the ML infra
    layer behind the domain boundary.

    Only the surface area actually used by cross-service callers is declared here.
    """

    @abstractmethod
    async def generate(
        self,
        request: ReasoningRequest,
        *,
        preferred_tier: Optional[str] = None,
    ) -> ReasoningResponse:
        """Generate a response using the selected reasoning tier."""

    @abstractmethod
    async def generate_stream(
        self,
        request: ReasoningRequest,
        *,
        preferred_tier: Optional[str] = None,
    ):
        """Stream a response. Returns an async generator of str chunks."""


class IModelRegistry(DomainService):
    """Abstraction over ModelRegistry.

    The ML service internals (smart_router, ranking) should inject this
    instead of the concrete ModelRegistry, ensuring they remain testable
    without a live provider registry.
    """

    @abstractmethod
    def get_provider(self, tier: int, provider_name: Optional[str] = None) -> ReasoningContract:
        """Return the configured reasoning provider for the given tier."""

    @abstractmethod
    def list_entries(self) -> List[Dict[str, Any]]:
        """Return all registered model entries (name, tier, status)."""

    @abstractmethod
    def get_fallback_profiles(self, tier: int, exclude_name: str) -> List[Any]:
        """Return potential fallback models for a given tier."""
