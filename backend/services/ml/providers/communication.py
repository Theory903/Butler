"""Communication Providers — Slack, Discord, Telegram, WhatsApp, Line, Matrix, Teams, Twitch."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import Any

import httpx
import structlog

from services.security.safe_request import SafeRequestClient

logger = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)


class Message:
    """Unified message format."""

    def __init__(self, content: str, sender: str, channel: str, metadata: dict[str, Any] = None):
        self.content = content
        self.sender = sender
        self.channel = channel
        self.metadata = metadata or {}


class MessageHandler:
    """Handler for incoming messages."""

    def __init__(self, callback: Callable[[Message], Any]):
        self.callback = callback

    async def handle(self, message: Message):
        return await self.callback(message)


# ── Slack Provider ───────────────────────────────────────────────────────────


class SlackProvider:
    """Slack Messaging Provider."""

    def __init__(
        self,
        bot_token: str | None = None,
        signing_secret: str | None = None,
        tenant_id: str | None = None,
    ):
        self._bot_token = bot_token or os.environ.get("SLACK_BOT_TOKEN")
        self._signing_secret = signing_secret or os.environ.get("SLACK_SIGNING_SECRET")
        self.tenant_id = tenant_id or "default"
        self._client = httpx.AsyncClient(
            base_url="https://slack.com/api",
            headers={"Authorization": f"Bearer {self._bot_token}"},
            timeout=_DEFAULT_TIMEOUT,
        )
        self._safe_client = SafeRequestClient(timeout=_DEFAULT_TIMEOUT)
        self._handlers: dict[str, MessageHandler] = {}

    async def send_message(
        self, channel: str, text: str, blocks: list | None = None
    ) -> dict[str, Any]:
        """Send a message to a Slack channel."""
        payload = {"channel": channel, "text": text}
        if blocks:
            payload["blocks"] = blocks

        if self._safe_client and self.tenant_id:
            response = await self._safe_client.post(
                "https://slack.com/api/chat.postMessage",
                self.tenant_id,
                json=payload,
                headers={"Authorization": f"Bearer {self._bot_token}"},
            )
        else:
            response = await self._client.post("/chat.postMessage", json=payload)
        return response.json()

    async def send_dm(self, user_id: str, text: str) -> dict[str, Any]:
        """Send a direct message to a user."""
        # First open a conversation
        if self._safe_client and self.tenant_id:
            open_resp = await self._safe_client.post(
                "https://slack.com/api/conversations.open",
                self.tenant_id,
                json={"users": user_id},
                headers={"Authorization": f"Bearer {self._bot_token}"},
            )
        else:
            open_resp = await self._client.post("/conversations.open", json={"users": user_id})
        open_data = open_resp.json()
        if not open_data.get("ok"):
            return open_data

        channel = open_data["channel"]["id"]
        return await self.send_message(channel, text)

    async def add_reaction(self, channel: str, timestamp: str, emoji: str) -> dict[str, Any]:
        """Add a reaction to a message."""
        payload = {"channel": channel, "timestamp": timestamp, "name": emoji}
        if self._safe_client and self.tenant_id:
            response = await self._safe_client.post(
                "https://slack.com/api/reactions.add",
                self.tenant_id,
                json=payload,
                headers={"Authorization": f"Bearer {self._bot_token}"},
            )
        else:
            response = await self._client.post("/reactions.add", json=payload)
        return response.json()

    def on_message(self, callback: Callable[[Message], Any]):
        """Register a message handler."""
        self._handlers["message"] = MessageHandler(callback)
        return callback


# ── Discord Provider ────────────────────────────────────────────────────────


class DiscordProvider:
    """Discord Messaging Provider."""

    def __init__(self, bot_token: str | None = None, tenant_id: str | None = None):
        self._bot_token = bot_token or os.environ.get("DISCORD_BOT_TOKEN")
        self.tenant_id = tenant_id or "default"
        self._client = httpx.AsyncClient(
            base_url="https://discord.com/api/v10",
            headers={"Authorization": f"Bot {self._bot_token}"},
            timeout=_DEFAULT_TIMEOUT,
        )
        self._safe_client = SafeRequestClient(timeout=_DEFAULT_TIMEOUT)
        self._handlers: dict[str, MessageHandler] = {}

    async def send_message(
        self, channel_id: str, content: str, embed: dict | None = None
    ) -> dict[str, Any]:
        """Send a message to a Discord channel."""
        payload = {"content": content}
        if embed:
            payload["embeds"] = [embed]

        if self._safe_client and self.tenant_id:
            response = await self._safe_client.post(
                f"https://discord.com/api/v10/channels/{channel_id}/messages",
                self.tenant_id,
                json=payload,
                headers={"Authorization": f"Bot {self._bot_token}"},
            )
        else:
            response = await self._client.post(f"/channels/{channel_id}/messages", json=payload)
        return response.json()

    async def send_dm(self, user_id: str, content: str) -> dict[str, Any]:
        """Send a direct message to a user."""
        # Create DM channel first
        if self._safe_client and self.tenant_id:
            response = await self._safe_client.post(
                "https://discord.com/api/v10/users/@me/channels",
                self.tenant_id,
                json={"recipient_id": user_id},
                headers={"Authorization": f"Bot {self._bot_token}"},
            )
        else:
            response = await self._client.post(
                "/users/@me/channels", json={"recipient_id": user_id}
            )
        if response.status_code != 200:
            return response.json()

        channel = response.json()
        return await self.send_message(channel["id"], content)

    async def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> dict[str, Any]:
        """Add a reaction to a message."""
        # Discord uses encoded emoji format
        encoded_emoji = emoji.encode("unicode_escape").decode("ascii")
        # SafeRequestClient doesn't support PUT, use httpx with egress check
        # For now, use direct httpx since PUT is not supported by SafeRequestClient
        response = await self._client.put(
            f"/channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me"
        )
        return {"ok": response.status_code == 204}

    def on_message(self, callback: Callable[[Message], Any]):
        """Register a message handler."""
        self._handlers["message"] = MessageHandler(callback)
        return callback


# ── Telegram Provider ───────────────────────────────────────────────────────


class TelegramProvider:
    """Telegram Messaging Provider."""

    def __init__(self, bot_token: str | None = None, tenant_id: str | None = None):
        self._bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.tenant_id = tenant_id or "default"
        self._client = httpx.AsyncClient(
            base_url=f"https://api.telegram.org/bot{self._bot_token}",
            timeout=_DEFAULT_TIMEOUT,
        )
        self._safe_client = SafeRequestClient(timeout=_DEFAULT_TIMEOUT)
        self._handlers: dict[str, MessageHandler] = {}

    async def send_message(
        self, chat_id: str, text: str, parse_mode: str = "Markdown"
    ) -> dict[str, Any]:
        """Send a message to a Telegram chat."""
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if self._safe_client and self.tenant_id:
            response = await self._safe_client.post(
                f"https://api.telegram.org/bot{self._bot_token}/sendMessage",
                self.tenant_id,
                json=payload,
            )
        else:
            response = await self._client.post("/sendMessage", json=payload)
        return response.json()

    async def send_photo(
        self, chat_id: str, photo: str, caption: str | None = None
    ) -> dict[str, Any]:
        """Send a photo to a Telegram chat."""
        payload = {"chat_id": chat_id, "photo": photo}
        if caption:
            payload["caption"] = caption

        if self._safe_client and self.tenant_id:
            response = await self._safe_client.post(
                f"https://api.telegram.org/bot{self._bot_token}/sendPhoto",
                self.tenant_id,
                json=payload,
            )
        else:
            response = await self._client.post("/sendPhoto", json=payload)
        return response.json()

    async def answer_callback(
        self, callback_query_id: str, text: str, show_alert: bool = False
    ) -> dict[str, Any]:
        """Answer a callback query."""
        payload = {
            "callback_query_id": callback_query_id,
            "text": text,
            "show_alert": show_alert,
        }
        if self._safe_client and self.tenant_id:
            response = await self._safe_client.post(
                f"https://api.telegram.org/bot{self._bot_token}/answerCallbackQuery",
                self.tenant_id,
                json=payload,
            )
        else:
            response = await self._client.post("/answerCallbackQuery", json=payload)
        return response.json()

    def on_message(self, callback: Callable[[Message], Any]):
        """Register a message handler."""
        self._handlers["message"] = MessageHandler(callback)
        return callback


# ── WhatsApp Provider ────────────────────────────────────────────────────────


class WhatsAppProvider:
    """WhatsApp Business API Provider."""

    def __init__(
        self,
        phone_number_id: str | None = None,
        access_token: str | None = None,
        tenant_id: str | None = None,
    ):
        self._phone_number_id = phone_number_id or os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
        self._access_token = access_token or os.environ.get("WHATSAPP_ACCESS_TOKEN")
        self.tenant_id = tenant_id or "default"
        self._client = httpx.AsyncClient(
            base_url="https://graph.facebook.com/v18.0",
            headers={"Authorization": f"Bearer {self._access_token}"},
            timeout=_DEFAULT_TIMEOUT,
        )
        self._safe_client = SafeRequestClient(timeout=_DEFAULT_TIMEOUT)
        self._handlers: dict[str, MessageHandler] = {}

    async def send_message(self, to: str, text: str) -> dict[str, Any]:
        """Send a WhatsApp message."""
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }
        if self._safe_client and self.tenant_id:
            response = await self._safe_client.post(
                f"https://graph.facebook.com/v18.0/{self._phone_number_id}/messages",
                self.tenant_id,
                json=payload,
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
        else:
            response = await self._client.post(f"/{self._phone_number_id}/messages", json=payload)
        return response.json()

    async def send_template(
        self, to: str, template_name: str, components: list | None = None
    ) -> dict[str, Any]:
        """Send a WhatsApp template message."""
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "components": components or [],
            },
        }
        if self._safe_client and self.tenant_id:
            response = await self._safe_client.post(
                f"https://graph.facebook.com/v18.0/{self._phone_number_id}/messages",
                self.tenant_id,
                json=payload,
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
        else:
            response = await self._client.post(f"/{self._phone_number_id}/messages", json=payload)
        return response.json()

    def on_message(self, callback: Callable[[Message], Any]):
        """Register a message handler."""
        self._handlers["message"] = MessageHandler(callback)
        return callback


# ── Line Provider ───────────────────────────────────────────────────────────


class LineProvider:
    """LINE Messaging API Provider."""

    def __init__(
        self,
        channel_access_token: str | None = None,
        channel_secret: str | None = None,
        tenant_id: str | None = None,
    ):
        self._channel_access_token = channel_access_token or os.environ.get(
            "LINE_CHANNEL_ACCESS_TOKEN"
        )
        self._channel_secret = channel_secret or os.environ.get("LINE_CHANNEL_SECRET")
        self.tenant_id = tenant_id or "default"
        self._client = httpx.AsyncClient(
            base_url="https://api.line.me/v2",
            headers={"Authorization": f"Bearer {self._channel_access_token}"},
            timeout=_DEFAULT_TIMEOUT,
        )
        self._safe_client = SafeRequestClient(timeout=_DEFAULT_TIMEOUT)
        self._handlers: dict[str, MessageHandler] = {}

    async def send_message(self, to: str, text: str) -> dict[str, Any]:
        """Send a message to a LINE user."""
        payload = {
            "to": to,
            "messages": [{"type": "text", "text": text}],
        }
        if self._safe_client and self.tenant_id:
            response = await self._safe_client.post(
                "https://api.line.me/v2/bot/message/push",
                self.tenant_id,
                json=payload,
                headers={"Authorization": f"Bearer {self._channel_access_token}"},
            )
        else:
            response = await self._client.post("/bot/message/push", json=payload)
        return response.json()

    async def send_flex(self, to: str, alt_text: str, flex_content: dict) -> dict[str, Any]:
        """Send a flex message."""
        payload = {
            "to": to,
            "messages": [{"type": "flex", "altText": alt_text, "contents": flex_content}],
        }
        if self._safe_client and self.tenant_id:
            response = await self._safe_client.post(
                "https://api.line.me/v2/bot/message/push",
                self.tenant_id,
                json=payload,
                headers={"Authorization": f"Bearer {self._channel_access_token}"},
            )
        else:
            response = await self._client.post("/bot/message/push", json=payload)
        return response.json()

    def on_message(self, callback: Callable[[Message], Any]):
        """Register a message handler."""
        self._handlers["message"] = MessageHandler(callback)
        return callback


# ── Matrix Provider ─────────────────────────────────────────────────────────


class MatrixProvider:
    """Matrix Chat Provider."""

    def __init__(
        self,
        homeserver: str = "",
        access_token: str | None = None,
        user_id: str | None = None,
        tenant_id: str | None = None,
    ):
        self._homeserver = homeserver or os.environ.get("MATRIX_HOMESERVER", "https://matrix.org")
        self._access_token = access_token or os.environ.get("MATRIX_ACCESS_TOKEN")
        self._user_id = user_id or os.environ.get("MATRIX_USER_ID")
        self.tenant_id = tenant_id or "default"
        self._client = httpx.AsyncClient(
            base_url=self._homeserver,
            headers={"Authorization": f"Bearer {self._access_token}"},
            timeout=_DEFAULT_TIMEOUT,
        )
        self._safe_client = SafeRequestClient(timeout=_DEFAULT_TIMEOUT)
        self._handlers: dict[str, MessageHandler] = {}

    async def send_message(self, room_id: str, text: str) -> dict[str, Any]:
        """Send a message to a Matrix room."""
        txn_id = str(asyncio.get_event_loop().time())
        payload = {"msgtype": "m.text", "body": text}
        # SafeRequestClient doesn't support PUT, use httpx with egress check
        # For now, use direct httpx since PUT is not supported by SafeRequestClient
        response = await self._client.put(
            f"/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}",
            json=payload,
        )
        return response.json()

    async def send_notice(self, room_id: str, text: str) -> dict[str, Any]:
        """Send a notice (bot message) to a Matrix room."""
        txn_id = str(asyncio.get_event_loop().time())
        payload = {"msgtype": "m.notice", "body": text}
        # SafeRequestClient doesn't support PUT, use httpx with egress check
        # For now, use direct httpx since PUT is not supported by SafeRequestClient
        response = await self._client.put(
            f"/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}",
            json=payload,
        )
        return response.json()

    def on_message(self, callback: Callable[[Message], Any]):
        """Register a message handler."""
        self._handlers["message"] = MessageHandler(callback)
        return callback


# ── Microsoft Teams Provider ─────────────────────────────────────────────


class TeamsProvider:
    """Microsoft Teams Messaging Provider."""

    def __init__(
        self,
        bot_id: str | None = None,
        bot_password: str | None = None,
        tenant_id: str | None = None,
    ):
        self._bot_id = bot_id or os.environ.get("TEAMS_BOT_ID")
        self._bot_password = bot_password or os.environ.get("TEAMS_BOT_PASSWORD")
        self.tenant_id = tenant_id or "default"
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        self._safe_client = SafeRequestClient(timeout=_DEFAULT_TIMEOUT)
        self._service_url = ""
        self._handlers: dict[str, MessageHandler] = {}

    def set_service_url(self, service_url: str):
        """Set the service URL for Teams API."""
        self._service_url = service_url
        self._client.base_url = service_url

    async def send_message(self, conversation_id: str, text: str) -> dict[str, Any]:
        """Send a message to a Teams conversation."""
        payload = {
            "type": "message",
            "text": text,
            "from": {"id": self._bot_id},
            "conversation": {"id": conversation_id},
        }
        if self._safe_client and self.tenant_id and self._service_url:
            response = await self._safe_client.post(
                f"{self._service_url}/v3/conversations/{conversation_id}/activities",
                self.tenant_id,
                json=payload,
            )
        else:
            response = await self._client.post(
                f"/v3/conversations/{conversation_id}/activities",
                json=payload,
            )
        return response.json()

    async def send_card(self, conversation_id: str, card: dict) -> dict[str, Any]:
        """Send an adaptive card to Teams."""
        payload = {
            "type": "message",
            "attachments": [
                {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}
            ],
            "conversation": {"id": conversation_id},
        }
        if self._safe_client and self.tenant_id and self._service_url:
            response = await self._safe_client.post(
                f"{self._service_url}/v3/conversations/{conversation_id}/activities",
                self.tenant_id,
                json=payload,
            )
        else:
            response = await self._client.post(
                f"/v3/conversations/{conversation_id}/activities",
                json=payload,
            )
        return response.json()

    def on_message(self, callback: Callable[[Message], Any]):
        """Register a message handler."""
        self._handlers["message"] = MessageHandler(callback)
        return callback


# ── Communication Factory ────────────────────────────────────────────────


class CommunicationProviderFactory:
    """Factory for communication providers."""

    @classmethod
    def get_provider(cls, provider_type: str, **kwargs):
        """Return a communication provider instance."""
        if provider_type == "slack":
            return SlackProvider(**kwargs)
        if provider_type == "discord":
            return DiscordProvider(**kwargs)
        if provider_type == "telegram":
            return TelegramProvider(**kwargs)
        if provider_type == "whatsapp":
            return WhatsAppProvider(**kwargs)
        if provider_type == "line":
            return LineProvider(**kwargs)
        if provider_type == "matrix":
            return MatrixProvider(**kwargs)
        if provider_type == "teams":
            return TeamsProvider(**kwargs)
        raise ValueError(f"Unsupported communication provider: {provider_type}")
