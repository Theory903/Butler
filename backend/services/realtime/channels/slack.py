"""Slack channel adapter (port of openclaw `extensions/slack`)."""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseChannel, ChannelConfig, ChannelKind, ChannelMessage

logger = logging.getLogger(__name__)


class SlackChannel(BaseChannel):
    """Slack adapter using `slack_sdk`.

    Requires:
        pip install slack-sdk
    """

    def __init__(self, config: ChannelConfig) -> None:
        super().__init__(config)
        self._client: Any = None

    async def connect(self) -> None:
        try:
            from slack_sdk.web.async_client import AsyncWebClient

            self._client = AsyncWebClient(token=self._config.token)
            self._connected = True
            logger.info("slack_channel_connected")
        except ImportError:
            logger.warning("slack_sdk_not_installed: pip install slack-sdk")
        except Exception as e:
            logger.error(f"slack_connect_failed: {e}")

    async def disconnect(self) -> None:
        self._client = None
        self._connected = False

    async def send(self, message: ChannelMessage) -> None:
        if not self._client:
            raise RuntimeError("Slack channel not connected")
        try:
            await self._client.chat_postMessage(channel=message.chat_id, text=message.text)
        except Exception as e:
            logger.error(f"slack_send_failed: {e}")

    async def receive(self) -> list[ChannelMessage]:
        # Slack uses Events API webhooks — inbound events are pushed to the
        # webhook endpoint (see `services/realtime/channels/webhook.py`).
        return []
