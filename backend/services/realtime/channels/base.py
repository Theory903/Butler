"""Base channel adapter for messaging platforms.

Port-friendly abstraction over openclaw's `extensions/{discord,slack,...}` adapters.
Channels handle inbound message ingestion and outbound message dispatch.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ChannelKind(str, Enum):
    DISCORD = "discord"
    SLACK = "slack"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    IMESSAGE = "imessage"
    SIGNAL = "signal"
    MATRIX = "matrix"
    WEBHOOK = "webhook"
    EMAIL = "email"


@dataclass
class ChannelMessage:
    """Normalized inbound/outbound channel message."""

    channel: ChannelKind
    chat_id: str
    user_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    attachments: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ChannelConfig:
    """Channel adapter configuration."""

    kind: ChannelKind
    token: str | None = None
    webhook_url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class BaseChannel(ABC):
    """Base class for all channel adapters."""

    def __init__(self, config: ChannelConfig) -> None:
        self._config = config
        self._connected = False

    @property
    def kind(self) -> ChannelKind:
        return self._config.kind

    @property
    def is_connected(self) -> bool:
        return self._connected

    @abstractmethod
    async def connect(self) -> None:
        """Connect to the channel (e.g., open WS, register webhook)."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect cleanly."""

    @abstractmethod
    async def send(self, message: ChannelMessage) -> None:
        """Send an outbound message."""

    @abstractmethod
    async def receive(self) -> list[ChannelMessage]:
        """Pull pending inbound messages (or noop for push channels)."""
