"""
Change Log - Change Log and Replay Mechanism

Implements change log for data change tracking and replay.
Supports operation logging, change tracking, and selective replay.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class OperationType(StrEnum):
    """Operation type."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


@dataclass(frozen=True, slots=True)
class ChangeLogEntry:
    """Change log entry."""

    entry_id: str
    operation_type: OperationType
    data_id: str
    data_type: str
    previous_data: Any | None
    new_data: Any
    timestamp: datetime
    source: str
    version: int


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """Replay result."""

    replay_id: str
    from_entry_id: str
    to_entry_id: str
    operations_replayed: int
    successful: bool
    error: str | None
    replayed_at: datetime


class ChangeLog:
    """
    Change log for data change tracking.

    Features:
    - Operation logging
    - Change tracking
    - Selective replay
    - Version control
    """

    def __init__(self) -> None:
        """Initialize change log."""
        self._entries: list[ChangeLogEntry] = []
        self._data_versions: dict[str, int] = {}  # data_id -> version
        self._replay_callback: Callable[[ChangeLogEntry], Awaitable[bool]] | None = None

    def set_replay_callback(
        self,
        callback: Callable[[ChangeLogEntry], Awaitable[bool]],
    ) -> None:
        """
        Set callback for replay operations.

        Args:
            callback: Async function to replay an entry
        """
        self._replay_callback = callback

    async def log_change(
        self,
        operation_type: OperationType,
        data_id: str,
        data_type: str,
        previous_data: Any | None,
        new_data: Any,
        source: str,
    ) -> ChangeLogEntry:
        """
        Log a data change.

        Args:
            operation_type: Operation type
            data_id: Data identifier
            data_type: Data type
            previous_data: Previous data
            new_data: New data
            source: Change source

        Returns:
            Change log entry
        """
        # Increment version
        current_version = self._data_versions.get(data_id, 0) + 1
        self._data_versions[data_id] = current_version

        entry_id = f"entry-{datetime.now(UTC).timestamp()}-{current_version}"

        entry = ChangeLogEntry(
            entry_id=entry_id,
            operation_type=operation_type,
            data_id=data_id,
            data_type=data_type,
            previous_data=previous_data,
            new_data=new_data,
            timestamp=datetime.now(UTC),
            source=source,
            version=current_version,
        )

        self._entries.append(entry)

        logger.debug(
            "change_logged",
            entry_id=entry_id,
            operation_type=operation_type,
            data_id=data_id,
        )

        return entry

    async def replay_from_entry(
        self,
        from_entry_id: str,
        to_entry_id: str | None = None,
    ) -> ReplayResult:
        """
        Replay changes from an entry.

        Args:
            from_entry_id: Starting entry ID
            to_entry_id: Ending entry ID (None for latest)

        Returns:
            Replay result
        """
        replay_id = f"replay-{datetime.now(UTC).timestamp()}"

        # Find entry indices
        from_index = None
        to_index = len(self._entries)

        for i, entry in enumerate(self._entries):
            if entry.entry_id == from_entry_id:
                from_index = i
            if to_entry_id and entry.entry_id == to_entry_id:
                to_index = i + 1

        if from_index is None:
            return ReplayResult(
                replay_id=replay_id,
                from_entry_id=from_entry_id,
                to_entry_id=to_entry_id or "",
                operations_replayed=0,
                successful=False,
                error="Starting entry not found",
                replayed_at=datetime.now(UTC),
            )

        # Replay entries
        operations_replayed = 0

        if not self._replay_callback:
            return ReplayResult(
                replay_id=replay_id,
                from_entry_id=from_entry_id,
                to_entry_id=to_entry_id or "",
                operations_replayed=0,
                successful=False,
                error="No replay callback configured",
                replayed_at=datetime.now(UTC),
            )

        try:
            for entry in self._entries[from_index:to_index]:
                success = await self._replay_callback(entry)
                if success:
                    operations_replayed += 1

            result = ReplayResult(
                replay_id=replay_id,
                from_entry_id=from_entry_id,
                to_entry_id=to_entry_id or "",
                operations_replayed=operations_replayed,
                successful=True,
                error=None,
                replayed_at=datetime.now(UTC),
            )

            logger.info(
                "replay_completed",
                replay_id=replay_id,
                operations_replayed=operations_replayed,
            )

            return result

        except Exception as e:
            result = ReplayResult(
                replay_id=replay_id,
                from_entry_id=from_entry_id,
                to_entry_id=to_entry_id or "",
                operations_replayed=operations_replayed,
                successful=False,
                error=str(e),
                replayed_at=datetime.now(UTC),
            )

            logger.error(
                "replay_failed",
                replay_id=replay_id,
                error=str(e),
            )

            return result

    async def replay_data_changes(
        self,
        data_id: str,
        from_version: int | None = None,
        to_version: int | None = None,
    ) -> ReplayResult:
        """
        Replay changes for specific data.

        Args:
            data_id: Data identifier
            from_version: Starting version
            to_version: Ending version

        Returns:
            Replay result
        """
        # Find entries for this data
        data_entries = [entry for entry in self._entries if entry.data_id == data_id]

        if not data_entries:
            return ReplayResult(
                replay_id=f"replay-{datetime.now(UTC).timestamp()}",
                from_entry_id="",
                to_entry_id="",
                operations_replayed=0,
                successful=False,
                error="No entries found for data",
                replayed_at=datetime.now(UTC),
            )

        # Filter by version
        if from_version is not None:
            data_entries = [e for e in data_entries if e.version >= from_version]

        if to_version is not None:
            data_entries = [e for e in data_entries if e.version <= to_version]

        if not data_entries:
            return ReplayResult(
                replay_id=f"replay-{datetime.now(UTC).timestamp()}",
                from_entry_id="",
                to_entry_id="",
                operations_replayed=0,
                successful=False,
                error="No entries in version range",
                replayed_at=datetime.now(UTC),
            )

        # Replay entries
        operations_replayed = 0

        if not self._replay_callback:
            return ReplayResult(
                replay_id=f"replay-{datetime.now(UTC).timestamp()}",
                from_entry_id="",
                to_entry_id="",
                operations_replayed=0,
                successful=False,
                error="No replay callback configured",
                replayed_at=datetime.now(UTC),
            )

        try:
            for entry in data_entries:
                success = await self._replay_callback(entry)
                if success:
                    operations_replayed += 1

            result = ReplayResult(
                replay_id=f"replay-{datetime.now(UTC).timestamp()}",
                from_entry_id=data_entries[0].entry_id,
                to_entry_id=data_entries[-1].entry_id,
                operations_replayed=operations_replayed,
                successful=True,
                error=None,
                replayed_at=datetime.now(UTC),
            )

            logger.info(
                "data_replay_completed",
                data_id=data_id,
                operations_replayed=operations_replayed,
            )

            return result

        except Exception as e:
            result = ReplayResult(
                replay_id=f"replay-{datetime.now(UTC).timestamp()}",
                from_entry_id="",
                to_entry_id="",
                operations_replayed=operations_replayed,
                successful=False,
                error=str(e),
                replayed_at=datetime.now(UTC),
            )

            logger.error(
                "data_replay_failed",
                data_id=data_id,
                error=str(e),
            )

            return result

    def get_entries(
        self,
        data_id: str | None = None,
        data_type: str | None = None,
        operation_type: OperationType | None = None,
        limit: int = 100,
    ) -> list[ChangeLogEntry]:
        """
        Get change log entries.

        Args:
            data_id: Filter by data ID
            data_type: Filter by data type
            operation_type: Filter by operation type
            limit: Maximum number of entries

        Returns:
            List of change log entries
        """
        entries = self._entries

        if data_id:
            entries = [e for e in entries if e.data_id == data_id]

        if data_type:
            entries = [e for e in entries if e.data_type == data_type]

        if operation_type:
            entries = [e for e in entries if e.operation_type == operation_type]

        return sorted(entries, key=lambda e: e.timestamp, reverse=True)[:limit]

    def get_data_version(self, data_id: str) -> int | None:
        """
        Get current version of data.

        Args:
            data_id: Data identifier

        Returns:
            Current version or None
        """
        return self._data_versions.get(data_id)

    def get_data_history(
        self,
        data_id: str,
    ) -> list[ChangeLogEntry]:
        """
        Get change history for data.

        Args:
            data_id: Data identifier

        Returns:
            List of change log entries
        """
        return [entry for entry in self._entries if entry.data_id == data_id]

    def cleanup_old_entries(self, retention_days: int = 30) -> int:
        """
        Clean up old change log entries.

        Args:
            retention_days: Retention period in days

        Returns:
            Number of entries cleaned up
        """
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        initial_count = len(self._entries)

        self._entries = [entry for entry in self._entries if entry.timestamp > cutoff]

        cleaned = initial_count - len(self._entries)

        if cleaned > 0:
            logger.info(
                "old_entries_cleaned",
                count=cleaned,
            )

        return cleaned

    def get_change_log_stats(self) -> dict[str, Any]:
        """
        Get change log statistics.

        Returns:
            Change log statistics
        """
        total_entries = len(self._entries)

        operation_type_counts: dict[str, int] = {}
        for entry in self._entries:
            operation_type_counts[entry.operation_type] = (
                operation_type_counts.get(entry.operation_type, 0) + 1
            )

        data_type_counts: dict[str, int] = {}
        for entry in self._entries:
            data_type_counts[entry.data_type] = data_type_counts.get(entry.data_type, 0) + 1

        return {
            "total_entries": total_entries,
            "unique_data_ids": len(self._data_versions),
            "operation_type_breakdown": operation_type_counts,
            "data_type_breakdown": data_type_counts,
        }
