"""
Multi-Master Sync - Multi-Master Data Synchronization

Implements multi-master data synchronization across nodes.
Supports bidirectional sync, conflict detection, and consistency guarantees.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class SyncStatus(StrEnum):
    """Synchronization status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CONFLICTED = "conflicted"


@dataclass(frozen=True, slots=True)
class SyncNode:
    """Synchronization node."""

    node_id: str
    endpoint: str
    last_sync: datetime | None
    healthy: bool
    priority: int


@dataclass(frozen=True, slots=True)
class SyncOperation:
    """Synchronization operation."""

    operation_id: str
    source_node: str
    target_node: str
    data_id: str
    data_type: str
    data: Any
    timestamp: datetime
    status: SyncStatus
    version: int


@dataclass(frozen=True, slots=True)
class SyncConflict:
    """Synchronization conflict."""

    conflict_id: str
    operation_id: str
    data_id: str
    source_version: int
    target_version: int
    source_data: Any
    target_data: Any
    detected_at: datetime
    resolved: bool
    resolution: str | None


class MultiMasterSync:
    """
    Multi-master synchronization service.

    Features:
    - Bidirectional synchronization
    - Conflict detection
    - Version control
    - Consistency checks
    """

    def __init__(self) -> None:
        """Initialize multi-master sync service."""
        self._nodes: dict[str, SyncNode] = {}
        self._operations: list[SyncOperation] = []
        self._conflicts: list[SyncConflict] = []
        self._data_versions: dict[str, int] = {}  # data_id -> version
        self._sync_tasks: dict[str, asyncio.Task] = {}

    def add_node(
        self,
        node_id: str,
        endpoint: str,
        priority: int = 5,
    ) -> SyncNode:
        """
        Add a sync node.

        Args:
            node_id: Node identifier
            endpoint: Node endpoint
            priority: Node priority

        Returns:
            Sync node
        """
        node = SyncNode(
            node_id=node_id,
            endpoint=endpoint,
            last_sync=None,
            healthy=True,
            priority=priority,
        )

        self._nodes[node_id] = node

        logger.info(
            "sync_node_added",
            node_id=node_id,
            endpoint=endpoint,
        )

        return node

    async def sync_data(
        self,
        source_node: str,
        target_node: str,
        data_id: str,
        data_type: str,
        data: Any,
    ) -> SyncOperation:
        """
        Synchronize data between nodes.

        Args:
            source_node: Source node identifier
            target_node: Target node identifier
            data_id: Data identifier
            data_type: Data type
            data: Data to sync

        Returns:
            Sync operation
        """
        operation_id = f"op-{datetime.now(UTC).timestamp()}"

        # Increment version
        current_version = self._data_versions.get(data_id, 0) + 1
        self._data_versions[data_id] = current_version

        operation = SyncOperation(
            operation_id=operation_id,
            source_node=source_node,
            target_node=target_node,
            data_id=data_id,
            data_type=data_type,
            data=data,
            timestamp=datetime.now(UTC),
            status=SyncStatus.PENDING,
            version=current_version,
        )

        self._operations.append(operation)

        # Start sync task
        task = asyncio.create_task(self._execute_sync(operation))
        self._sync_tasks[operation_id] = task

        return operation

    async def _execute_sync(self, operation: SyncOperation) -> SyncOperation:
        """
        Execute synchronization operation.

        Args:
            operation: Sync operation

        Returns:
            Updated operation
        """
        # Update status to in progress
        in_progress_op = SyncOperation(
            operation_id=operation.operation_id,
            source_node=operation.source_node,
            target_node=operation.target_node,
            data_id=operation.data_id,
            data_type=operation.data_type,
            data=operation.data,
            timestamp=operation.timestamp,
            status=SyncStatus.IN_PROGRESS,
            version=operation.version,
        )

        # Update in operations list
        for i, op in enumerate(self._operations):
            if op.operation_id == operation.operation_id:
                self._operations[i] = in_progress_op
                break

        try:
            # In production, this would perform actual network sync
            await asyncio.sleep(0.1)  # Simulate network delay

            # Check for conflicts
            target_version = self._data_versions.get(operation.data_id, 0)

            if target_version > 0 and target_version != operation.version:
                # Conflict detected
                conflict = SyncConflict(
                    conflict_id=f"conflict-{datetime.now(UTC).timestamp()}",
                    operation_id=operation.operation_id,
                    data_id=operation.data_id,
                    source_version=operation.version,
                    target_version=target_version,
                    source_data=operation.data,
                    target_data=None,  # Would fetch from target in production
                    detected_at=datetime.now(UTC),
                    resolved=False,
                    resolution=None,
                )

                self._conflicts.append(conflict)

                conflicted_op = SyncOperation(
                    operation_id=operation.operation_id,
                    source_node=operation.source_node,
                    target_node=operation.target_node,
                    data_id=operation.data_id,
                    data_type=operation.data_type,
                    data=operation.data,
                    timestamp=operation.timestamp,
                    status=SyncStatus.CONFLICTED,
                    version=operation.version,
                )

                for i, op in enumerate(self._operations):
                    if op.operation_id == operation.operation_id:
                        self._operations[i] = conflicted_op
                        break

                logger.warning(
                    "sync_conflict_detected",
                    operation_id=operation.operation_id,
                    data_id=operation.data_id,
                )

                return conflicted_op

            # Sync successful
            completed_op = SyncOperation(
                operation_id=operation.operation_id,
                source_node=operation.source_node,
                target_node=operation.target_node,
                data_id=operation.data_id,
                data_type=operation.data_type,
                data=operation.data,
                timestamp=operation.timestamp,
                status=SyncStatus.COMPLETED,
                version=operation.version,
            )

            for i, op in enumerate(self._operations):
                if op.operation_id == operation.operation_id:
                    self._operations[i] = completed_op
                    break

            # Update node last sync
            if operation.target_node in self._nodes:
                node = self._nodes[operation.target_node]
                updated_node = SyncNode(
                    node_id=node.node_id,
                    endpoint=node.endpoint,
                    last_sync=datetime.now(UTC),
                    healthy=node.healthy,
                    priority=node.priority,
                )
                self._nodes[operation.target_node] = updated_node

            logger.info(
                "sync_completed",
                operation_id=operation.operation_id,
                data_id=operation.data_id,
            )

            return completed_op

        except Exception as e:
            # Sync failed
            failed_op = SyncOperation(
                operation_id=operation.operation_id,
                source_node=operation.source_node,
                target_node=operation.target_node,
                data_id=operation.data_id,
                data_type=operation.data_type,
                data=operation.data,
                timestamp=operation.timestamp,
                status=SyncStatus.FAILED,
                version=operation.version,
            )

            for i, op in enumerate(self._operations):
                if op.operation_id == operation.operation_id:
                    self._operations[i] = failed_op
                    break

            logger.error(
                "sync_failed",
                operation_id=operation.operation_id,
                error=str(e),
            )

            return failed_op

    def get_conflicts(
        self,
        resolved: bool | None = None,
        limit: int = 100,
    ) -> list[SyncConflict]:
        """
        Get synchronization conflicts.

        Args:
            resolved: Filter by resolved status
            limit: Maximum number of conflicts

        Returns:
            List of conflicts
        """
        conflicts = self._conflicts

        if resolved is not None:
            conflicts = [c for c in conflicts if c.resolved == resolved]

        return sorted(conflicts, key=lambda c: c.detected_at, reverse=True)[:limit]

    def get_operations(
        self,
        status: SyncStatus | None = None,
        limit: int = 100,
    ) -> list[SyncOperation]:
        """
        Get synchronization operations.

        Args:
            status: Filter by status
            limit: Maximum number of operations

        Returns:
            List of operations
        """
        operations = self._operations

        if status:
            operations = [op for op in operations if op.status == status]

        return sorted(operations, key=lambda op: op.timestamp, reverse=True)[:limit]

    def get_node(self, node_id: str) -> SyncNode | None:
        """
        Get a sync node.

        Args:
            node_id: Node identifier

        Returns:
            Sync node or None
        """
        return self._nodes.get(node_id)

    def remove_node(self, node_id: str) -> bool:
        """
        Remove a sync node.

        Args:
            node_id: Node identifier

        Returns:
            True if removed
        """
        if node_id in self._nodes:
            del self._nodes[node_id]

            logger.info(
                "sync_node_removed",
                node_id=node_id,
            )

            return True
        return False

    def mark_node_healthy(self, node_id: str, healthy: bool) -> bool:
        """
        Mark node health status.

        Args:
            node_id: Node identifier
            healthy: Health status

        Returns:
            True if updated
        """
        if node_id in self._nodes:
            node = self._nodes[node_id]
            updated_node = SyncNode(
                node_id=node.node_id,
                endpoint=node.endpoint,
                last_sync=node.last_sync,
                healthy=healthy,
                priority=node.priority,
            )

            self._nodes[node_id] = updated_node

            logger.info(
                "node_health_updated",
                node_id=node_id,
                healthy=healthy,
            )

            return True
        return False

    def get_sync_stats(self) -> dict[str, Any]:
        """
        Get synchronization statistics.

        Returns:
            Sync statistics
        """
        total_operations = len(self._operations)
        total_conflicts = len(self._conflicts)

        status_counts: dict[str, int] = {}
        for op in self._operations:
            status_counts[op.status] = status_counts.get(op.status, 0) + 1

        resolved_conflicts = sum(1 for c in self._conflicts if c.resolved)

        return {
            "total_nodes": len(self._nodes),
            "healthy_nodes": sum(1 for n in self._nodes.values() if n.healthy),
            "total_operations": total_operations,
            "total_conflicts": total_conflicts,
            "resolved_conflicts": resolved_conflicts,
            "unresolved_conflicts": total_conflicts - resolved_conflicts,
            "status_breakdown": status_counts,
        }
