"""
Consumer Group Manager - Production Consumer Group Management

Manages Kafka consumer groups for Butler production queues.
Handles consumer group lifecycle, offset management, and health monitoring.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError
from redis.asyncio import Redis

from infrastructure.redpanda_client import RedpandaClient
from services.queues.redpanda_topology import PRODUCTION_CONSUMER_GROUPS

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ConsumerGroupHealth:
    """Health status of a consumer group."""

    group_id: str
    topic: str
    active_consumers: int
    lag: int  # Messages lagging
    status: str  # "healthy", "lagging", "dead"
    last_seen: datetime


@dataclass(frozen=True, slots=True)
class ConsumerMetrics:
    """Metrics for a consumer."""

    consumer_id: str
    group_id: str
    topic: str
    partition: int
    records_consumed: int
    records_lag: int
    current_offset: int
    last_commit_time: datetime


class ConsumerGroupManager:
    """
    Manage Kafka consumer groups for production queues.

    Handles consumer group lifecycle, offset management, and health monitoring.
    """

    def __init__(
        self,
        redpanda_client: RedpandaClient,
        redis: Redis | None = None,
    ) -> None:
        """Initialize consumer group manager."""
        self._redpanda = redpanda_client
        self._redis = redis
        self._active_consumers: dict[str, AIOKafkaConsumer] = {}
        self._health_cache: dict[str, ConsumerGroupHealth] = {}

    def _health_key(self, group_id: str) -> str:
        """Generate Redis key for consumer group health using TenantNamespace."""
        # Consumer group health is infrastructure-level, not tenant-scoped
        # These are global cluster health keys
        return f"consumer_group:health:{group_id}"

    async def start_consumer(
        self,
        group_id: str,
        callback,
        tenant_id: str | None = None,
    ) -> None:
        """
        Start a consumer for a specific group.

        Args:
            group_id: Consumer group ID
            callback: Async callback function to handle messages
            tenant_id: Optional tenant ID for tenant-aware consumption
        """
        if group_id in self._active_consumers:
            logger.warning(
                "consumer_already_active",
                group_id=group_id,
            )
            return

        config = PRODUCTION_CONSUMER_GROUPS.get(group_id)
        if not config:
            logger.error(
                "consumer_group_config_not_found",
                group_id=group_id,
            )
            raise ValueError(f"Consumer group config not found: {group_id}")

        try:
            # Start consuming
            await self._redpanda.consume(
                topic=config.topic,
                group_id=group_id,
                callback=callback,
                tenant_id=tenant_id,
            )

            # Mark consumer as active
            self._active_consumers[group_id] = True  # Placeholder

            logger.info(
                "consumer_started",
                group_id=group_id,
                topic=config.topic,
            )

        except KafkaError as e:
            logger.exception(
                "consumer_start_failed",
                group_id=group_id,
                error=str(e),
            )
            raise

    async def stop_consumer(self, group_id: str) -> None:
        """
        Stop a consumer for a specific group.

        Args:
            group_id: Consumer group ID
        """
        if group_id not in self._active_consumers:
            logger.warning(
                "consumer_not_active",
                group_id=group_id,
            )
            return

        try:
            # Stop consuming (handled by redpanda client)
            del self._active_consumers[group_id]

            logger.info(
                "consumer_stopped",
                group_id=group_id,
            )

        except Exception as e:
            logger.exception(
                "consumer_stop_failed",
                group_id=group_id,
                error=str(e),
            )

    async def get_consumer_group_health(
        self,
        group_id: str,
    ) -> ConsumerGroupHealth:
        """
        Get health status of a consumer group.

        Args:
            group_id: Consumer group ID

        Returns:
            Consumer group health status
        """
        # Check cache first
        if group_id in self._health_cache:
            cached = self._health_cache[group_id]
            # Cache for 30 seconds
            if datetime.now() - cached.last_seen < timedelta(seconds=30):
                return cached

        config = PRODUCTION_CONSUMER_GROUPS.get(group_id)
        if not config:
            logger.error(
                "consumer_group_config_not_found",
                group_id=group_id,
            )
            raise ValueError(f"Consumer group config not found: {group_id}")

        # Check Redis for health status
        if self._redis:
            health_data = await self._redis.hgetall(self._health_key(group_id))

            if health_data:
                health = ConsumerGroupHealth(
                    group_id=group_id,
                    topic=config.topic,
                    active_consumers=int(health_data.get(b"active_consumers", b"0")),
                    lag=int(health_data.get(b"lag", b"0")),
                    status=health_data.get(b"status", b"unknown").decode(),
                    last_seen=datetime.fromtimestamp(float(health_data.get(b"last_seen", b"0"))),
                )

                # Update cache
                self._health_cache[group_id] = health
                return health

        # Default health if no data
        health = ConsumerGroupHealth(
            group_id=group_id,
            topic=config.topic,
            active_consumers=1 if group_id in self._active_consumers else 0,
            lag=0,
            status="healthy" if group_id in self._active_consumers else "dead",
            last_seen=datetime.now(),
        )

        self._health_cache[group_id] = health
        return health

    async def update_consumer_group_health(
        self,
        group_id: str,
        active_consumers: int,
        lag: int,
        status: str,
    ) -> None:
        """
        Update health status of a consumer group.

        Args:
            group_id: Consumer group ID
            active_consumers: Number of active consumers
            lag: Consumer lag (messages)
            status: Health status
        """
        if self._redis:
            await self._redis.hset(
                self._health_key(group_id),
                mapping={
                    "active_consumers": active_consumers,
                    "lag": lag,
                    "status": status,
                    "last_seen": datetime.now().timestamp(),
                },
            )
            await self._redis.expire(self._health_key(group_id), 60)

        # Update cache
        config = PRODUCTION_CONSUMER_GROUPS.get(group_id)
        if config:
            self._health_cache[group_id] = ConsumerGroupHealth(
                group_id=group_id,
                topic=config.topic,
                active_consumers=active_consumers,
                lag=lag,
                status=status,
                last_seen=datetime.now(),
            )

    async def get_all_consumer_group_health(self) -> dict[str, ConsumerGroupHealth]:
        """
        Get health status of all consumer groups.

        Returns:
            Dictionary mapping group ID to health status
        """
        health_status = {}

        for group_id in PRODUCTION_CONSUMER_GROUPS:
            health = await self.get_consumer_group_health(group_id)
            health_status[group_id] = health

        return health_status

    async def reset_consumer_group_offset(
        self,
        group_id: str,
        topic: str,
        partition: int | None = None,
        offset: int | None = None,
    ) -> None:
        """
        Reset consumer group offset.

        Args:
            group_id: Consumer group ID
            topic: Topic name
            partition: Partition to reset (None for all)
            offset: Offset to reset to (None for earliest)
        """
        from aiokafka.admin import AIOKafkaAdminClient

        admin_client = AIOKafkaAdminClient(
            bootstrap_servers=self._redpanda._bootstrap_servers,
        )
        await admin_client.start()

        try:
            topic_partitions = {topic: []}

            if partition is not None:
                topic_partitions[topic].append(partition)
            else:
                # All partitions
                topic_partitions[topic] = None

            if offset is None:
                # Reset to earliest
                await admin_client.alter_consumer_group_offsets(
                    group_id=group_id,
                    offsets={},
                )
            else:
                # Reset to specific offset
                offsets = {topic: {partition: offset}}
                await admin_client.alter_consumer_group_offsets(
                    group_id=group_id,
                    offsets=offsets,
                )

            logger.info(
                "consumer_group_offset_reset",
                group_id=group_id,
                topic=topic,
                partition=partition,
                offset=offset,
            )

        finally:
            await admin_client.close()

    async def delete_consumer_group(self, group_id: str) -> None:
        """
        Delete a consumer group.

        Args:
            group_id: Consumer group ID
        """
        from aiokafka.admin import AIOKafkaAdminClient

        admin_client = AIOKafkaAdminClient(
            bootstrap_servers=self._redpanda._bootstrap_servers,
        )
        await admin_client.start()

        try:
            await admin_client.delete_consumer_groups([group_id])

            # Stop consumer if active
            if group_id in self._active_consumers:
                await self.stop_consumer(group_id)

            # Clear cache
            if group_id in self._health_cache:
                del self._health_cache[group_id]

            # Clear Redis
            if self._redis:
                await self._redis.delete(self._health_key(group_id))

            logger.info(
                "consumer_group_deleted",
                group_id=group_id,
            )

        finally:
            await admin_client.close()

    async def monitor_consumer_groups(
        self,
        interval_seconds: int = 30,
    ) -> None:
        """
        Continuously monitor consumer group health.

        Args:
            interval_seconds: Monitoring interval
        """
        while True:
            try:
                health_status = await self.get_all_consumer_group_health()

                # Log unhealthy groups
                for group_id, health in health_status.items():
                    if health.status != "healthy":
                        logger.warning(
                            "consumer_group_unhealthy",
                            group_id=group_id,
                            status=health.status,
                            lag=health.lag,
                            active_consumers=health.active_consumers,
                        )

                await asyncio.sleep(interval_seconds)

            except Exception as e:
                logger.exception(
                    "consumer_group_monitoring_error",
                    error=str(e),
                )
                await asyncio.sleep(interval_seconds)

    async def get_consumer_metrics(
        self,
        group_id: str,
    ) -> list[ConsumerMetrics]:
        """
        Get detailed metrics for a consumer group.

        Args:
            group_id: Consumer group ID

        Returns:
            List of consumer metrics
        """
        # This would require querying Kafka admin client for consumer details
        # For now, return empty list
        return []
