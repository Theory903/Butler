from __future__ import annotations

import os
from typing import Any, Dict, Optional
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class ButlerBaseConfig(BaseSettings):
    """
    Standard configuration base for all Butler services (v3.0).
    
    Principles:
    - Immutable: Settings once loaded should not be changed at runtime.
    - Fail-fast: Service should not start if any critical config is invalid.
    - Secure: Sensitive fields are wrapped in SecretStr.
    """
    
    # -- Service Identity --
    SERVICE_NAME: str = Field(..., description="Canonical name of the service (e.g. 'orchestrator')")
    ENVIRONMENT: str = Field("development", pattern="^(development|staging|production)$")
    VERSION: str = "3.0.0"
    
    # -- Connectivity --
    HOST: str = "0.0.0.0"
    PORT: int = Field(8000, ge=1024, le=65535)
    
    # -- Observability --
    LOG_LEVEL: str = Field("INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    ENABLE_TRACING: bool = True
    METRICS_PORT: int = 9090
    
    # -- Security --
    # Every Butler service requires an API key for inter-service communication
    BUTLER_INTERNAL_KEY: SecretStr = Field(..., description="System-level key for internal RPC authentication")
    
    # -- Advanced: Hardware / Concurrency --
    MAX_CONCURRENCY: int = Field(1000, gt=0)
    SHUTDOWN_TIMEOUT_S: int = 30
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    @field_validator("SERVICE_NAME")
    @classmethod
    def validate_service_name(cls, v: str) -> str:
        if not v.islower():
            raise ValueError("Service names must be lowercase (e.g. 'ml-service')")
        return v
