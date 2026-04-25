from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace

from core.observability import get_metrics
from domain.events.schemas import ButlerMessage, ChannelDefinition, MessageContext

tracer = trace.get_tracer(__name__)


class OpenClawTranslationError(ValueError):
    """Raised when an OpenClaw payload cannot be safely translated."""


class OpenClawTranslationShim:
    """Translation layer between OpenClaw adapters and Butler core.

    Responsibilities:
    - normalize inbound OpenClaw events into canonical ButlerMessage objects
    - normalize outbound ButlerMessage objects into OpenClaw-compatible payloads
    - emit observability signals without affecting the hot path
    - reject malformed payloads early and explicitly
    """

    @staticmethod
    def to_butler_message(openclaw_event: dict[str, Any], channel_id: str) -> ButlerMessage:
        """Convert an inbound OpenClaw event to a canonical ButlerMessage."""
        with tracer.start_as_current_span("openclaw_shim.translate_inbound") as span:
            normalized_channel_id = _clean_required(channel_id, "channel_id")

            if not isinstance(openclaw_event, dict):
                raise OpenClawTranslationError("openclaw_event must be a dictionary")

            oc_sender = _as_dict(openclaw_event.get("sender"))
            oc_channel = _as_dict(openclaw_event.get("channel"))
            message_type = _clean_optional(openclaw_event.get("type")) or "text"

            content = _extract_content(openclaw_event)
            message_id = (
                _clean_optional(openclaw_event.get("message_id"))
                or _clean_optional(openclaw_event.get("id"))
                or _synthetic_message_id(normalized_channel_id)
            )

            sender_id = (
                _clean_optional(oc_sender.get("id"))
                or _clean_optional(openclaw_event.get("sender_id"))
                or "anonymous"
            )

            resolved_channel_id = (
                _clean_optional(oc_channel.get("id"))
                or _clean_optional(openclaw_event.get("channel_id"))
                or "unknown"
            )

            tenant_id = (
                _clean_optional(openclaw_event.get("workspace_id"))
                or _clean_optional(openclaw_event.get("tenant_id"))
                or "default"
            )

            timestamp = _normalize_timestamp(
                openclaw_event.get("timestamp")
                or openclaw_event.get("created_at")
                or openclaw_event.get("occurred_at")
            )

            context = MessageContext(
                channel=ChannelDefinition(
                    platform=normalized_channel_id,
                    channel_id=resolved_channel_id,
                    thread_id=_clean_optional(
                        oc_channel.get("thread_id") or openclaw_event.get("thread_id")
                    ),
                ),
                sender_id=sender_id,
                tenant_id=tenant_id,
            )

            metadata = {
                "translation_source": "openclaw_shim",
                "raw_type": message_type,
                "adapter": "openclaw",
            }

            # Preserve non-core raw context for debugging/replay, without dumping everything blindly.
            raw_metadata = _as_dict(openclaw_event.get("metadata"))
            if raw_metadata:
                metadata["raw_metadata"] = raw_metadata

            attachments = _normalize_attachments(openclaw_event.get("attachments"))

            _safe_record_translation_metric(direction="inbound", channel=normalized_channel_id)

            span.set_attribute("messaging.system", "openclaw")
            span.set_attribute("messaging.operation", "translate_inbound")
            span.set_attribute("butler.channel", normalized_channel_id)
            span.set_attribute("butler.message_type", message_type)
            span.set_attribute("butler.tenant_id", tenant_id)

            return ButlerMessage(
                id=message_id,
                content=content,
                context=context,
                timestamp=timestamp.isoformat(),
                metadata=metadata,
                attachments=attachments,
            )

    @staticmethod
    def from_butler_message(butler_message: ButlerMessage) -> dict[str, Any]:
        """Convert an outbound ButlerMessage into an OpenClaw-compatible event shape."""
        with tracer.start_as_current_span("openclaw_shim.translate_outbound") as span:
            if not isinstance(butler_message, ButlerMessage):
                raise OpenClawTranslationError("butler_message must be a ButlerMessage")

            channel = butler_message.context.channel
            platform = _clean_required(channel.platform, "context.channel.platform")
            channel_id = _clean_required(channel.channel_id, "context.channel.channel_id")
            tenant_id = _clean_required(butler_message.context.tenant_id, "context.tenant_id")

            timestamp = _normalize_timestamp(getattr(butler_message, "timestamp", None))

            payload = {
                "message_id": _clean_optional(getattr(butler_message, "id", None))
                or _synthetic_message_id(platform),
                "type": "text",
                "content": butler_message.content or "",
                "timestamp": timestamp.isoformat(),
                "channel": {
                    "id": channel_id,
                    "thread_id": _clean_optional(channel.thread_id),
                },
                "workspace_id": tenant_id,
                "metadata": {
                    **_as_dict(getattr(butler_message, "metadata", None)),
                    "translation_source": "openclaw_shim",
                },
            }

            attachments = _normalize_attachments(getattr(butler_message, "attachments", None))
            if attachments:
                payload["attachments"] = attachments

            _safe_record_translation_metric(direction="outbound", channel=platform)

            span.set_attribute("messaging.system", "openclaw")
            span.set_attribute("messaging.operation", "translate_outbound")
            span.set_attribute("butler.channel", platform)
            span.set_attribute("butler.tenant_id", tenant_id)

            return payload


def _extract_content(openclaw_event: dict[str, Any]) -> str:
    """Extract canonical text content from a raw OpenClaw event."""
    content = openclaw_event.get("content")

    if isinstance(content, str):
        cleaned = content.strip()
        if cleaned:
            return cleaned

    if isinstance(content, dict):
        # Common adapter pattern: {"text": "..."}
        text_value = content.get("text")
        if isinstance(text_value, str) and text_value.strip():
            return text_value.strip()

    # Some adapters may emit body/text instead of content
    for fallback_key in ("text", "body", "message"):
        fallback = openclaw_event.get(fallback_key)
        if isinstance(fallback, str) and fallback.strip():
            return fallback.strip()

    raise OpenClawTranslationError("missing non-empty message content")


def _normalize_attachments(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []

    if not isinstance(value, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            normalized.append(dict(item))
    return normalized


def _normalize_timestamp(value: Any) -> datetime:
    if value is None:
        return datetime.now(UTC)

    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)

    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return datetime.now(UTC)
        try:
            parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
            return (
                parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
            )
        except ValueError:
            return datetime.now(UTC)

    return datetime.now(UTC)


def _clean_required(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise OpenClawTranslationError(f"{field_name} must be a non-empty string")
    cleaned = value.strip()
    if not cleaned:
        raise OpenClawTranslationError(f"{field_name} must be a non-empty string")
    return cleaned


def _clean_optional(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _synthetic_message_id(channel_id: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    return f"{channel_id}:{timestamp}"


def _safe_record_translation_metric(*, direction: str, channel: str) -> None:
    """Emit metrics without ever breaking translation."""
    try:
        metrics = get_metrics()

        # Preferred explicit method if you wire one in ButlerMetrics later.
        if hasattr(metrics, "record_tool_call"):
            metrics.record_tool_call(
                tool_name="openclaw_translation_shim",
                risk_tier="L0",
                success=True,
            )
    except Exception:
        # Observe-and-continue. Observability never gets to break the hot path.
        pass
