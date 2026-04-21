"""Hermes OpenClaw Integration Shim.

Translates legacy OpenClaw channel patterns into the canonical ButlerMessage format.
This allows Hermes to natively consume OpenClaw channel adapters without modifying
the core Butler orchestration engine or violating the multi-tenant policy engine.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime

from domain.events.schemas import ButlerMessage, MessageContext, ChannelDefinition
from core.observability import get_metrics
from core.tracing import tracer


class OpenClawTranslationShim:
    """Translation layer between OpenClaw adapters and Butler core."""

    @staticmethod
    def to_butler_message(openclaw_event: Dict[str, Any], channel_id: str) -> ButlerMessage:
        """Convert an inbound OpenClaw event to a canonical ButlerMessage.
        
        Args:
            openclaw_event: The raw event dictionary from the OpenClaw adapter.
            channel_id: The Hermes channel identifier (e.g., 'whatsapp', 'discord').
            
        Returns:
            A normalized ButlerMessage ready for the orchestrator.
        """
        with tracer.start_as_current_span(f"openclaw_shim.translate_inbound"):
            # Extract standard OpenClaw fields
            oc_sender = openclaw_event.get("sender", {})
            oc_channel = openclaw_event.get("channel", {})
            content = openclaw_event.get("content", "")
            
            # Map to Butler MessageContext
            context = MessageContext(
                channel=ChannelDefinition(
                    platform=channel_id,
                    channel_id=oc_channel.get("id", "unknown"),
                    thread_id=oc_channel.get("thread_id")
                ),
                sender_id=oc_sender.get("id", "anonymous"),
                tenant_id=openclaw_event.get("workspace_id", "default")
            )
            
            get_metrics().inc_counter("openclaw_shim.messages_translated", tags={"direction": "inbound", "channel": channel_id})
            
            return ButlerMessage(
                id=openclaw_event.get("message_id", ""),
                content=content,
                context=context,
                timestamp=datetime.utcnow().isoformat(),
                metadata={"translation_source": "openclaw_shim", "raw_type": openclaw_event.get("type", "text")}
            )

    @staticmethod
    def from_butler_message(butler_message: ButlerMessage) -> Dict[str, Any]:
        """Convert an outbound ButlerMessage back to an OpenClaw event shape.
        
        Args:
            butler_message: The canonical message emitted by Butler Orchestrator.
            
        Returns:
            A dictionary matching the OpenClaw adapter expectations.
        """
        with tracer.start_as_current_span("openclaw_shim.translate_outbound"):
            get_metrics().inc_counter("openclaw_shim.messages_translated", tags={"direction": "outbound", "channel": butler_message.context.channel.platform})
            
            return {
                "type": "text",
                "content": butler_message.content,
                "channel": {
                    "id": butler_message.context.channel.channel_id,
                    "thread_id": butler_message.context.channel.thread_id
                },
                "workspace_id": butler_message.context.tenant_id,
                "metadata": butler_message.metadata
            }
