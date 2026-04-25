import json
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from fastapi import WebSocket
from redis.asyncio import Redis
from starlette.websockets import WebSocketDisconnect

from core.state_sync import GlobalStateSyncer, StateType

from .events import RealtimeEvent
from .presence import PresenceService

if TYPE_CHECKING:
    from .listener import RealtimePubSubListener

logger = structlog.get_logger(__name__)


class ConnectionManager:
    """WebSocket connection lifecycle management with Distributed PubSub."""

    def __init__(
        self, redis: Redis, presence: PresenceService, syncer: GlobalStateSyncer | None = None
    ):
        self._local_connections: dict[str, WebSocket] = {}  # account_id → local websocket
        self._redis = redis
        self._presence = presence
        self._syncer = syncer
        self._node_id = os.getenv("BUTLER_NODE_ID", "gateway-local")
        self._pubsub_prefix = "butler:pubsub:acct:"
        self._listener: RealtimePubSubListener | None = None

    def set_listener(self, listener: "RealtimePubSubListener"):
        """Setter to avoid circular DI during init."""
        self._listener = listener

    async def connect(self, websocket: WebSocket, account_id: str, session_id: str):
        """Accept connection and register locally + update global presence with pipelining."""
        await websocket.accept()
        self._local_connections[account_id] = websocket

        # 1. Update presence in a single round-trip
        now = datetime.now(UTC).isoformat()
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hset(
                f"presence:{account_id}",
                mapping={
                    "status": "connected",
                    "session_id": session_id,
                    "connected_at": now,
                    "node_id": self._node_id,
                    "device_id": websocket.headers.get("X-Device-ID", "unknown"),
                },
            )
            pipe.sadd(f"butler:presence:nodes:{self._node_id}", account_id)
            pipe.expire(f"presence:{account_id}", 3600)
            await pipe.execute()

        # 2. Broadcast Node Assignment (Oracle-Grade Scaling)
        if self._syncer:
            await self._syncer.broadcast_node_assignment(account_id, self._node_id)
            await self._syncer.broadcast_state_change(
                state_type=StateType.SESSION_STARTED,
                account_id=account_id,
                payload={"session_id": session_id, "node_id": self._node_id},
            )

        # 3. Dynamic PubSub Subscription (Distributed Routing)
        if self._listener:
            await self._listener.subscribe_account(account_id)

    async def disconnect(self, account_id: str):
        """Remove connection locally and update global presence."""
        self._local_connections.pop(account_id, None)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hset(f"presence:{account_id}", key="status", value="disconnected")
            pipe.srem(f"butler:presence:nodes:{self._node_id}", account_id)
            await pipe.execute()

        # 2. Broadcast Disconnect
        if self._syncer:
            await self._syncer.broadcast_state_change(
                state_type=StateType.PRESENCE_CHANGED,
                account_id=account_id,
                payload={"status": "disconnected", "node_id": self._node_id},
            )

        # 3. Dynamic PubSub Unsubscription
        if self._listener:
            await self._listener.unsubscribe_account(account_id)

    async def send_event(self, account_id: str, event: RealtimeEvent):
        """
        Send event via Global PubSub Bus with pipelining for durability.
        Any Butler node listening for this account will receive and dispatch.
        """
        # 1. Prepare messages
        channel = f"{self._pubsub_prefix}{account_id}"
        event_dict = event.to_dict()
        message = json.dumps(event_dict)

        # 2. Execute Publish + Durable Log in a single pipeline execution
        async with self._redis.pipeline(transaction=False) as pipe:
            pipe.publish(channel, message)

            if event.durable:
                msg = {k: str(v) for k, v in event_dict.items()}
                pipe.xadd(
                    f"events:{account_id}",
                    msg,
                    maxlen=1000,
                )
            await pipe.execute()

    async def dispatch_local(self, account_id: str, event_dict: dict):
        """
        Actual delivery to the physical WebSocket on THIS node.
        Called by the PubSubListener.
        """
        ws = self._local_connections.get(account_id)
        if ws:
            try:
                await ws.send_json(event_dict)
            except WebSocketDisconnect:
                await self.disconnect(account_id)
            except Exception as e:
                logger.error("ws_dispatch_failed", account_id=account_id, error=str(e))

    async def broadcast_to_account(self, account_id: str, event: RealtimeEvent):
        """Broadcast via Global Bus."""
        await self.send_event(account_id, event)
