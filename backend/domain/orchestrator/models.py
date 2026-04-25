from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database import Base

UTC = UTC
UUIDType = UUID


def now_utc() -> datetime:
    return datetime.now(UTC)


class Workflow(Base):
    """Workflow container for related tasks and durable execution state."""

    __tablename__ = "workflows"
    __table_args__ = (
        Index(
            "ix_workflows_tenant_account_session_created_at",
            "tenant_id",
            "account_id",
            "session_id",
            "created_at",
        ),
        Index("ix_workflows_tenant_account_status", "tenant_id", "account_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True),
        nullable=False,
        index=True,
    )
    session_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        index=True,
    )
    plan_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    state_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    context_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __mapper_args__ = {"version_id_col": version}


class ApprovalRequest(Base):
    """Approval request for high-risk tool execution."""

    __tablename__ = "approval_requests"
    __table_args__ = (
        Index("ix_approval_requests_tenant_account_status", "tenant_id", "account_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True),
        nullable=False,
        index=True,
    )
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflows.id"),
        nullable=True,
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_tier: Mapped[int] = mapped_column(Integer, nullable=False)
    args_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        index=True,
    )
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUIDType(as_uuid=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        nullable=False,
    )


class Task(Base):
    """Individual execution unit within a workflow."""

    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_workflow_status", "workflow_id", "status"),
        Index("ix_tasks_parent_status", "parent_task_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id"),
        nullable=False,
        index=True,
    )
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id"),
        nullable=True,
    )
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        index=True,
    )
    input_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    output_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    compensation_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType(as_uuid=True),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __mapper_args__ = {"version_id_col": version}


class TaskTransition(Base):
    """Event trail for task status transitions."""

    __tablename__ = "task_transitions"
    __table_args__ = (Index("ix_task_transitions_task_created_at", "task_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id"),
        nullable=False,
        index=True,
    )
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_col: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        nullable=False,
    )


class WorkflowApprovalRequest(Base):
    """Approval request for gated workflow operations."""

    __tablename__ = "workflow_approval_requests"
    __table_args__ = (
        Index("ix_workflow_approval_requests_workflow_status", "workflow_id", "status"),
        Index(
            "ix_workflow_approval_requests_tenant_account_status_expires_at",
            "tenant_id",
            "account_id",
            "status",
            "expires_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True),
        nullable=False,
        index=True,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id"),
        nullable=False,
        index=True,
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True),
        nullable=False,
        index=True,
    )
    approval_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        nullable=False,
    )


class WorkflowEvent(Base):
    """Persistent workflow event log for replay and recovery."""

    __tablename__ = "workflow_events"
    __table_args__ = (
        Index("ix_workflow_events_workflow_created_at", "workflow_id", "created_at"),
        Index("ix_workflow_events_workflow_node_type", "workflow_id", "node_id", "event_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    node_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    output_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        nullable=False,
    )


class WorkflowSignal(Base):
    """External signals sent to running workflows."""

    __tablename__ = "workflow_signals"
    __table_args__ = (
        Index("ix_workflow_signals_workflow_signal_status", "workflow_id", "signal_name", "status"),
        Index("ix_workflow_signals_idempotency_key", "idempotency_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id"),
        nullable=False,
        index=True,
    )
    signal_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        index=True,
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        nullable=False,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class SystemNode(Base):
    """Persistent registry of cluster nodes."""

    __tablename__ = "nodes"
    __table_args__ = (Index("ix_nodes_status_last_heartbeat", "status", "last_heartbeat"),)

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="STARTING",
        index=True,
    )
    resource_pressure: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    last_heartbeat: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        onupdate=now_utc,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        nullable=False,
    )
