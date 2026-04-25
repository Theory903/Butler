"""Butler configuration using pydantic-settings.

Single source of truth for all runtime settings.

Governed by: docs/00-governance/transplant-constitution.md §3
"""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Module-level export for easier imports
BUTLER_NODE_ID = "node-1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Service
    SERVICE_NAME: str = "butler"
    SERVICE_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    BUTLER_NODE_ID: str = "node-1"  # Override in prod with unique ID

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:19006"]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: object) -> object:
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            if raw.startswith("["):
                return raw
            return [item.strip() for item in raw.split(",") if item.strip()]
        return value

    @field_validator("PORT")
    @classmethod
    def validate_port(cls, value: int) -> int:
        """Validate port is in valid range."""
        if not 1 <= value <= 65535:
            raise ValueError("PORT must be between 1 and 65535")
        return value

    @field_validator("DATABASE_POOL_SIZE")
    @classmethod
    def validate_pool_size(cls, value: int) -> int:
        """Validate pool size is positive."""
        if value <= 0:
            raise ValueError("DATABASE_POOL_SIZE must be positive")
        return value

    @field_validator("JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    @classmethod
    def validate_token_expiry(cls, value: int) -> int:
        """Validate token expiry is positive."""
        if value <= 0:
            raise ValueError("JWT_ACCESS_TOKEN_EXPIRE_MINUTES must be positive")
        return value

    @field_validator("RATE_LIMIT_REQUESTS")
    @classmethod
    def validate_rate_limit(cls, value: int) -> int:
        """Validate rate limit is positive."""
        if value <= 0:
            raise ValueError("RATE_LIMIT_REQUESTS must be positive")
        return value

    @field_validator("MAX_CONCURRENCY")
    @classmethod
    def validate_concurrency(cls, value: int) -> int:
        """Validate max concurrency is positive."""
        if value <= 0:
            raise ValueError("MAX_CONCURRENCY must be positive")
        return value

    # Service Discovery / URLs
    ORCHESTRATOR_URL: str = "http://localhost:8000"  # Self-referencing in monolithic mode

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://butler:butler@localhost:5432/butler"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_SESSION_TTL: int = 86400
    REDIS_CACHE_TTL: int = 3600

    # JWT / Auth — RS256 ONLY. HS256 is NEVER used.
    # Point to PEM files. In dev, a key pair is auto-generated if not set.
    JWT_PRIVATE_KEY_PATH: str | None = None
    JWT_PUBLIC_KEY_PATH: str | None = None
    JWT_ALGORITHM: str = "RS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "https://butler.lasmoid.ai"
    JWT_AUDIENCE: str = "https://butler.lasmoid.ai"

    # JWKS
    JWKS_KEY_ID: str = "butler-key-1"
    JWKS_ROTATION_DAYS: int = 90

    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Advanced: Hardware / Concurrency
    MAX_CONCURRENCY: int = 1000
    BUTLER_INTERNAL_KEY: str = "butler-internal-dev-key"

    # WebAuthn (Passkeys)
    WEBAUTHN_RP_ID: str = "localhost"  # In prod: butler.lasmoid.ai
    WEBAUTHN_RP_NAME: str = "Butler AI"
    WEBAUTHN_ORIGIN: str = "http://localhost:3000"  # In prod: https://butler.lasmoid.ai

    # Idempotency
    IDEMPOTENCY_TTL_SECONDS: int = 86400

    # External AI Providers
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None
    GROQ_API_KEY: str | None = None

    # Hermes Integration
    HERMES_HOME: str = "/tmp/hermes"

    # LLM Model Config
    DEFAULT_MODEL: str = "claude-sonnet-4-5"  # Profile A — standard chat
    LONG_CONTEXT_MODEL: str = "claude-opus-4-5"  # Profile B — long-context planner
    LONG_CONTEXT_TOKEN_THRESHOLD: int = 8192  # Switch to Profile B above this
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    RERANKER_MODEL: str = "bge-reranker-v2-m3"

    # ── Audio Service ──────────────────────────────────────────────────────
    AUDIO_GPU_ENDPOINT: str = "http://audio-gpu:8009"
    STT_DEFAULT_QUALITY: str = "balanced"
    STT_CONFIDENCE_THRESHOLD: float = 0.85
    STT_UPGRADE_THRESHOLD: float = 0.75
    STT_PRIMARY_MODEL: str = "parakeet-tdt-0.6b-v3"
    STT_SECONDARY_MODEL: str = "whisper-large-v3"
    STT_LOCAL_MODEL: str = "whisper.cpp-base"

    DIARIZATION_ENABLED: bool = True
    DIARIZATION_MODEL: str = "pyannote/heartbeat"

    TTS_DEFAULT_VOICE: str = "en_US/aristl"
    HUGGINGFACE_TOKEN: str | None = None
    ACOUSTID_API_KEY: str | None = None

    # ── Memory Infrastructure ───────────────────────────────────────────────
    KNOWLEDGE_STORE_BACKEND: str = "postgres"  # postgres | neo4j
    VECTOR_STORE_BACKEND: str = "postgres"  # postgres | qdrant

    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "butler-dev"

    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: str | None = None

    # ── Data Directory ────────────────────────────────────────────────────────
    # BUTLER_DATA_DIR is the canonical data root for ALL persistent Butler data.
    BUTLER_DATA_DIR: str = "/var/butler/data"

    # ── TriAttention ML Serving ───────────────────────────────────────────────
    # Profile B: long-context vLLM serving with TriAttention KV compression.
    # ONLY used by MLService. Never imported by Orchestrator, Memory, or routes.
    TRIATTENTION_ENABLED: bool = False  # Enable Profile B serving
    TRIATTENTION_HOST: str = ""  # vLLM host for Profile B
    TRIATTENTION_KV_BUDGET_TOKENS: int = 20000
    # NOTE: prefix_caching must be DISABLED when TriAttention is active.
    # This is enforced by MLService, not set here.

    # ── pyturboquant Cold Tier ────────────────────────────────────────────────
    TURBOQUANT_ENABLED: bool = False  # Enable cold-tier memory compression
    TURBOQUANT_INDEX_PATH: str = ""  # Path to cold-tier index directory
    TURBOQUANT_CODEBOOK_SIZE: int = 256  # PQ codebook size

    # ── Marketplace & Ecosystem (Phase 12) ──────────────────────────────────
    CLAW_HUB_URL: str = "http://localhost:8080"  # Mock registry for now
    SEARXNG_URL: str = "http://localhost:8080"
    SEMGREP_RULES_PATH: str | None = None
    PLUGINS_ISOLATION_ENABLED: bool = True
    PLUGINS_ISOLATION_BACKEND: str = "subprocess"  # subprocess | docker
    PLUGINS_DOCKER_IMAGE: str = "butler-sandbox:latest"

    # Observability
    OTEL_ENDPOINT: str | None = None  # e.g. "http://otel-collector:4317"
    LOG_LEVEL: str = "INFO"

    # AWS Configuration
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None


settings = Settings()
