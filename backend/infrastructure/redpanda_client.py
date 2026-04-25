"""
Redpanda (Kafka-compatible) client for Butler production queue infrastructure.

Production-grade event streaming with:
- Tenant-aware partitioning
- Durable message delivery
- Dead letter queues
- Exactly-once semantics support
"""

import json
from typing import Any

import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaError
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)


class RedpandaClient:
    """Redpanda client wrapper for production queue infrastructure."""

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        redis: Redis | None = None,
    ):
        """
        Initialize Redpanda client.

        Args:
            bootstrap_servers: Redpanda bootstrap servers
            redis: Optional Redis client for caching
        """
        self._bootstrap_servers = bootstrap_servers
        self._redis = redis
        self._producer: AIOKafkaProducer | None = None
        self._consumer: AIOKafkaConsumer | None = None

    async def get_producer(self) -> AIOKafkaProducer:
        """Get or create Kafka producer."""
        if self._producer is None:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks="all",  # Wait for all replicas
                retries=3,
                max_in_flight_requests_per_connection=1,
                enable_idempotence=True,  # Exactly-once semantics
                compression_type="gzip",
            )
            await self._producer.start()
            logger.info("redpanda_producer_started", bootstrap_servers=self._bootstrap_servers)
        return self._producer

    async def get_consumer(
        self,
        topic: str,
        group_id: str,
        tenant_id: str | None = None,
    ) -> AIOKafkaConsumer:
        """
        Get or create Kafka consumer for a topic.

        Args:
            topic: Topic to consume from
            group_id: Consumer group ID
            tenant_id: Optional tenant ID for tenant-aware consumption

        Returns:
            Kafka consumer instance
        """
        if self._consumer is None:
            # Tenant-aware partition assignment if tenant_id provided
            if tenant_id:
                # In production, this would use tenant-specific partition assignment
                # For now, we'll use a simple strategy
                partition_strategy = f"tenant:{tenant_id}"
            else:
                partition_strategy = "roundrobin"

            self._consumer = AIOKafkaConsumer(
                topic,
                bootstrap_servers=self._bootstrap_servers,
                group_id=group_id,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                key_deserializer=lambda k: k.decode("utf-8") if k else None,
                auto_offset_reset="latest",
                enable_auto_commit=False,  # Manual commit for exactly-once
                max_poll_records=100,
                session_timeout_ms=30000,
                heartbeat_interval_ms=3000,
            )
            await self._consumer.start()
            logger.info(
                "redpanda_consumer_started",
                topic=topic,
                group_id=group_id,
                tenant_id=tenant_id,
                partition_strategy=partition_strategy,
            )
        return self._consumer

    async def publish(
        self,
        topic: str,
        value: dict[str, Any],
        key: str | None = None,
        tenant_id: str | None = None,
    ) -> None:
        """
        Publish a message to a topic.

        Args:
            topic: Topic to publish to
            value: Message value (dict)
            key: Optional message key for partitioning
            tenant_id: Optional tenant ID for tenant-aware partitioning
        """
        try:
            producer = await self.get_producer()

            # Use tenant_id as key for tenant-aware partitioning if no key provided
            if key is None and tenant_id:
                key = tenant_id

            # Add tenant_id to message metadata
            if tenant_id:
                value["_tenant_id"] = tenant_id

            await producer.send_and_wait(topic, value=value, key=key)

            logger.debug(
                "message_published",
                topic=topic,
                key=key,
                tenant_id=tenant_id,
            )

        except KafkaError as e:
            logger.exception(
                "message_publish_failed",
                topic=topic,
                key=key,
                tenant_id=tenant_id,
                error=str(e),
            )
            raise

    async def consume(
        self,
        topic: str,
        group_id: str,
        callback,
        tenant_id: str | None = None,
    ) -> None:
        """
        Consume messages from a topic with a callback.

        Args:
            topic: Topic to consume from
            group_id: Consumer group ID
            callback: Async callback function to handle messages
            tenant_id: Optional tenant ID for tenant-aware consumption
        """
        try:
            consumer = await self.get_consumer(topic, group_id, tenant_id)

            async for message in consumer:
                try:
                    # Extract tenant_id from message metadata
                    message_tenant_id = message.value.get("_tenant_id")

                    # Skip if tenant_id provided and doesn't match
                    if tenant_id and message_tenant_id != tenant_id:
                        logger.debug(
                            "message_skipped_tenant_mismatch",
                            message_tenant_id=message_tenant_id,
                            expected_tenant_id=tenant_id,
                        )
                        await consumer.commit()
                        continue

                    # Call callback
                    await callback(message)

                    # Commit offset after successful processing
                    await consumer.commit()

                except Exception as e:
                    logger.exception(
                        "message_processing_failed",
                        topic=topic,
                        partition=message.partition,
                        offset=message.offset,
                        error=str(e),
                    )
                    # Send to dead letter queue on failure
                    await self._send_to_dlq(topic, message, str(e))

        except KafkaError as e:
            logger.exception(
                "consumer_error",
                topic=topic,
                group_id=group_id,
                tenant_id=tenant_id,
                error=str(e),
            )
            raise

    async def _send_to_dlq(self, original_topic: str, message, error: str) -> None:
        """Send failed message to dead letter queue."""
        dlq_topic = f"{original_topic}-dlq"
        dlq_value = {
            "original_topic": original_topic,
            "original_message": message.value,
            "error": error,
            "timestamp": message.timestamp,
        }
        await self.publish(dlq_topic, dlq_value, key=message.key)
        logger.warning(
            "message_sent_to_dlq",
            original_topic=original_topic,
            dlq_topic=dlq_topic,
        )

    async def close(self) -> None:
        """Close producer and consumer connections."""
        if self._producer:
            await self._producer.stop()
            self._producer = None
            logger.info("redpanda_producer_stopped")

        if self._consumer:
            await self._consumer.stop()
            self._consumer = None
            logger.info("redpanda_consumer_stopped")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


class QueueTopology:
    """Manage queue topology for Butler."""

    # Core topics
    WORKFLOW_EVENTS = "butler.workflow.events"
    TOOL_EXECUTIONS = "butler.tool.executions"
    AUDIT_EVENTS = "butler.audit.events"
    BILLING_EVENTS = "butler.billing.events"
    MEMORY_COMPACTION = "butler.memory.compaction"
    REALTIME_DELIVERY = "butler.realtime.delivery"

    # Dead letter queues
    WORKFLOW_DLQ = f"{WORKFLOW_EVENTS}-dlq"
    TOOL_EXECUTIONS_DLQ = f"{TOOL_EXECUTIONS}-dlq"
    AUDIT_DLQ = f"{AUDIT_EVENTS}-dlq"

    @classmethod
    def get_all_topics(cls) -> list[str]:
        """Get all Butler topics."""
        return [
            cls.WORKFLOW_EVENTS,
            cls.TOOL_EXECUTIONS,
            cls.AUDIT_EVENTS,
            cls.BILLING_EVENTS,
            cls.MEMORY_COMPACTION,
            cls.REALTIME_DELIVERY,
            cls.WORKFLOW_DLQ,
            cls.TOOL_EXECUTIONS_DLQ,
            cls.AUDIT_DLQ,
        ]


class PartitionStrategy:
    """Partition strategy for tenant-aware queue partitioning."""

    @staticmethod
    def get_partition(tenant_id: str, num_partitions: int) -> int:
        """
        Get partition for a tenant using consistent hashing.

        Args:
            tenant_id: Tenant ID
            num_partitions: Number of partitions

        Returns:
            Partition number
        """
        # Simple hash-based partitioning
        hash_value = hash(tenant_id)
        return abs(hash_value) % num_partitions

    @staticmethod
    def get_partition_key(tenant_id: str, resource_type: str) -> str:
        """
        Get partition key for tenant and resource type.

        Args:
            tenant_id: Tenant ID
            resource_type: Type of resource (workflow, tool, etc.)

        Returns:
            Partition key
        """
        return f"{tenant_id}:{resource_type}"
