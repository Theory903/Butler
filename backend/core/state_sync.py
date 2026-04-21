import asyncio
import json
import uuid
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from redis.asyncio import Redis
import structlog

logger = structlog.get_logger(__name__)


class StateType(str, Enum):
    """State event types for real-time sync."""
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"
    PRESENCE_CHANGED = "presence_changed"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"

class GlobalStateSyncer:
    """
    Synchronizes state across all Butler nodes using Redis Pub/Sub.
    Allows nodes to broadcast 'state_update' events and registered handlers to react.
    """
    def __init__(self, redis: Redis, node_id: Optional[str] = None):
        self._redis = redis
        self._node_id = node_id or str(uuid.uuid4())
        self._channel = "butler:state:sync"
        self._handlers: Dict[str, List[Callable[[Dict[str, Any]], Any]]] = {}
        self._listening_task: Optional[asyncio.Task] = None

    def register_handler(self, topic: str, handler: Callable[[Dict[str, Any]], Any]):
        """Register a handler for a specific state topic (e.g., 'user_prefs')."""
        if topic not in self._handlers:
            self._handlers[topic] = []
        self._handlers[topic].append(handler)

    async def broadcast(self, topic: str, payload: Dict[str, Any]):
        """Broadcast a state update to all nodes."""
        message = {
            "source_node": self._node_id,
            "topic": topic,
            "payload": payload
        }
        await self._redis.publish(self._channel, json.dumps(message))

    async def start_listening(self):
        """Start the background listening loop."""
        if self._listening_task:
            return

        self._listening_task = asyncio.create_task(self._listen_loop())
        logger.info("global_state_syncer_started", node_id=self._node_id)

    async def stop_listening(self):
        """Stop the background listening loop."""
        if self._listening_task:
            self._listening_task.cancel()
            try:
                await self._listening_task
            except asyncio.CancelledError:
                pass
            self._listening_task = None

    async def _listen_loop(self):
        """Internal loop to consume sync messages."""
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._channel)
        
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                
                try:
                    data = json.loads(message["data"])
                    if data.get("source_node") == self._node_id:
                        continue # Ignore own broadcasts

                    topic = data.get("topic")
                    payload = data.get("payload")
                    
                    if topic in self._handlers:
                        for handler in self._handlers[topic]:
                            try:
                                if asyncio.iscoroutinefunction(handler):
                                    await handler(payload)
                                else:
                                    handler(payload)
                            except Exception as e:
                                logger.error("state_handler_failed", topic=topic, error=str(e))
                except Exception as e:
                    logger.error("state_sync_parse_error", error=str(e))
        finally:
            await pubsub.unsubscribe(self._channel)
            await pubsub.close()
