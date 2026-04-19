"""Butler Platform Registry — Phase 7b.

14 platform adapters that Butler can send/receive from.
Each adapter declares its capabilities, auth mechanism,
rate limits, and message format constraints.

Butler controls the platform dispatch boundary:
  OrchestratorService → PlatformRegistry.dispatch() → PlatformAdapter
  (never the reverse — platforms never call Orchestrator directly)

Platforms:
  1.  api             — REST API (JSON)
  2.  web             — Web frontend (SSE/WebSocket)
  3.  mobile_ios      — iOS app
  4.  mobile_android  — Android app
  5.  slack           — Slack Bot API
  6.  email           — Email (SMTP/IMAP)
  7.  whatsapp        — WhatsApp Business API
  8.  telegram        — Telegram Bot
  9.  sms             — SMS (Twilio/Vonage)
  10. discord         — Discord Bot
  11. teams           — Microsoft Teams
  12. voice           — Voice call (Twilio Voice)
  13. iot             — IoT device (MQTT/CoAP)
  14. mcp_client      — External MCP client

Sovereignty rules:
  - PlatformRegistry is read-only at runtime. Adapters are registered
    at startup. No dynamic registration from user input.
  - Each adapter declares a max_message_chars limit. Butler truncates
    before dispatching (no silent overflow).
  - Platform adapters NEVER call Hermes or memory services.
  - Auth mechanism is declared per platform; enforced by GatewayService.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PlatformId(str, Enum):
    API            = "api"
    WEB            = "web"
    MOBILE_IOS     = "mobile_ios"
    MOBILE_ANDROID = "mobile_android"
    SLACK          = "slack"
    EMAIL          = "email"
    WHATSAPP       = "whatsapp"
    TELEGRAM       = "telegram"
    SMS            = "sms"
    DISCORD        = "discord"
    TEAMS          = "teams"
    VOICE          = "voice"
    IOT            = "iot"
    MCP_CLIENT     = "mcp_client"
    SIGNAL         = "signal"
    MATTERMOST     = "mattermost"
    MATRIX         = "matrix"
    DINGTALK       = "dingtalk"
    FEISHU         = "feishu"
    WECOM          = "wecom"
    WEIXIN         = "weixin"
    QQBOT          = "qqbot"
    HOMEASSISTANT  = "homeassistant"
    BLUEBUBBLES    = "bluebubbles"
    WEBHOOK        = "webhook"


class AuthMechanism(str, Enum):
    JWT         = "jwt"
    OAUTH2      = "oauth2"
    API_KEY     = "api_key"
    WEBHOOK_SIG = "webhook_sig"
    MTLS        = "mtls"
    NONE        = "none"


class MessageFormat(str, Enum):
    JSON       = "json"
    MARKDOWN   = "markdown"
    PLAIN_TEXT = "plain_text"
    HTML       = "html"
    VOICE_SSML = "voice_ssml"
    MQTT       = "mqtt"
    MCP_JSON   = "mcp_json"


@dataclass(frozen=True)
class PlatformAdapter:
    """Describes a Butler-supported platform channel."""
    id: PlatformId
    display_name: str
    description: str
    auth_mechanism: AuthMechanism
    message_format: MessageFormat
    max_message_chars: int        # Hard limit; Butler truncates before dispatch
    supports_streaming: bool      # SSE or WebSocket available
    supports_files: bool          # Can receive file attachments
    supports_voice: bool          # Can handle audio input/output
    supports_multi_turn: bool     # Stateful multi-turn conversations
    rate_limit_rpm: int           # Platform-imposed RPM limit (0 = unlimited)
    webhook_path: str | None      # For outbound webhook delivery (None = pull)
    requires_approval_for: list[str] = field(default_factory=list)  # Tool categories requiring approval on this platform
    notes: str = ""
    adapter_class: type | None = None  # Lazy-loaded Hermes adapter class


# ── Platform Definitions ───────────────────────────────────────────────────────

_ADAPTERS: list[PlatformAdapter] = [

    PlatformAdapter(
        id=PlatformId.API,
        display_name="REST API",
        description="Direct REST API access — developer integration.",
        auth_mechanism=AuthMechanism.JWT,
        message_format=MessageFormat.JSON,
        max_message_chars=1_000_000,
        supports_streaming=True,
        supports_files=True,
        supports_voice=False,
        supports_multi_turn=True,
        rate_limit_rpm=10_000,
        webhook_path=None,
    ),

    PlatformAdapter(
        id=PlatformId.WEB,
        display_name="Web Frontend",
        description="React web interface via SSE and WebSocket.",
        auth_mechanism=AuthMechanism.JWT,
        message_format=MessageFormat.MARKDOWN,
        max_message_chars=500_000,
        supports_streaming=True,
        supports_files=True,
        supports_voice=True,
        supports_multi_turn=True,
        rate_limit_rpm=5_000,
        webhook_path=None,
    ),

    PlatformAdapter(
        id=PlatformId.MOBILE_IOS,
        display_name="iOS App",
        description="React Native iOS application.",
        auth_mechanism=AuthMechanism.JWT,
        message_format=MessageFormat.JSON,
        max_message_chars=200_000,
        supports_streaming=True,
        supports_files=True,
        supports_voice=True,
        supports_multi_turn=True,
        rate_limit_rpm=2_000,
        webhook_path=None,
        notes="APNs push notifications for background delivery.",
    ),

    PlatformAdapter(
        id=PlatformId.MOBILE_ANDROID,
        display_name="Android App",
        description="React Native Android application.",
        auth_mechanism=AuthMechanism.JWT,
        message_format=MessageFormat.JSON,
        max_message_chars=200_000,
        supports_streaming=True,
        supports_files=True,
        supports_voice=True,
        supports_multi_turn=True,
        rate_limit_rpm=2_000,
        webhook_path=None,
        notes="FCM push notifications for background delivery.",
    ),

    PlatformAdapter(
        id=PlatformId.SLACK,
        display_name="Slack",
        description="Slack Bot API with slash commands and app mentions.",
        auth_mechanism=AuthMechanism.WEBHOOK_SIG,
        message_format=MessageFormat.MARKDOWN,
        max_message_chars=3_000,       # Slack Block Kit message limit
        supports_streaming=False,
        supports_files=True,
        supports_voice=False,
        supports_multi_turn=True,
        rate_limit_rpm=60,             # Slack Tier 2 rate limit
        webhook_path="/webhooks/slack",
        requires_approval_for=["file_write", "external_api_calls", "email_send"],
        notes="Slack signatures verified via HMAC-SHA256.",
    ),

    PlatformAdapter(
        id=PlatformId.EMAIL,
        display_name="Email",
        description="SMTP send / IMAP receive integration.",
        auth_mechanism=AuthMechanism.API_KEY,
        message_format=MessageFormat.HTML,
        max_message_chars=100_000,
        supports_streaming=False,
        supports_files=True,
        supports_voice=False,
        supports_multi_turn=False,     # Each email is independent
        rate_limit_rpm=10,
        webhook_path="/webhooks/email",
        requires_approval_for=["*"],   # All tool calls require approval over email
        notes="DKIM/SPF verified on inbound. SendGrid/SES on outbound.",
    ),

    PlatformAdapter(
        id=PlatformId.WHATSAPP,
        display_name="WhatsApp",
        description="WhatsApp Business API via Meta Cloud API.",
        auth_mechanism=AuthMechanism.WEBHOOK_SIG,
        message_format=MessageFormat.PLAIN_TEXT,
        max_message_chars=4_096,
        supports_streaming=False,
        supports_files=True,           # Images, docs, audio
        supports_voice=True,
        supports_multi_turn=True,
        rate_limit_rpm=80,
        webhook_path="/webhooks/whatsapp",
        requires_approval_for=["file_write", "external_api_calls", "email_send"],
        notes="Meta webhook signature verified via X-Hub-Signature-256.",
    ),

    PlatformAdapter(
        id=PlatformId.TELEGRAM,
        display_name="Telegram",
        description="Telegram Bot API via webhooks.",
        auth_mechanism=AuthMechanism.WEBHOOK_SIG,
        message_format=MessageFormat.MARKDOWN,
        max_message_chars=4_096,
        supports_streaming=False,
        supports_files=True,
        supports_voice=True,
        supports_multi_turn=True,
        rate_limit_rpm=60,
        webhook_path="/webhooks/telegram",
        notes="Secret token in X-Telegram-Bot-Api-Secret-Token header.",
    ),

    PlatformAdapter(
        id=PlatformId.SMS,
        display_name="SMS",
        description="SMS via Twilio or Vonage.",
        auth_mechanism=AuthMechanism.WEBHOOK_SIG,
        message_format=MessageFormat.PLAIN_TEXT,
        max_message_chars=160,         # Single SMS segment; Butler auto-splits
        supports_streaming=False,
        supports_files=False,
        supports_voice=False,
        supports_multi_turn=True,
        rate_limit_rpm=10,
        webhook_path="/webhooks/sms",
        requires_approval_for=["*"],
        notes="160 chars/segment. Butler chunks long replies into segments.",
    ),

    PlatformAdapter(
        id=PlatformId.DISCORD,
        display_name="Discord",
        description="Discord Bot API with slash commands.",
        auth_mechanism=AuthMechanism.WEBHOOK_SIG,
        message_format=MessageFormat.MARKDOWN,
        max_message_chars=2_000,
        supports_streaming=False,
        supports_files=True,
        supports_voice=False,          # Voice channel audio via separate pipeline
        supports_multi_turn=True,
        rate_limit_rpm=50,
        webhook_path="/webhooks/discord",
        notes="Ed25519 signature verification on interactions.",
    ),

    PlatformAdapter(
        id=PlatformId.TEAMS,
        display_name="Microsoft Teams",
        description="Microsoft Teams Bot Framework integration.",
        auth_mechanism=AuthMechanism.OAUTH2,
        message_format=MessageFormat.JSON,
        max_message_chars=28_000,
        supports_streaming=False,
        supports_files=True,
        supports_voice=False,
        supports_multi_turn=True,
        rate_limit_rpm=120,
        webhook_path="/webhooks/teams",
        notes="Azure AD OAuth2 token validation. Adaptive Cards for rich messages.",
    ),

    PlatformAdapter(
        id=PlatformId.VOICE,
        display_name="Voice Call",
        description="Bidirectional voice via Twilio Voice or WebRTC.",
        auth_mechanism=AuthMechanism.JWT,
        message_format=MessageFormat.VOICE_SSML,
        max_message_chars=5_000,       # SSML per turn
        supports_streaming=True,
        supports_files=False,
        supports_voice=True,
        supports_multi_turn=True,
        rate_limit_rpm=5,
        webhook_path="/webhooks/voice",
        requires_approval_for=["email_send", "file_write", "external_api_calls"],
        notes="STT → Butler → TTS pipeline. P99 latency target <800ms.",
    ),

    PlatformAdapter(
        id=PlatformId.IOT,
        display_name="IoT Device",
        description="MQTT/CoAP for embedded and IoT device control.",
        auth_mechanism=AuthMechanism.MTLS,
        message_format=MessageFormat.MQTT,
        max_message_chars=65_535,
        supports_streaming=False,
        supports_files=False,
        supports_voice=False,
        supports_multi_turn=False,
        rate_limit_rpm=1_000,
        webhook_path=None,
        notes="mTLS client certificate per device. OWASP IoT Top 10 compliant.",
    ),

    PlatformAdapter(
        id=PlatformId.MCP_CLIENT,
        display_name="MCP Client",
        description="External MCP client (Claude Desktop, Cursor, IDEs).",
        auth_mechanism=AuthMechanism.API_KEY,
        message_format=MessageFormat.MCP_JSON,
        max_message_chars=2_000_000,
        supports_streaming=True,
        supports_files=True,
        supports_voice=False,
        supports_multi_turn=True,
        rate_limit_rpm=500,
        webhook_path=None,
        notes="MCP 2025-03-26 protocol. tools/list + tools/call JSON-RPC.",
    ),

    PlatformAdapter(
        id=PlatformId.SIGNAL,
        display_name="Signal",
        description="Signal Secure Messenger.",
        auth_mechanism=AuthMechanism.WEBHOOK_SIG,
        message_format=MessageFormat.PLAIN_TEXT,
        max_message_chars=4096,
        supports_streaming=False,
        supports_files=True,
        supports_voice=True,
        supports_multi_turn=True,
        rate_limit_rpm=60,
        webhook_path="/webhooks/signal",
    ),

    PlatformAdapter(
        id=PlatformId.MATTERMOST,
        display_name="Mattermost",
        description="Mattermost Enterprise messaging.",
        auth_mechanism=AuthMechanism.WEBHOOK_SIG,
        message_format=MessageFormat.MARKDOWN,
        max_message_chars=4000,
        supports_streaming=False,
        supports_files=True,
        supports_voice=False,
        supports_multi_turn=True,
        rate_limit_rpm=60,
        webhook_path="/webhooks/mattermost",
    ),

    PlatformAdapter(
        id=PlatformId.MATRIX,
        display_name="Matrix",
        description="Matrix decentralized network.",
        auth_mechanism=AuthMechanism.WEBHOOK_SIG,
        message_format=MessageFormat.MARKDOWN,
        max_message_chars=4096,
        supports_streaming=False,
        supports_files=True,
        supports_voice=False,
        supports_multi_turn=True,
        rate_limit_rpm=60,
        webhook_path="/webhooks/matrix",
    ),

    PlatformAdapter(
        id=PlatformId.DINGTALK,
        display_name="DingTalk",
        description="DingTalk Enterprise messaging.",
        auth_mechanism=AuthMechanism.WEBHOOK_SIG,
        message_format=MessageFormat.MARKDOWN,
        max_message_chars=2000,
        supports_streaming=False,
        supports_files=True,
        supports_voice=False,
        supports_multi_turn=True,
        rate_limit_rpm=60,
        webhook_path="/webhooks/dingtalk",
    ),

    PlatformAdapter(
        id=PlatformId.FEISHU,
        display_name="Feishu / Lark",
        description="Feishu / Lark Enterprise collaboration.",
        auth_mechanism=AuthMechanism.WEBHOOK_SIG,
        message_format=MessageFormat.MARKDOWN,
        max_message_chars=4000,
        supports_streaming=False,
        supports_files=True,
        supports_voice=False,
        supports_multi_turn=True,
        rate_limit_rpm=60,
        webhook_path="/webhooks/feishu",
    ),

    PlatformAdapter(
        id=PlatformId.WECOM,
        display_name="WeCom",
        description="WeCom (WeChat Work) Enterprise.",
        auth_mechanism=AuthMechanism.WEBHOOK_SIG,
        message_format=MessageFormat.MARKDOWN,
        max_message_chars=2048,
        supports_streaming=False,
        supports_files=True,
        supports_voice=False,
        supports_multi_turn=True,
        rate_limit_rpm=60,
        webhook_path="/webhooks/wecom",
    ),

    PlatformAdapter(
        id=PlatformId.WEIXIN,
        display_name="WeChat",
        description="WeChat Personal / Official Accounts.",
        auth_mechanism=AuthMechanism.WEBHOOK_SIG,
        message_format=MessageFormat.PLAIN_TEXT,
        max_message_chars=2048,
        supports_streaming=False,
        supports_files=True,
        supports_voice=True,
        supports_multi_turn=True,
        rate_limit_rpm=60,
        webhook_path="/webhooks/weixin",
    ),

    PlatformAdapter(
        id=PlatformId.QQBOT,
        display_name="QQ Bot",
        description="Tencent QQ Bot.",
        auth_mechanism=AuthMechanism.WEBHOOK_SIG,
        message_format=MessageFormat.MARKDOWN,
        max_message_chars=2000,
        supports_streaming=False,
        supports_files=True,
        supports_voice=False,
        supports_multi_turn=True,
        rate_limit_rpm=60,
        webhook_path="/webhooks/qqbot",
    ),

    PlatformAdapter(
        id=PlatformId.HOMEASSISTANT,
        display_name="Home Assistant",
        description="Home Assistant smart home integration.",
        auth_mechanism=AuthMechanism.WEBHOOK_SIG,
        message_format=MessageFormat.PLAIN_TEXT,
        max_message_chars=1000,
        supports_streaming=False,
        supports_files=False,
        supports_voice=False,
        supports_multi_turn=True,
        rate_limit_rpm=60,
        webhook_path="/webhooks/homeassistant",
    ),

    PlatformAdapter(
        id=PlatformId.BLUEBUBBLES,
        display_name="BlueBubbles",
        description="BlueBubbles iMessage bridge.",
        auth_mechanism=AuthMechanism.WEBHOOK_SIG,
        message_format=MessageFormat.PLAIN_TEXT,
        max_message_chars=2000,
        supports_streaming=False,
        supports_files=True,
        supports_voice=False,
        supports_multi_turn=True,
        rate_limit_rpm=60,
        webhook_path="/webhooks/bluebubbles",
    ),

    PlatformAdapter(
        id=PlatformId.WEBHOOK,
        display_name="Generic Webhook",
        description="Generic outbound webhook sender.",
        auth_mechanism=AuthMechanism.WEBHOOK_SIG,
        message_format=MessageFormat.JSON,
        max_message_chars=100_000,
        supports_streaming=False,
        supports_files=False,
        supports_voice=False,
        supports_multi_turn=False,
        rate_limit_rpm=100,
        webhook_path="/webhooks/generic",
    ),
]


# ── Registry ───────────────────────────────────────────────────────────────────

class PlatformRegistry:
    """Immutable registry of all supported Butler platforms.

    Usage:
        registry = PlatformRegistry()
        adapter = registry.get(PlatformId.SLACK)
        all_streaming = registry.filter(supports_streaming=True)
    """

    def __init__(self) -> None:
        self._adapters: dict[PlatformId, PlatformAdapter] = {
            a.id: a for a in _ADAPTERS
        }

    def get(self, platform_id: PlatformId) -> PlatformAdapter | None:
        return self._adapters.get(platform_id)

    def get_by_webhook_path(self, path: str) -> PlatformAdapter | None:
        """Find a platform by its incoming webhook path."""
        for adapter in self._adapters.values():
            if adapter.webhook_path == path:
                return adapter
        return None

    def filter(
        self,
        supports_streaming: bool | None = None,
        supports_voice: bool | None = None,
        supports_files: bool | None = None,
        auth_mechanism: AuthMechanism | None = None,
        message_format: MessageFormat | None = None,
    ) -> list[PlatformAdapter]:
        result = list(self._adapters.values())
        if supports_streaming is not None:
            result = [a for a in result if a.supports_streaming == supports_streaming]
        if supports_voice is not None:
            result = [a for a in result if a.supports_voice == supports_voice]
        if supports_files is not None:
            result = [a for a in result if a.supports_files == supports_files]
        if auth_mechanism is not None:
            result = [a for a in result if a.auth_mechanism == auth_mechanism]
        if message_format is not None:
            result = [a for a in result if a.message_format == message_format]
        return result

    def truncate_for_platform(self, platform_id: PlatformId, text: str) -> str:
        """Truncate text to the platform's max_message_chars limit."""
        adapter = self._adapters.get(platform_id)
        if adapter is None:
            return text
        limit = adapter.max_message_chars
        if len(text) <= limit:
            return text
        # Truncate and append truncation marker
        marker = "…[truncated]"
        return text[: limit - len(marker)] + marker

    def requires_approval_for_tool(self, platform_id: PlatformId, tool_category: str) -> bool:
        """Check if a platform requires approval for a given tool category."""
        adapter = self._adapters.get(platform_id)
        if adapter is None:
            return False
        return "*" in adapter.requires_approval_for or tool_category in adapter.requires_approval_for

    def list_all(self) -> list[dict]:
        return [
            {
                "id": a.id.value,
                "display_name": a.display_name,
                "auth": a.auth_mechanism.value,
                "format": a.message_format.value,
                "max_chars": a.max_message_chars,
                "streaming": a.supports_streaming,
                "voice": a.supports_voice,
                "files": a.supports_files,
                "rate_limit_rpm": a.rate_limit_rpm,
            }
            for a in self._adapters.values()
        ]

    @property
    def platform_count(self) -> int:
        return len(self._adapters)

    def load_hermes_platform_adapters(self, platform_ids: list[PlatformId] | None = None) -> None:
        """Lazy load Hermes platform adapter classes into the registry.
        
        Args:
            platform_ids: List of platforms to load. Defaults to all mapped platforms.
        """
        import importlib
        
        mapping = {
            PlatformId.SLACK: "integrations.hermes.gateway.platforms.slack.SlackAdapter",
            PlatformId.TELEGRAM: "integrations.hermes.gateway.platforms.telegram.TelegramAdapter",
            PlatformId.DISCORD: "integrations.hermes.gateway.platforms.discord.DiscordAdapter",
            PlatformId.EMAIL: "integrations.hermes.gateway.platforms.email.EmailAdapter",
            PlatformId.WHATSAPP: "integrations.hermes.gateway.platforms.whatsapp.WhatsAppAdapter",
            PlatformId.SMS: "integrations.hermes.gateway.platforms.sms.SmsAdapter",
            PlatformId.API: "integrations.hermes.gateway.platforms.api_server.APIServerAdapter",
            PlatformId.SIGNAL: "integrations.hermes.gateway.platforms.signal.SignalAdapter",
            PlatformId.MATTERMOST: "integrations.hermes.gateway.platforms.mattermost.MattermostAdapter",
            PlatformId.MATRIX: "integrations.hermes.gateway.platforms.matrix.MatrixAdapter",
            PlatformId.DINGTALK: "integrations.hermes.gateway.platforms.dingtalk.DingTalkAdapter",
            PlatformId.FEISHU: "integrations.hermes.gateway.platforms.feishu.FeishuAdapter",
            PlatformId.WECOM: "integrations.hermes.gateway.platforms.wecom.WeComAdapter",
            PlatformId.WEIXIN: "integrations.hermes.gateway.platforms.weixin.WeixinAdapter",
            PlatformId.QQBOT: "integrations.hermes.gateway.platforms.qqbot.QQAdapter",
            PlatformId.HOMEASSISTANT: "integrations.hermes.gateway.platforms.homeassistant.HomeAssistantAdapter",
            PlatformId.BLUEBUBBLES: "integrations.hermes.gateway.platforms.bluebubbles.BlueBubblesAdapter",
            PlatformId.WEBHOOK: "integrations.hermes.gateway.platforms.webhook.WebhookAdapter",
        }

        if platform_ids is None:
            platform_ids = list(mapping.keys())
            
        for pid in platform_ids:
            if pid not in mapping:
                continue
                
            module_path, class_name = mapping[pid].rsplit(".", 1)
            try:
                module = importlib.import_module(module_path)
                cls = getattr(module, class_name)
                
                # Update the adapter in place
                adapter = self._adapters[pid]
                # Dataclasses with frozen=True prevent direct attribute assignment
                # We bypass this for internal wiring by using object.__setattr__
                object.__setattr__(adapter, "adapter_class", cls)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Failed to load Hermes adapter for %s: %s", pid, e)


# ── Singleton ──────────────────────────────────────────────────────────────────

_registry: PlatformRegistry | None = None


def get_platform_registry() -> PlatformRegistry:
    global _registry  # noqa: PLW0603
    if _registry is None:
        _registry = PlatformRegistry()
    return _registry
