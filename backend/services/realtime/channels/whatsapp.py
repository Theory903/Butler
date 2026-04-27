"""WhatsApp channel adapter (port of openclaw `extensions/whatsapp`).

Uses Meta WhatsApp Cloud API. Inbound messages arrive via webhook;
this adapter handles outbound dispatch and webhook payload normalization.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .base import BaseChannel, ChannelConfig, ChannelKind, ChannelMessage

import structlog

logger = structlog.get_logger(__name__)


class WhatsAppChannel(BaseChannel):
    """WhatsApp Cloud API adapter."""

    BASE_URL = "https://graph.facebook.com/v20.0"

    def __init__(self, config: ChannelConfig) -> None:
        super().__init__(config)
        self._http: httpx.AsyncClient | None = None
        self._phone_number_id = config.extra.get("phone_number_id", "")

    async def connect(self) -> None:
        if not self._config.token or not self._phone_number_id:
            raise ValueError("WhatsApp token + phone_number_id required")
        self._http = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {self._config.token}"},
            timeout=30,
        )
        self._connected = True
        logger.info("whatsapp_channel_connected")

    async def disconnect(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None
        self._connected = False

    async def send(self, message: ChannelMessage) -> None:
        if not self._http:
            raise RuntimeError("WhatsApp channel not connected")
        try:
            await self._http.post(
                f"/{self._phone_number_id}/messages",
                json={
                    "messaging_product": "whatsapp",
                    "to": message.chat_id,
                    "type": "text",
                    "text": {"body": message.text},
                },
            )
        except Exception as e:
            logger.error(f"whatsapp_send_failed: {e}")

    async def receive(self) -> list[ChannelMessage]:
        # Inbound is webhook-pushed — see api/routes/webhooks/whatsapp.py
        return []

    @staticmethod
    def parse_webhook(payload: dict[str, Any]) -> list[ChannelMessage]:
        """Normalize an inbound WhatsApp webhook payload."""
        messages: list[ChannelMessage] = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                for msg in change.get("value", {}).get("messages", []):
                    messages.append(
                        ChannelMessage(
                            channel=ChannelKind.WHATSAPP,
                            chat_id=msg.get("from", ""),
                            user_id=msg.get("from", ""),
                            text=msg.get("text", {}).get("body", ""),
                            metadata={"wa_id": msg.get("id", "")},
                        )
                    )
        return messages
