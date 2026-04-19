import uuid
from datetime import datetime, UTC
from sqlalchemy import String, JSON, DateTime, ForeignKey, Integer, Text, UUID as UUIDType
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from infrastructure.database import Base

def now_utc():
    return datetime.now(UTC)

class Workflow(Base):
    """Workflow = container for related tasks."""
    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(UUIDType(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUIDType(as_uuid=True), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    intent: Mapped[str] = mapped_column(String(64), nullable=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)  # macro, routine, durable
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    plan_schema: Mapped[dict] = mapped_column(JSONB, nullable=True)
    context_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=True)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

class Task(Base):
    """Individual execution unit within a workflow."""
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUIDType(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id"), nullable=False, index=True)
    parent_task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)  # planning, execution, approval
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    input_data: Mapped[dict] = mapped_column(JSONB, nullable=True)
    output_data: Mapped[dict] = mapped_column(JSONB, nullable=True)
    error_data: Mapped[dict] = mapped_column(JSONB, nullable=True)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=True)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    compensation_task_id: Mapped[uuid.UUID] = mapped_column(UUIDType(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

class TaskTransition(Base):
    """Event-sourced trail for task status changes. Partitioned by month."""
    __tablename__ = "task_transitions"

    id: Mapped[uuid.UUID] = mapped_column(UUIDType(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger: Mapped[str] = mapped_column(String(64), nullable=False)  # auto, manual, timeout, error
    metadata_col: Mapped[dict] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class ApprovalRequest(Base):
    """Approval request for gated operations."""
    __tablename__ = "approval_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUIDType(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id"), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUIDType(as_uuid=True), nullable=False)
    approval_type: Mapped[str] = mapped_column(String(32), nullable=False)  # tool, send, delete
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")  # pending, approved, denied, expired
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
