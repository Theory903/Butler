"""Telegram channel adapter (port of openclaw `extensions/telegram`)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .base import BaseChannel, ChannelConfig, ChannelKind, ChannelMessage

logger = logging.getLogger(__name__)


class TelegramChannel(BaseChannel):
    """Telegram Bot API adapter (no SDK; uses raw HTTP)."""

    BASE_URL = "https://api.telegram.org"

    def __init__(self, config: ChannelConfig) -> None:
        super().__init__(config)
        self._http: httpx.AsyncClient | None = None
        self._offset: int = 0

    async def connect(self) -> None:
        if not self._config.token:
            raise ValueError("Telegram token is required")
        self._http = httpx.AsyncClient(base_url=f"{self.BASE_URL}/bot{self._config.token}", timeout=30)
        self._connected = True
        logger.info("telegram_channel_connected")

    async def disconnect(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None
        self._connected = False

    async def send(self, message: ChannelMessage) -> None:
        if not self._http:
            raise RuntimeError("Telegram channel not connected")
        try:
            await self._http.post(
                "/sendMessage",
                json={"chat_id": message.chat_id, "text": message.text},
            )
        except Exception as e:
            logger.error(f"telegram_send_failed: {e}")

    async def receive(self) -> list[ChannelMessage]:
        if not self._http:
            return []
        try:
            response = await self._http.get(
                "/getUpdates",
                params={"offset": self._offset, "timeout": 0},
            )
            data = response.json()
            results: list[ChannelMessage] = []
            for update in data.get("result", []):
                self._offset = max(self._offset, update["update_id"] + 1)
                msg = update.get("message")
                if not msg:
                    continue
                results.append(
                    ChannelMessage(
                        channel=ChannelKind.TELEGRAM,
                        chat_id=str(msg["chat"]["id"]),
                        user_id=str(msg["from"]["id"]),
                        text=msg.get("text", ""),
                        metadata={"username": msg["from"].get("username", "")},
                    )
                )
            return results
        except Exception as e:
            logger.error(f"telegram_receive_failed: {e}")
            return []
