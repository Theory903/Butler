"""Butler Communication channel adapters for Butler.

Provides unified interface for Discord, Slack, Telegram, WhatsApp.
"""

import logging
from typing import Any

from services.realtime.channels.base import (
    BaseChannel,
    ChannelConfig,
    ChannelKind,
    ChannelMessage,
)
from services.realtime.channels.discord import DiscordChannel
from services.realtime.channels.slack import SlackChannel
from services.realtime.channels.telegram import TelegramChannel
from services.realtime.channels.whatsapp import WhatsAppChannel

import structlog

logger = structlog.get_logger(__name__)

__all__ = [
    "BaseChannel",
    "ChannelConfig",
    "ChannelKind",
    "ChannelMessage",
    "DiscordChannel",
    "SlackChannel",
    "TelegramChannel",
    "WhatsAppChannel",
    "ChannelRegistry",
    "build_channel",
]


class ChannelRegistry:
    """Registry for managing live channel adapters."""

    def __init__(self) -> None:
        self._channels: dict[str, BaseChannel] = {}

    def register(self, name: str, channel: BaseChannel) -> None:
        self._channels[name] = channel

    def get(self, name: str) -> BaseChannel | None:
        return self._channels.get(name)

    def list(self) -> list[str]:
        return list(self._channels.keys())

    async def connect_all(self) -> None:
        for ch in self._channels.values():
            if not ch.is_connected:
                await ch.connect()

    async def disconnect_all(self) -> None:
        """Disconnect all registered channels."""
        for channel_id, channel in self._channels.items():
            try:
                await channel.disconnect()
                logger.info("channel_disconnected", extra={"channel_id": channel_id})
            except Exception as e:
                logger.error(
                    "channel_disconnect_failed", extra={"channel_id": channel_id, "error": str(e)}
                )


_CHANNEL_BUILDERS: dict[ChannelKind, type[BaseChannel]] = {
    ChannelKind.DISCORD: DiscordChannel,
    ChannelKind.SLACK: SlackChannel,
    ChannelKind.TELEGRAM: TelegramChannel,
    ChannelKind.WHATSAPP: WhatsAppChannel,
}


def build_channel(config: ChannelConfig) -> BaseChannel:
    """Factory that builds the right adapter for a channel kind."""
    cls = _CHANNEL_BUILDERS.get(config.kind)
    if cls is None:
        raise ValueError(f"Unsupported channel kind: {config.kind}")
    return cls(config)
