from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)

type JsonDict = dict[str, Any]
type StateHandler = Callable[[JsonDict], Any] | Callable[[JsonDict], Awaitable[Any]]


class StateType(StrEnum):
    """State event types for real-time sync."""

    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"
    PRESENCE_CHANGED = "presence_changed"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    NODE_OFFLINE = "NODE_OFFLINE"


class GlobalStateSyncer:
    """Cluster-wide state synchronization over Redis Pub/Sub.

    Design goals:
    - fire-and-forget cluster broadcasts
    - structured message envelope
    - background listener with graceful lifecycle
    - handler isolation so one bad consumer does not poison the loop
    - bounded Redis and handler waits
    - compatibility with existing Butler call sites
    """

    def __init__(
        self,
        redis: Redis,
        node_id: str | None = None,
        *,
        channel: str = "butler:state:sync",
        redis_timeout_seconds: float = 5.0,
        handler_timeout_seconds: float = 10.0,
        max_concurrent_handler_tasks: int = 100,
    ) -> None:
        self._redis = redis
        self._node_id = node_id or str(uuid.uuid4())
        self._channel = channel

        self._redis_timeout_seconds = redis_timeout_seconds
        self._handler_timeout_seconds = handler_timeout_seconds
        self._max_concurrent_handler_tasks = max_concurrent_handler_tasks

        self._handlers: dict[str, list[StateHandler]] = defaultdict(list)
        self._listening_task: asyncio.Task[None] | None = None
        self._is_running = False
        self._pubsub: Any | None = None

        self._handler_tasks: set[asyncio.Task[Any]] = set()
        self._handler_semaphore = asyncio.Semaphore(self._max_concurrent_handler_tasks)

    @property
    def node_id(self) -> str:
        return self._node_id

    def register_handler(self, topic: str | StateType, handler: StateHandler) -> None:
        """Register a handler for a topic.

        Duplicate registrations of the same callable for the same topic are ignored.
        """
        normalized_topic = self._normalize_topic(topic)

        existing = self._handlers[normalized_topic]
        if any(registered is handler for registered in existing):
            logger.debug(
                "global_state_syncer_handler_already_registered",
                node_id=self._node_id,
                topic=normalized_topic,
                handler=repr(handler),
            )
            return

        existing.append(handler)
        logger.debug(
            "global_state_syncer_handler_registered",
            node_id=self._node_id,
            topic=normalized_topic,
            handler_count=len(existing),
        )

    def unregister_handler(self, topic: str | StateType, handler: StateHandler) -> bool:
        """Unregister a previously registered handler."""
        normalized_topic = self._normalize_topic(topic)
        handlers = self._handlers.get(normalized_topic)
        if not handlers:
            return False

        original_len = len(handlers)
        handlers[:] = [registered for registered in handlers if registered is not handler]

        if not handlers:
            self._handlers.pop(normalized_topic, None)

        removed = len(handlers) != original_len
        if removed:
            logger.debug(
                "global_state_syncer_handler_unregistered",
                node_id=self._node_id,
                topic=normalized_topic,
                handler_count=len(handlers),
            )
        return removed

    async def broadcast(self, topic: str | StateType, payload: JsonDict) -> int:
        """Broadcast a state update to all nodes.

        Returns the Redis publish receiver count when available.
        """
        normalized_topic = self._normalize_topic(topic)
        message = self._build_message(normalized_topic, payload)

        receiver_count = await asyncio.wait_for(
            self._redis.publish(self._channel, json.dumps(message, separators=(",", ":"))),
            timeout=self._redis_timeout_seconds,
        )

        logger.debug(
            "global_state_syncer_broadcast",
            node_id=self._node_id,
            topic=normalized_topic,
            receiver_count=int(receiver_count),
            event_id=message["event_id"],
        )
        return int(receiver_count)

    async def broadcast_global_event(self, topic: str | StateType, payload: JsonDict) -> int:
        """Compatibility wrapper for existing Butler call sites."""
        return await self.broadcast(topic, payload)

    async def start_listening(self) -> None:
        """Start the background listening loop."""
        if self._listening_task is not None and not self._listening_task.done():
            logger.debug("global_state_syncer_already_listening", node_id=self._node_id)
            return

        self._is_running = True
        self._listening_task = asyncio.create_task(
            self._listen_loop(),
            name=f"global-state-syncer:{self._node_id}",
        )
        logger.info("global_state_syncer_started", node_id=self._node_id, channel=self._channel)

    async def stop_listening(self) -> None:
        """Stop the background listening loop and wait for handler tasks to drain."""
        self._is_running = False

        if self._listening_task is not None:
            self._listening_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listening_task
            self._listening_task = None

        if self._pubsub is not None:
            await self._close_pubsub(self._pubsub)
            self._pubsub = None

        if self._handler_tasks:
            tasks = list(self._handler_tasks)
            for task in tasks:
                task.cancel()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                    logger.warning(
                        "global_state_syncer_handler_task_shutdown_error",
                        node_id=self._node_id,
                        error=str(result),
                    )
            self._handler_tasks.clear()

        logger.info("global_state_syncer_stopped", node_id=self._node_id)

    async def _listen_loop(self) -> None:
        """Consume sync messages from Redis Pub/Sub."""
        pubsub = self._redis.pubsub()
        self._pubsub = pubsub

        try:
            await asyncio.wait_for(
                pubsub.subscribe(self._channel),
                timeout=self._redis_timeout_seconds,
            )

            while self._is_running:
                try:
                    raw_message = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=False, timeout=1.0),
                        timeout=self._redis_timeout_seconds + 1.0,
                    )
                except TimeoutError:
                    continue

                if raw_message is None:
                    continue

                message_type = raw_message.get("type")
                if message_type != "message":
                    continue

                try:
                    envelope = self._decode_message(raw_message)
                except Exception as exc:
                    logger.error(
                        "state_sync_parse_error",
                        node_id=self._node_id,
                        error=str(exc),
                    )
                    continue

                if envelope["source_node"] == self._node_id:
                    continue

                topic = envelope["topic"]
                payload = envelope["payload"]
                event_id = envelope["event_id"]

                handlers = list(self._handlers.get(topic, []))
                if not handlers:
                    logger.debug(
                        "state_sync_no_handlers",
                        node_id=self._node_id,
                        topic=topic,
                        event_id=event_id,
                    )
                    continue

                for handler in handlers:
                    task = asyncio.create_task(
                        self._run_handler(
                            topic=topic,
                            payload=payload,
                            handler=handler,
                            event_id=event_id,
                        ),
                        name=f"state-handler:{topic}:{self._node_id}",
                    )
                    self._handler_tasks.add(task)
                    task.add_done_callback(self._handler_tasks.discard)

        except asyncio.CancelledError:
            logger.debug("global_state_syncer_listener_cancelled", node_id=self._node_id)
            raise
        except Exception as exc:
            logger.exception(
                "global_state_syncer_listener_failed",
                node_id=self._node_id,
                error=str(exc),
            )
            raise
        finally:
            await self._close_pubsub(pubsub)
            if self._pubsub is pubsub:
                self._pubsub = None

    async def _run_handler(
        self,
        *,
        topic: str,
        payload: JsonDict,
        handler: StateHandler,
        event_id: str,
    ) -> None:
        """Run one handler in isolation with timeout and concurrency control."""
        async with self._handler_semaphore:
            try:
                result = handler(payload)
                if asyncio.iscoroutine(result):
                    await asyncio.wait_for(result, timeout=self._handler_timeout_seconds)
                else:
                    # sync handler, already executed
                    pass

                logger.debug(
                    "state_handler_completed",
                    node_id=self._node_id,
                    topic=topic,
                    event_id=event_id,
                    handler=repr(handler),
                )

            except asyncio.CancelledError:
                logger.debug(
                    "state_handler_cancelled",
                    node_id=self._node_id,
                    topic=topic,
                    event_id=event_id,
                    handler=repr(handler),
                )
                raise
            except TimeoutError:
                logger.error(
                    "state_handler_timed_out",
                    node_id=self._node_id,
                    topic=topic,
                    event_id=event_id,
                    handler=repr(handler),
                    timeout_seconds=self._handler_timeout_seconds,
                )
            except Exception as exc:
                logger.error(
                    "state_handler_failed",
                    node_id=self._node_id,
                    topic=topic,
                    event_id=event_id,
                    handler=repr(handler),
                    error=str(exc),
                )

    def _build_message(self, topic: str, payload: JsonDict) -> JsonDict:
        now = time.time()
        return {
            "event_id": str(uuid.uuid4()),
            "source_node": self._node_id,
            "topic": topic,
            "payload": dict(payload or {}),
            "published_at": now,
            "schema_version": "1.0",
        }

    def _decode_message(self, raw_message: JsonDict) -> JsonDict:
        raw_data = raw_message.get("data")
        if isinstance(raw_data, bytes):
            decoded = raw_data.decode("utf-8")
        elif isinstance(raw_data, str):
            decoded = raw_data
        else:
            raise TypeError(f"Unexpected pubsub data type: {type(raw_data)!r}")

        parsed = json.loads(decoded)
        if not isinstance(parsed, dict):
            raise ValueError("Pub/Sub message must decode to a JSON object")

        source_node = parsed.get("source_node")
        topic = parsed.get("topic")
        payload = parsed.get("payload")
        event_id = parsed.get("event_id") or str(uuid.uuid4())

        if not isinstance(source_node, str) or not source_node.strip():
            raise ValueError("Invalid source_node in sync message")
        if not isinstance(topic, str) or not topic.strip():
            raise ValueError("Invalid topic in sync message")
        if not isinstance(payload, dict):
            raise ValueError("Invalid payload in sync message")

        return {
            "event_id": str(event_id),
            "source_node": source_node.strip(),
            "topic": topic.strip(),
            "payload": payload,
            "published_at": parsed.get("published_at"),
            "schema_version": parsed.get("schema_version"),
        }

    def _normalize_topic(self, topic: str | StateType) -> str:
        if isinstance(topic, StateType):
            return topic.value

        normalized = str(topic).strip()
        if not normalized:
            raise ValueError("topic must not be empty")
        return normalized

    async def _close_pubsub(self, pubsub: Any) -> None:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(
                pubsub.unsubscribe(self._channel),
                timeout=self._redis_timeout_seconds,
            )
        with contextlib.suppress(Exception):
            await asyncio.wait_for(
                pubsub.close(),
                timeout=self._redis_timeout_seconds,
            )
