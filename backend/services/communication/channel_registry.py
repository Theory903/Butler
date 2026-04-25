"""
Butler Channel Registry System
Implements channel adoption matrix and registry following SWE-5 requirements.
"""

from __future__ import annotations

import enum
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, ClassVar
from uuid import UUID

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class Channel(enum.StrEnum):
    """Supported communication channels in adoption order."""

    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    SLACK = "slack"
    DISCORD = "discord"
    SIGNAL = "signal"
    MATRIX = "matrix"
    TEAMS = "teams"
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    WEBHOOK = "webhook"
    IN_APP = "in_app"

    @classmethod
    def priority_order(cls) -> list[Channel]:
        """Return channels in adoption priority order (P0 first)."""
        return [
            cls.WHATSAPP,
            cls.TELEGRAM,
            cls.SLACK,
            cls.DISCORD,
            cls.SIGNAL,
            cls.MATRIX,
            cls.TEAMS,
            cls.EMAIL,
            cls.SMS,
            cls.PUSH,
            cls.WEBHOOK,
            cls.IN_APP,
        ]


class AuthMode(enum.StrEnum):
    """Channel authentication modes."""

    OAUTH2 = "oauth2"
    API_KEY = "api_key"
    WEBHOOK_SECRET = "webhook_secret"
    JWT = "jwt"
    MUTUAL_TLS = "mutual_tls"
    NONE = "none"


class ApprovalModel(enum.StrEnum):
    """Channel user approval models."""

    EXPLICIT_OPT_IN = "explicit_opt_in"
    IMPLICIT = "implicit"
    DOUBLE_OPT_IN = "double_opt_in"
    VERIFIED = "verified"


class PortabilityRating(int, enum.Enum):
    """User data portability rating 1-5 (higher = better)."""

    VERY_LOW = 1
    LOW = 2
    MEDIUM = 3
    HIGH = 4
    VERY_HIGH = 5


class AdoptionTier(enum.StrEnum):
    """Channel adoption priority tier."""

    P0 = "p0"  # Production ready, fully supported
    P1 = "p1"  # Beta, partial support
    P2 = "p2"  # Alpha, experimental
    P3 = "p3"  # Planned, not implemented


class ChannelHealth(enum.StrEnum):
    """Channel health states."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ChannelConfig(BaseModel):
    """Channel configuration and metadata."""

    channel: Channel
    name: str
    auth_mode: AuthMode
    approval_model: ApprovalModel
    portability_rating: PortabilityRating
    adoption_tier: AdoptionTier
    rate_limit_requests: int = Field(gt=0, description="Requests per minute allowed")
    rate_limit_burst: int = Field(gt=0, description="Burst requests allowed")
    circuit_breaker_threshold: int = Field(gt=0, default=5, description="Failures before open")
    circuit_breaker_recovery_timeout: int = Field(
        gt=0, default=30, description="Seconds in half-open"
    )
    supports_idempotency: bool = Field(default=True)
    supports_delivery_receipts: bool = Field(default=False)
    supports_typing_indicators: bool = Field(default=False)
    supports_reactions: bool = Field(default=False)
    supports_threads: bool = Field(default=False)
    supports_attachments: bool = Field(default=False)
    max_attachment_size_bytes: int = Field(default=0)
    webhook_verification_required: bool = Field(default=True)
    enabled: bool = Field(default=True)

    @validator("rate_limit_burst")
    def burst_ge_rate_limit(cls, v: int, values: dict[str, Any]) -> int:
        if v < values.get("rate_limit_requests", 0):
            raise ValueError("Burst must be >= rate limit requests")
        return v


class Capability(enum.StrEnum):
    """Butler capabilities that channels may support."""

    SEND_MESSAGE = "send_message"
    RECEIVE_MESSAGE = "receive_message"
    EDIT_MESSAGE = "edit_message"
    DELETE_MESSAGE = "delete_message"
    SEND_ATTACHMENT = "send_attachment"
    RECEIVE_ATTACHMENT = "receive_attachment"
    TYPING_INDICATOR = "typing_indicator"
    MESSAGE_REACTION = "message_reaction"
    THREADS = "threads"
    DELIVERY_RECEIPT = "delivery_receipt"
    READ_RECEIPT = "read_receipt"
    USER_PRESENCE = "user_presence"
    BOT_COMMANDS = "bot_commands"
    INTERACTIVE_BUTTONS = "interactive_buttons"
    MODALS = "modals"


class CapabilityMatrix:
    """Maps channels to supported Butler capabilities."""

    _capabilities: ClassVar[dict[Channel, set[Capability]]] = defaultdict(set)

    @classmethod
    def register_capability(cls, channel: Channel, capability: Capability) -> None:
        cls._capabilities[channel].add(capability)

    @classmethod
    def register_capabilities(cls, channel: Channel, capabilities: list[Capability]) -> None:
        for cap in capabilities:
            cls.register_capability(channel, cap)

    @classmethod
    def supports(cls, channel: Channel, capability: Capability) -> bool:
        return capability in cls._capabilities.get(channel, set())

    @classmethod
    def get_supported_capabilities(cls, channel: Channel) -> set[Capability]:
        return cls._capabilities.get(channel, set()).copy()

    @classmethod
    def get_channels_for_capability(cls, capability: Capability) -> list[Channel]:
        return [channel for channel, caps in cls._capabilities.items() if capability in caps]


class RateLimiter:
    """Token bucket rate limiter per channel."""

    def __init__(self, requests_per_minute: int, burst: int):
        self.requests_per_minute = requests_per_minute
        self.burst = burst
        self.tokens = burst
        self.last_refill = datetime.utcnow()
        self.refill_interval = timedelta(seconds=60 / requests_per_minute)

    def _refill(self) -> None:
        now = datetime.utcnow()
        elapsed = now - self.last_refill
        new_tokens = int(elapsed / self.refill_interval)
        if new_tokens > 0:
            self.tokens = min(self.burst, self.tokens + new_tokens)
            self.last_refill = now

    def try_acquire(self, tokens: int = 1) -> bool:
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def reset(self) -> None:
        self.tokens = self.burst
        self.last_refill = datetime.utcnow()


class CircuitBreaker:
    """Circuit breaker pattern implementation per channel."""

    def __init__(self, failure_threshold: int, recovery_timeout: int):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = timedelta(seconds=recovery_timeout)
        self.failure_count = 0
        self.last_failure_time: datetime | None = None
        self.state = "closed"  # closed, open, half_open

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = "closed"
        self.last_failure_time = None

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        if self.failure_count >= self.failure_threshold:
            self.state = "open"

    def allow_request(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if (
                self.last_failure_time
                and datetime.utcnow() - self.last_failure_time > self.recovery_timeout
            ):
                self.state = "half_open"
                return True
            return False
        return True

    def reset(self) -> None:
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"


class ChannelAdapter(ABC):
    """Abstract base class for all channel adapters."""

    channel: ClassVar[Channel]
    config: ChannelConfig

    def __init__(self, config: ChannelConfig):
        self.config = config
        self.rate_limiter = RateLimiter(
            requests_per_minute=config.rate_limit_requests, burst=config.rate_limit_burst
        )
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_breaker_threshold,
            recovery_timeout=config.circuit_breaker_recovery_timeout,
        )
        self.health = ChannelHealth.UNKNOWN
        self.last_health_check: datetime | None = None

    @abstractmethod
    async def verify_webhook(self, headers: dict[str, str], body: bytes) -> bool:
        """Verify incoming webhook request authenticity."""

    @abstractmethod
    async def send_message(
        self, recipient_id: str, message: dict[str, Any], idempotency_key: UUID | None = None
    ) -> dict[str, Any]:
        """Send message through channel with idempotency support."""

    @abstractmethod
    async def check_health(self) -> ChannelHealth:
        """Perform channel health check and return current status."""

    @abstractmethod
    async def parse_incoming_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Parse channel-specific incoming message payload to standard format."""

    async def can_send(self) -> bool:
        """Check if message can be sent through this channel."""
        if not self.config.enabled:
            return False
        if not self.circuit_breaker.allow_request():
            return False
        return self.rate_limiter.try_acquire()

    def record_success(self) -> None:
        self.circuit_breaker.record_success()

    def record_failure(self) -> None:
        self.circuit_breaker.record_failure()


class ChannelRegistry:
    """Singleton registry for all available channel adapters."""

    _instance: ChannelRegistry | None = None
    _adapters: dict[Channel, ChannelAdapter] = {}
    _configs: dict[Channel, ChannelConfig] = {}

    def __new__(cls) -> ChannelRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_instance(cls) -> ChannelRegistry:
        return cls()

    def register(self, adapter_class: type[ChannelAdapter], config: ChannelConfig) -> None:
        """Register a channel adapter with configuration."""
        with tracer.start_as_current_span("channel_registry.register") as span:
            span.set_attribute("channel", config.channel.value)
            span.set_attribute("adapter_class", adapter_class.__name__)

            if config.channel in self._adapters:
                logger.warning(f"Overwriting existing adapter for channel: {config.channel}")

            adapter = adapter_class(config)
            self._adapters[config.channel] = adapter
            self._configs[config.channel] = config

            logger.info(f"Registered channel adapter: {config.channel} ({config.adoption_tier})")
            span.set_status(Status(StatusCode.OK))

    def get(self, channel: Channel) -> ChannelAdapter | None:
        """Get adapter for specified channel."""
        return self._adapters.get(channel)

    def get_config(self, channel: Channel) -> ChannelConfig | None:
        """Get configuration for specified channel."""
        return self._configs.get(channel)

    def get_enabled_channels(self) -> list[Channel]:
        """Get list of all enabled channels."""
        return [channel for channel, config in self._configs.items() if config.enabled]

    def get_channels_by_tier(self, tier: AdoptionTier) -> list[Channel]:
        """Get channels by adoption priority tier."""
        return [
            channel
            for channel, config in self._configs.items()
            if config.adoption_tier == tier and config.enabled
        ]

    async def check_all_health(self) -> dict[Channel, ChannelHealth]:
        """Run health checks on all registered channels."""
        results = {}
        with tracer.start_as_current_span("channel_registry.check_all_health"):
            for channel, adapter in self._adapters.items():
                try:
                    health = await adapter.check_health()
                    adapter.health = health
                    adapter.last_health_check = datetime.utcnow()
                    results[channel] = health
                except Exception as e:
                    logger.error(f"Health check failed for {channel}: {e}", exc_info=True)
                    results[channel] = ChannelHealth.UNHEALTHY
            return results

    def unregister(self, channel: Channel) -> None:
        """Unregister a channel adapter."""
        if channel in self._adapters:
            del self._adapters[channel]
            del self._configs[channel]
            logger.info(f"Unregistered channel adapter: {channel}")

    def reset(self) -> None:
        """Clear all registered adapters (for testing)."""
        self._adapters.clear()
        self._configs.clear()

    def load_hermes_adapters(self) -> None:
        """Dynamically load Hermes implementations for active channels.

        This satisfies the Flight 1 Oracle-Grade requirement where Hermes is the
        permanent integration layer for channels, but is not tightly coupled in Butler core.
        """
        import importlib

        with tracer.start_as_current_span("channel_registry.load_hermes_adapters"):
            for config in self._configs.values():
                if not config.enabled:
                    continue

                # We attempt to load the adapter from the hermes gateway namespace
                # Format: integrations.hermes.gateway.platforms.{channel}.{Channel}Adapter
                module_name = f"integrations.hermes.gateway.platforms.{config.channel.value}"
                class_name = f"{config.channel.name.capitalize()}Adapter"

                try:
                    module = importlib.import_module(module_name)
                    adapter_class = getattr(module, class_name)

                    # Instantiate and register the Hermes-backed adapter
                    adapter = adapter_class(config)
                    self._adapters[config.channel] = adapter
                    logger.info(f"Loaded Hermes adapter for channel: {config.channel}")
                except (ImportError, AttributeError):
                    logger.debug(
                        f"No Hermes adapter found for {config.channel}, falling back to default/stub."
                    )


# Initialize default capability mappings
def _initialize_default_capabilities() -> None:
    """Initialize standard capability mappings for known channels."""
    # P0 Channels
    CapabilityMatrix.register_capabilities(
        Channel.WHATSAPP,
        [
            Capability.SEND_MESSAGE,
            Capability.RECEIVE_MESSAGE,
            Capability.SEND_ATTACHMENT,
            Capability.RECEIVE_ATTACHMENT,
            Capability.TYPING_INDICATOR,
            Capability.DELIVERY_RECEIPT,
            Capability.READ_RECEIPT,
            Capability.INTERACTIVE_BUTTONS,
        ],
    )

    CapabilityMatrix.register_capabilities(
        Channel.TELEGRAM,
        [
            Capability.SEND_MESSAGE,
            Capability.RECEIVE_MESSAGE,
            Capability.EDIT_MESSAGE,
            Capability.DELETE_MESSAGE,
            Capability.SEND_ATTACHMENT,
            Capability.RECEIVE_ATTACHMENT,
            Capability.TYPING_INDICATOR,
            Capability.MESSAGE_REACTION,
            Capability.THREADS,
            Capability.BOT_COMMANDS,
            Capability.INTERACTIVE_BUTTONS,
            Capability.MODALS,
        ],
    )

    CapabilityMatrix.register_capabilities(
        Channel.SLACK,
        [
            Capability.SEND_MESSAGE,
            Capability.RECEIVE_MESSAGE,
            Capability.EDIT_MESSAGE,
            Capability.DELETE_MESSAGE,
            Capability.SEND_ATTACHMENT,
            Capability.RECEIVE_ATTACHMENT,
            Capability.TYPING_INDICATOR,
            Capability.MESSAGE_REACTION,
            Capability.THREADS,
            Capability.BOT_COMMANDS,
            Capability.INTERACTIVE_BUTTONS,
            Capability.MODALS,
            Capability.USER_PRESENCE,
        ],
    )

    CapabilityMatrix.register_capabilities(
        Channel.DISCORD,
        [
            Capability.SEND_MESSAGE,
            Capability.RECEIVE_MESSAGE,
            Capability.EDIT_MESSAGE,
            Capability.DELETE_MESSAGE,
            Capability.SEND_ATTACHMENT,
            Capability.RECEIVE_ATTACHMENT,
            Capability.TYPING_INDICATOR,
            Capability.MESSAGE_REACTION,
            Capability.THREADS,
            Capability.BOT_COMMANDS,
            Capability.INTERACTIVE_BUTTONS,
            Capability.USER_PRESENCE,
        ],
    )

    # P1 Channels
    CapabilityMatrix.register_capabilities(
        Channel.SIGNAL,
        [
            Capability.SEND_MESSAGE,
            Capability.RECEIVE_MESSAGE,
            Capability.SEND_ATTACHMENT,
            Capability.RECEIVE_ATTACHMENT,
            Capability.TYPING_INDICATOR,
            Capability.DELIVERY_RECEIPT,
            Capability.READ_RECEIPT,
        ],
    )

    CapabilityMatrix.register_capabilities(
        Channel.MATRIX,
        [
            Capability.SEND_MESSAGE,
            Capability.RECEIVE_MESSAGE,
            Capability.EDIT_MESSAGE,
            Capability.DELETE_MESSAGE,
            Capability.SEND_ATTACHMENT,
            Capability.RECEIVE_ATTACHMENT,
            Capability.TYPING_INDICATOR,
            Capability.MESSAGE_REACTION,
            Capability.THREADS,
            Capability.DELIVERY_RECEIPT,
            Capability.READ_RECEIPT,
        ],
    )

    # P2 Channels
    CapabilityMatrix.register_capabilities(
        Channel.TEAMS,
        [
            Capability.SEND_MESSAGE,
            Capability.RECEIVE_MESSAGE,
            Capability.SEND_ATTACHMENT,
            Capability.RECEIVE_ATTACHMENT,
            Capability.TYPING_INDICATOR,
            Capability.BOT_COMMANDS,
            Capability.INTERACTIVE_BUTTONS,
        ],
    )

    # Utility Channels
    CapabilityMatrix.register_capabilities(
        Channel.EMAIL,
        [
            Capability.SEND_MESSAGE,
            Capability.RECEIVE_MESSAGE,
            Capability.SEND_ATTACHMENT,
            Capability.RECEIVE_ATTACHMENT,
        ],
    )

    CapabilityMatrix.register_capabilities(
        Channel.SMS,
        [
            Capability.SEND_MESSAGE,
            Capability.RECEIVE_MESSAGE,
            Capability.DELIVERY_RECEIPT,
        ],
    )

    CapabilityMatrix.register_capabilities(
        Channel.PUSH,
        [
            Capability.SEND_MESSAGE,
            Capability.INTERACTIVE_BUTTONS,
        ],
    )

    CapabilityMatrix.register_capabilities(
        Channel.WEBHOOK,
        [
            Capability.SEND_MESSAGE,
            Capability.RECEIVE_MESSAGE,
            Capability.SEND_ATTACHMENT,
            Capability.RECEIVE_ATTACHMENT,
        ],
    )

    CapabilityMatrix.register_capabilities(
        Channel.IN_APP,
        [
            Capability.SEND_MESSAGE,
            Capability.RECEIVE_MESSAGE,
            Capability.EDIT_MESSAGE,
            Capability.DELETE_MESSAGE,
            Capability.SEND_ATTACHMENT,
            Capability.RECEIVE_ATTACHMENT,
            Capability.TYPING_INDICATOR,
            Capability.MESSAGE_REACTION,
            Capability.THREADS,
            Capability.DELIVERY_RECEIPT,
            Capability.READ_RECEIPT,
            Capability.INTERACTIVE_BUTTONS,
        ],
    )


_initialize_default_capabilities()
