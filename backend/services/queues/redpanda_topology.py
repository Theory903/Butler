"""
Redpanda Topic Topology - Production Queue Infrastructure

Defines and manages Redpanda topic topology for Butler.
Creates topics, partitions, and consumer groups for production event streaming.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import structlog

from infrastructure.redpanda_client import QueueTopology

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class TopicConfig:
    """Configuration for a Redpanda topic."""

    name: str
    partitions: int
    replication_factor: int
    retention_ms: int
    cleanup_policy: str  # "delete" or "compact"
    min_insync_replicas: int
    enable_idempotence: bool


# Production topic configurations
PRODUCTION_TOPICS: dict[str, TopicConfig] = {
    QueueTopology.WORKFLOW_EVENTS: TopicConfig(
        name=QueueTopology.WORKFLOW_EVENTS,
        partitions=12,  # Scale for high throughput
        replication_factor=3,  # Production durability
        retention_ms=86400000,  # 24 hours
        cleanup_policy="delete",
        min_insync_replicas=2,
        enable_idempotence=True,
    ),
    QueueTopology.TOOL_EXECUTIONS: TopicConfig(
        name=QueueTopology.TOOL_EXECUTIONS,
        partitions=24,  # Higher partition count for tool executions
        replication_factor=3,
        retention_ms=604800000,  # 7 days
        cleanup_policy="delete",
        min_insync_replicas=2,
        enable_idempotence=True,
    ),
    QueueTopology.AUDIT_EVENTS: TopicConfig(
        name=QueueTopology.AUDIT_EVENTS,
        partitions=6,
        replication_factor=3,
        retention_ms=2592000000,  # 30 days
        cleanup_policy="delete",
        min_insync_replicas=2,
        enable_idempotence=False,  # Audit events don't need idempotence
    ),
    QueueTopology.BILLING_EVENTS: TopicConfig(
        name=QueueTopology.BILLING_EVENTS,
        partitions=6,
        replication_factor=3,
        retention_ms=2592000000,  # 30 days
        cleanup_policy="compact",  # Compaction for billing deduplication
        min_insync_replicas=2,
        enable_idempotence=True,
    ),
    QueueTopology.MEMORY_COMPACTION: TopicConfig(
        name=QueueTopology.MEMORY_COMPACTION,
        partitions=12,
        replication_factor=3,
        retention_ms=86400000,  # 24 hours
        cleanup_policy="delete",
        min_insync_replicas=2,
        enable_idempotence=True,
    ),
    QueueTopology.REALTIME_DELIVERY: TopicConfig(
        name=QueueTopology.REALTIME_DELIVERY,
        partitions=24,  # High partition count for low latency
        replication_factor=2,  # Lower replication for latency
        retention_ms=300000,  # 5 minutes
        cleanup_policy="delete",
        min_insync_replicas=1,
        enable_idempotence=True,
    ),
    # Dead letter queues
    QueueTopology.WORKFLOW_DLQ: TopicConfig(
        name=QueueTopology.WORKFLOW_DLQ,
        partitions=6,
        replication_factor=3,
        retention_ms=604800000,  # 7 days
        cleanup_policy="delete",
        min_insync_replicas=2,
        enable_idempotence=False,
    ),
    QueueTopology.TOOL_EXECUTIONS_DLQ: TopicConfig(
        name=QueueTopology.TOOL_EXECUTIONS_DLQ,
        partitions=6,
        replication_factor=3,
        retention_ms=604800000,  # 7 days
        cleanup_policy="delete",
        min_insync_replicas=2,
        enable_idempotence=False,
    ),
    QueueTopology.AUDIT_DLQ: TopicConfig(
        name=QueueTopology.AUDIT_DLQ,
        partitions=3,
        replication_factor=3,
        retention_ms=2592000000,  # 30 days
        cleanup_policy="delete",
        min_insync_replicas=2,
        enable_idempotence=False,
    ),
}


@dataclass(frozen=True, slots=True)
class ConsumerGroupConfig:
    """Configuration for a consumer group."""

    group_id: str
    topic: str
    auto_offset_reset: str = "latest"
    enable_auto_commit: bool = False
    max_poll_records: int = 100
    session_timeout_ms: int = 30000
    heartbeat_interval_ms: int = 3000


# Production consumer group configurations
PRODUCTION_CONSUMER_GROUPS: dict[str, ConsumerGroupConfig] = {
    "workflow-processor": ConsumerGroupConfig(
        group_id="workflow-processor",
        topic=QueueTopology.WORKFLOW_EVENTS,
        auto_offset_reset="latest",
        enable_auto_commit=False,
        max_poll_records=100,
        session_timeout_ms=30000,
        heartbeat_interval_ms=3000,
    ),
    "tool-executor": ConsumerGroupConfig(
        group_id="tool-executor",
        topic=QueueTopology.TOOL_EXECUTIONS,
        auto_offset_reset="latest",
        enable_auto_commit=False,
        max_poll_records=50,
        session_timeout_ms=30000,
        heartbeat_interval_ms=3000,
    ),
    "audit-logger": ConsumerGroupConfig(
        group_id="audit-logger",
        topic=QueueTopology.AUDIT_EVENTS,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        max_poll_records=500,
        session_timeout_ms=60000,
        heartbeat_interval_ms=5000,
    ),
    "billing-aggregator": ConsumerGroupConfig(
        group_id="billing-aggregator",
        topic=QueueTopology.BILLING_EVENTS,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        max_poll_records=200,
        session_timeout_ms=60000,
        heartbeat_interval_ms=5000,
    ),
    "memory-compactor": ConsumerGroupConfig(
        group_id="memory-compactor",
        topic=QueueTopology.MEMORY_COMPACTION,
        auto_offset_reset="latest",
        enable_auto_commit=False,
        max_poll_records=50,
        session_timeout_ms=30000,
        heartbeat_interval_ms=3000,
    ),
    "realtime-delivery": ConsumerGroupConfig(
        group_id="realtime-delivery",
        topic=QueueTopology.REALTIME_DELIVERY,
        auto_offset_reset="latest",
        enable_auto_commit=False,
        max_poll_records=25,
        session_timeout_ms=10000,
        heartbeat_interval_ms=1000,
    ),
}


class RedpandaTopologyManager:
    """
    Manage Redpanda topic topology.

    Creates topics, configures partitions, and sets up consumer groups.
    """

    def __init__(self, bootstrap_servers: str = "localhost:9092"):
        """Initialize topology manager."""
        self._bootstrap_servers = bootstrap_servers
        self._admin_client = None

    def _get_admin_client(self) -> Any:
        """Get or create Kafka admin client."""
        if self._admin_client is None:
            from aiokafka.admin import AIOKafkaAdminClient

            self._admin_client = AIOKafkaAdminClient(
                bootstrap_servers=self._bootstrap_servers,
            )
        return self._admin_client

    async def create_topics(self) -> dict[str, bool]:
        """
        Create all production topics.

        Returns:
            Dictionary mapping topic name to creation success status
        """
        from aiokafka.admin import NewTopic

        admin_client = self._get_admin_client()
        await admin_client.start()

        results = {}

        for topic_name, config in PRODUCTION_TOPICS.items():
            try:
                topic = NewTopic(
                    name=config.name,
                    num_partitions=config.partitions,
                    replication_factor=config.replication_factor,
                    config={
                        "retention.ms": str(config.retention_ms),
                        "cleanup.policy": config.cleanup_policy,
                        "min.insync.replicas": str(config.min_insync_replicas),
                        "message.max.bytes": "10485760",  # 10MB max message size
                    },
                )

                await admin_client.create_topics([topic])
                results[topic_name] = True

                logger.info(
                    "topic_created",
                    topic=topic_name,
                    partitions=config.partitions,
                    replication_factor=config.replication_factor,
                )

            except Exception as e:
                # Topic might already exist
                if "already exists" in str(e):
                    results[topic_name] = True
                    logger.info(
                        "topic_already_exists",
                        topic=topic_name,
                    )
                else:
                    results[topic_name] = False
                    logger.exception(
                        "topic_creation_failed",
                        topic=topic_name,
                        error=str(e),
                    )

        await admin_client.close()
        return results

    async def delete_topics(self, topic_names: list[str]) -> dict[str, bool]:
        """
        Delete specified topics.

        Args:
            topic_names: List of topic names to delete

        Returns:
            Dictionary mapping topic name to deletion success status
        """
        from aiokafka.admin import AIOKafkaAdminClient

        admin_client = AIOKafkaAdminClient(
            bootstrap_servers=self._bootstrap_servers,
        )
        await admin_client.start()

        results = {}

        for topic_name in topic_names:
            try:
                await admin_client.delete_topics([topic_name])
                results[topic_name] = True

                logger.info(
                    "topic_deleted",
                    topic=topic_name,
                )

            except Exception as e:
                results[topic_name] = False
                logger.exception(
                    "topic_deletion_failed",
                    topic=topic_name,
                    error=str(e),
                )

        await admin_client.close()
        return results

    async def list_topics(self) -> list[str]:
        """
        List all topics.

        Returns:
            List of topic names
        """
        from aiokafka.admin import AIOKafkaAdminClient

        admin_client = AIOKafkaAdminClient(
            bootstrap_servers=self._bootstrap_servers,
        )
        await admin_client.start()

        try:
            return await admin_client.list_topics()
        finally:
            await admin_client.close()

    async def get_topic_metadata(self, topic_name: str) -> dict[str, Any]:
        """
        Get metadata for a specific topic.

        Args:
            topic_name: Topic name

        Returns:
            Topic metadata dictionary
        """
        from aiokafka.admin import AIOKafkaAdminClient

        admin_client = AIOKafkaAdminClient(
            bootstrap_servers=self._bootstrap_servers,
        )
        await admin_client.start()

        try:
            return await admin_client.describe_topics([topic_name])
        finally:
            await admin_client.close()

    async def ensure_topology(self) -> dict[str, Any]:
        """
        Ensure production topology exists.

        Creates missing topics and verifies configuration.

        Returns:
            Summary of topology status
        """
        logger.info("ensuring_redpanda_topology")

        # Create topics
        creation_results = await self.create_topics()

        # List current topics
        current_topics = await self.list_topics()

        # Verify production topics exist
        missing_topics = []
        for topic in QueueTopology.get_all_topics():
            if topic not in current_topics:
                missing_topics.append(topic)

        summary = {
            "topics_created": sum(1 for v in creation_results.values() if v),
            "topics_failed": sum(1 for v in creation_results.values() if not v),
            "current_topics": len(current_topics),
            "missing_topics": missing_topics,
            "status": "healthy" if not missing_topics else "incomplete",
        }

        logger.info(
            "topology_ensured",
            **summary,
        )

        return summary


async def main() -> None:
    """Main entry point for topology management."""
    import sys

    bootstrap_servers = sys.argv[1] if len(sys.argv) > 1 else "localhost:9092"
    command = sys.argv[2] if len(sys.argv) > 2 else "ensure"

    manager = RedpandaTopologyManager(bootstrap_servers=bootstrap_servers)

    if command == "ensure":
        await manager.ensure_topology()
    elif command == "create":
        await manager.create_topics()
    elif command == "list":
        topics = await manager.list_topics()
        for _topic in topics:
            pass
    elif command == "delete":
        if len(sys.argv) > 3:
            topics_to_delete = sys.argv[3:]
            await manager.delete_topics(topics_to_delete)
        else:
            pass
    else:
        pass


if __name__ == "__main__":
    asyncio.run(main())
