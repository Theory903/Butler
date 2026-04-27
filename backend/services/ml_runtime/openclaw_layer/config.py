"""Configuration models for the provider orchestrator layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal
from os import environ


class APIMode(str, Enum):
    """API mode for provider communication."""
    CHAT_COMPLETIONS = "chat_completions"
    ANTHROPIC_MESSAGES = "anthropic_messages"
    CODEX_RESPONSES = "codex_responses"
    AUTO_DETECT = "auto_detect"


@dataclass(frozen=True)
class ProviderConfig:
    """Configuration for a single provider."""
    name: str
    base_url: str | None = None
    api_mode: APIMode = APIMode.AUTO_DETECT
    default_model: str | None = None
    supports_tools: bool = True
    supports_streaming: bool = True
    supports_images: bool = False
    max_tokens: int = 8192
    timeout_seconds: int = 120


@dataclass(frozen=True)
class RetryConfig:
    """Retry policy configuration."""
    max_retries: int = 3
    initial_delay_seconds: float = 1.0
    backoff_factor: float = 2.0
    max_delay_seconds: float = 30.0
    jitter: bool = True


@dataclass(frozen=True)
class RateLimitConfig:
    """Rate limiting configuration."""
    requests_per_minute: int = 60
    requests_per_hour: int = 3600
    burst_allowance: int = 10


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5
    recovery_timeout_seconds: int = 60
    half_open_max_calls: int = 3


@dataclass
class ProviderOrchestratorConfig:
    """Main configuration for the provider orchestrator."""
    retry: RetryConfig = field(default_factory=RetryConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    enable_observability: bool = True
    enable_cost_tracking: bool = True
    default_timeout_seconds: int = 120
    log_level: str = "INFO"


def load_config_from_env() -> ProviderOrchestratorConfig:
    """Load configuration from environment variables."""
    retry = RetryConfig(
        max_retries=int(environ.get("PROVIDER_MAX_RETRIES", "3")),
        initial_delay_seconds=float(environ.get("PROVIDER_INITIAL_DELAY", "1.0")),
        backoff_factor=float(environ.get("PROVIDER_BACKOFF_FACTOR", "2.0")),
        max_delay_seconds=float(environ.get("PROVIDER_MAX_DELAY", "30.0")),
        jitter=environ.get("PROVIDER_RETRY_JITTER", "true").lower() == "true",
    )
    
    rate_limit = RateLimitConfig(
        requests_per_minute=int(environ.get("PROVIDER_RPM", "60")),
        requests_per_hour=int(environ.get("PROVIDER_RPH", "3600")),
        burst_allowance=int(environ.get("PROVIDER_BURST", "10")),
    )
    
    circuit_breaker = CircuitBreakerConfig(
        failure_threshold=int(environ.get("CIRCUIT_BREAKER_THRESHOLD", "5")),
        recovery_timeout_seconds=int(environ.get("CIRCUIT_BREAKER_TIMEOUT", "60")),
        half_open_max_calls=int(environ.get("CIRCUIT_BREAKER_HALF_OPEN", "3")),
    )
    
    log_level_str = environ.get("PROVIDER_LOG_LEVEL", "INFO").upper()
    valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR"}
    if log_level_str not in valid_log_levels:
        log_level_str = "INFO"
    
    return ProviderOrchestratorConfig(
        retry=retry,
        rate_limit=rate_limit,
        circuit_breaker=circuit_breaker,
        enable_observability=environ.get("PROVIDER_OBSERVABILITY", "true").lower() == "true",
        enable_cost_tracking=environ.get("PROVIDER_COST_TRACKING", "true").lower() == "true",
        default_timeout_seconds=int(environ.get("PROVIDER_TIMEOUT", "120")),
        log_level=log_level_str,
    )
