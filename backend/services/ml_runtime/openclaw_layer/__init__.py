"""OpenClaw-inspired ML runtime provider orchestration layer.

This module provides production-grade provider orchestration including:
- Provider registry with normalization
- Credential pool with load balancing
- Failover and retry logic with exponential backoff
- SecretRef pattern for secure credential storage
- Rate limiter with burst allowance
- Observability (logging, metrics, tracing)
- Cost tracking per provider/key/request
"""

from .config import (
    ProviderOrchestratorConfig,
    load_config_from_env,
)
from .provider_registry import (
    ProviderSpec,
    ProviderRegistry,
    create_default_registry,
)
from .credential_pool import (
    Credential,
    CredentialPool,
    create_credential,
)
from .failover_engine import (
    RetryPolicy,
    CircuitBreakerConfig,
    CircuitBreaker,
    CircuitBreakerState,
    FailoverEngine,
)
from .secret_ref import (
    SecretRef,
    SecretResolver,
)
from .rate_limiter import (
    RateLimiter,
    MultiProviderRateLimiter,
)
from .observability import (
    ProviderObservability,
    log_provider_request,
    log_provider_response,
)
from .cost_tracker import (
    CostTracker,
)

__all__ = [
    # Config
    "ProviderOrchestratorConfig",
    "load_config_from_env",
    # Provider Registry
    "ProviderSpec",
    "ProviderRegistry",
    "create_default_registry",
    # Credential Pool
    "Credential",
    "CredentialPool",
    "create_credential",
    # Failover Engine
    "RetryPolicy",
    "CircuitBreakerConfig",
    "CircuitBreaker",
    "CircuitBreakerState",
    "FailoverEngine",
    # Secret Ref
    "SecretRef",
    "SecretResolver",
    # Rate Limiter
    "RateLimiter",
    "MultiProviderRateLimiter",
    # Observability
    "ProviderObservability",
    "log_provider_request",
    "log_provider_response",
    # Cost Tracker
    "CostTracker",
]
