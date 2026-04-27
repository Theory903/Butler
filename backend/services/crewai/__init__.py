"""CrewAI integration service for Butler.

This service provides CrewAI multi-agent orchestration capabilities
within Butler's execution framework, maintaining Butler's security,
durability, and governance boundaries.
"""

from .builder import CrewAIBuilder
from .config import CrewAIConfig
from .flow_integration import ButlerCheckpointHandler, CrewAIFlowAdapter
from .conditional_routing import ButlerRouterAdapter, ConditionalFlowBuilder
from .knowledge_integration import CrewAIKnowledgeAdapter, HybridKnowledgeRetriever
from .circuit_breaker import CircuitBreaker

__all__ = [
    "CrewAIBuilder",
    "CrewAIConfig",
    "CrewAIFlowAdapter",
    "ButlerCheckpointHandler",
    "ButlerRouterAdapter",
    "ConditionalFlowBuilder",
    "CrewAIKnowledgeAdapter",
    "HybridKnowledgeRetriever",
    "CircuitBreaker",
]
