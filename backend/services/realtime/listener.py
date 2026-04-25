"""RealtimePubSubListener — Phase 9 Scalability.

Handles the background Redis Pub/Sub subscription for the local node.
Works in tandem with ConnectionManager to ensure high-performance
distributed event fan-out.
"""

import asyncio
import contextlib
import json

import structlog
from redis.asyncio import Redis

from .manager import ConnectionManager

logger = structlog.get_logger(__name__)


class RealtimePubSubListener:
    """
    Background worker that listens to Redis Pub/Sub for realtime events.
    Uses dynamic subscription to only listen for channels relevant to local connections.
    """

    def __init__(self, redis: Redis, manager: ConnectionManager):
        self._redis = redis
        self._manager = manager
        self._pubsub = redis.pubsub()
        self._running = False
        self._task: asyncio.Task | None = None
        self._pubsub_prefix = "butler:pubsub:acct:"

    async def start(self):
        """Start the background pubsub loop."""
        if self._running:
            return

        self._running = True
        # Subscribe to a dummy channel to initialize the pubsub connection
        await self._pubsub.subscribe("butler:internal:wakeup")
        self._task = asyncio.create_task(self._loop())
        logger.info("realtime_pubsub_listener_started")

    async def stop(self):
        """Clean shutdown of the listener."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

        await self._pubsub.aclose()
        logger.info("realtime_pubsub_listener_stopped")

    async def subscribe_account(self, account_id: str):
        """Dynamically subscribe to an account's event channel."""
        channel = f"{self._pubsub_prefix}{account_id}"
        await self._pubsub.subscribe(channel)
        logger.debug("realtime_subscribed_to_account", account_id=account_id)

    async def unsubscribe_account(self, account_id: str):
        """Unsubscribe when client disconnects."""
        channel = f"{self._pubsub_prefix}{account_id}"
        await self._pubsub.unsubscribe(channel)
        logger.debug("realtime_unsubscribed_from_account", account_id=account_id)

    async def _loop(self):
        """Main event loop for processing Pub/Sub messages."""
        while self._running:
            try:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message is not None:
                    # message['channel'] = b'butler:pubsub:acct:auth0|...'
                    channel_name = message["channel"].decode()
                    account_id = channel_name.replace(self._pubsub_prefix, "")

                    data = json.loads(message["data"])

                    # Dispatch to local WS if it exists on THIS node
                    await self._manager.dispatch_local(account_id, data)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("pubsub_listener_error", error=str(e))
                await asyncio.sleep(1)  # simple backoff
