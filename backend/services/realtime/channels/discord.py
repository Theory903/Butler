"""Discord channel adapter (port of openclaw `extensions/discord`)."""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseChannel, ChannelConfig, ChannelKind, ChannelMessage

import structlog

logger = structlog.get_logger(__name__)


class DiscordChannel(BaseChannel):
    """Discord adapter using `discord.py`.

    Requires:
        pip install discord.py
    Token via `ChannelConfig.token`.
    """

    def __init__(self, config: ChannelConfig) -> None:
        super().__init__(config)
        self._client: Any = None
        self._inbox: list[ChannelMessage] = []

    async def connect(self) -> None:
        try:
            import discord  # type: ignore[import-not-found]

            intents = discord.Intents.default()
            intents.message_content = True
            self._client = discord.Client(intents=intents)

            @self._client.event
            async def on_message(message: Any) -> None:
                if message.author == self._client.user:
                    return
                self._inbox.append(
                    ChannelMessage(
                        channel=ChannelKind.DISCORD,
                        chat_id=str(message.channel.id),
                        user_id=str(message.author.id),
                        text=message.content,
                        metadata={"author_name": str(message.author)},
                    )
                )

            await self._client.login(self._config.token)
            self._connected = True
            logger.info("discord_channel_connected")
        except ImportError:
            logger.warning("discord_py_not_installed: pip install discord.py")
        except Exception as e:
            logger.error(f"discord_connect_failed: {e}")

    async def disconnect(self) -> None:
        if self._client and self._connected:
            await self._client.close()
            self._connected = False

    async def send(self, message: ChannelMessage) -> None:
        if not self._client:
            raise RuntimeError("Discord channel not connected")
        try:
            channel = await self._client.fetch_channel(int(message.chat_id))
            await channel.send(message.text)
        except Exception as e:
            logger.error(f"discord_send_failed: {e}")

    async def receive(self) -> list[ChannelMessage]:
        messages = list(self._inbox)
        self._inbox.clear()
        return messages
