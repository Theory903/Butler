"""Realtime WebSocket Multiplexer.

Upgraded Hermes integration layer component for multiplexing multiple
channel streams (e.g. workspace events, tool logs, presence) over a single
hardened WebSocket transport.

Features:
- Multi-channel routing and fan-out
- Topic subscription and dynamic routing
- Integration with HermesTransportEdge
"""

import asyncio
import json
from typing import Dict, Set, Callable, Awaitable

from fastapi import WebSocket
from core.observability import get_metrics
from core.tracing import tracer
from services.gateway.transport import ButlerTransportContext


class TopicSubscription:
    """Represents a client's subscription to a specific stream topic."""
    
    def __init__(self, topic: str):
        self.topic = topic
        self.active_transports: Set[ButlerTransportContext] = set()

    def add_transport(self, transport: ButlerTransportContext):
        self.active_transports.add(transport)

    def remove_transport(self, transport: ButlerTransportContext):
        self.active_transports.discard(transport)


class WebSocketMultiplexer:
    """Routes realtime messages to connected transports based on topics."""
    
    def __init__(self):
        # Maps topic strings (e.g., 'workspace_123_events') to Subscriptions
        self.topics: Dict[str, TopicSubscription] = {}
        # Keep track of what each transport is subscribed to for clean teardown
        self.transport_subscriptions: Dict[str, Set[str]] = {}

    async def handle_mux_stream(self, transport_ctx: ButlerTransportContext):
        """Consume messages from the transport and manage its routing subscriptions."""
        session_id = transport_ctx.account.session_id
        if session_id not in self.transport_subscriptions:
            self.transport_subscriptions[session_id] = set()
            
        websocket = transport_ctx.websocket
        get_metrics().inc_counter("realtime.mux.connected", tags={"tenant": transport_ctx.account.sub})
        
        try:
            while True:
                # The transport layer handles the raw edge ping/pong bounds.
                # Here we handle multiplexer command messages (subscribe, unsubscribe, publish).
                data = await websocket.receive_text()
                
                try:
                    payload = json.loads(data)
                    action = payload.get("action")
                    topic = payload.get("topic")
                    
                    if action == "subscribe" and topic:
                        await self.subscribe(transport_ctx, topic)
                    elif action == "unsubscribe" and topic:
                        await self.unsubscribe(transport_ctx, topic)
                        
                except json.JSONDecodeError:
                    get_metrics().inc_counter("realtime.mux.errors", tags={"type": "invalid_json"})
                    
        except Exception as e:
            # Cleanup on disconnect
            await self._cleanup_transport(transport_ctx)

    async def _cleanup_transport(self, transport_ctx: ButlerTransportContext) -> None:
        """Remove a transport from all subscribed topics."""
        session_id = transport_ctx.account.session_id
        with tracer.start_as_current_span("mux.cleanup"):
            subscribed_topics = self.transport_subscriptions.pop(session_id, set())
            for topic in subscribed_topics:
                if topic in self.topics:
                    self.topics[topic].remove_transport(transport_ctx)
                    # Cleanup empty topics
                    if not self.topics[topic].active_transports:
                        del self.topics[topic]
            
            get_metrics().inc_counter("realtime.mux.disconnected")

    async def subscribe(self, transport_ctx: ButlerTransportContext, topic: str) -> None:
        """Subscribe a transport context to a specific routing topic."""
        with tracer.start_as_current_span(f"mux.subscribe"):
            if topic not in self.topics:
                self.topics[topic] = TopicSubscription(topic)
                
            self.topics[topic].add_transport(transport_ctx)
            
            session_id = transport_ctx.account.session_id
            if session_id not in self.transport_subscriptions:
                self.transport_subscriptions[session_id] = set()
            self.transport_subscriptions[session_id].add(topic)
            
            get_metrics().inc_counter("realtime.mux.subscriptions", tags={"topic": topic})

    async def unsubscribe(self, transport_ctx: ButlerTransportContext, topic: str) -> None:
        """Unsubscribe a transport context from a specific routing topic."""
        if topic in self.topics:
            self.topics[topic].remove_transport(transport_ctx)
            if not self.topics[topic].active_transports:
                del self.topics[topic]
                
        session_id = transport_ctx.account.session_id
        if session_id in self.transport_subscriptions:
            self.transport_subscriptions[session_id].discard(topic)

    async def broadcast(self, topic: str, message: dict) -> None:
        """Fan-out a message to all transports subscribed to the topic."""
        with tracer.start_as_current_span("mux.broadcast"):
            if topic not in self.topics:
                return
                
            subscription = self.topics[topic]
            if not subscription.active_transports:
                return
                
            # Fire-and-forget concurrent writes
            tasks = []
            msg_str = json.dumps({"topic": topic, "payload": message})
            
            for transport_ctx in list(subscription.active_transports):
                tasks.append(
                    asyncio.create_task(
                        self._safe_send(transport_ctx, msg_str)
                    )
                )
                
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                get_metrics().inc_counter("realtime.mux.broadcasts", tags={"topic": topic}, value=len(tasks))

    async def _safe_send(self, transport_ctx: ButlerTransportContext, msg_str: str) -> None:
        """Safely send a string to a websocket, handling disconnects gracefully."""
        try:
            await transport_ctx.websocket.send_text(msg_str)
        except Exception:
            # If sending fails, the receive loop will likely break and invoke cleanup
            pass
