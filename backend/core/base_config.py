from __future__ import annotations

import re

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SERVICE_NAME_RE = re.compile(r"^[a-z0-9-]+$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ButlerBaseConfig(BaseSettings):
    """Standard immutable base configuration for Butler services.

    Principles:
    - fail fast on invalid startup config
    - keep sensitive values wrapped
    - provide consistent operational defaults
    """

    # Service identity
    SERVICE_NAME: str = Field(
        ...,
        description="Canonical service slug, for example 'orchestrator'",
    )
    ENVIRONMENT: str = Field(
        default="development",
        pattern="^(development|staging|production)$",
    )
    VERSION: str = Field(
        default="3.0.0",
        description="Service build/version identifier",
    )

    # Connectivity
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000, ge=1024, le=65535)

    # Observability
    LOG_LEVEL: str = Field(
        default="INFO",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
    )
    ENABLE_TRACING: bool = True
    METRICS_PORT: int = Field(default=9090, ge=1024, le=65535)

    # Security
    BUTLER_INTERNAL_KEY: SecretStr = Field(
        ...,
        description="System-level key for internal RPC authentication",
    )

    # Runtime / concurrency
    MAX_CONCURRENCY: int = Field(default=1000, gt=0)
    SHUTDOWN_TIMEOUT_S: int = Field(default=30, gt=0, le=300)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        frozen=True,
    )

    @field_validator("SERVICE_NAME")
    @classmethod
    def validate_service_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("SERVICE_NAME must not be empty")
        if cleaned != cleaned.lower():
            raise ValueError("SERVICE_NAME must be lowercase")
        if not _SERVICE_NAME_RE.fullmatch(cleaned):
            raise ValueError(
                "SERVICE_NAME must contain only lowercase letters, numbers, and hyphens"
            )
        return cleaned

    @field_validator("HOST")
    @classmethod
    def validate_host(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("HOST must not be empty")
        return cleaned

    @field_validator("VERSION")
    @classmethod
    def validate_version(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("VERSION must not be empty")
        if not _VERSION_RE.fullmatch(cleaned):
            raise ValueError("VERSION contains invalid characters")
        return cleaned

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("LOG_LEVEL must not be empty")
        return cleaned.upper()

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_staging(self) -> bool:
        return self.ENVIRONMENT == "staging"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def bind_address(self) -> str:
        return f"{self.HOST}:{self.PORT}"
