import uuid
from datetime import datetime, UTC
from sqlalchemy import String, Integer, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from infrastructure.database import Base

def now_utc():
    return datetime.now(UTC)

class ToolDefinition(Base):
    """Tool registry entry — defines what a tool CAN do."""
    __tablename__ = "tool_definitions"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)        # search, communication, device, data
    risk_tier: Mapped[str] = mapped_column(String(32), nullable=False)       # T0_safe, T1_low, T2_medium, T3_high
    input_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)   # JSON Schema for parameters
    output_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)  # JSON Schema for results
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    idempotent: Mapped[bool] = mapped_column(Boolean, default=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    compensation_handler: Mapped[str] = mapped_column(String(64), nullable=True)  # Name of undo tool
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[str] = mapped_column(String(16), default="1.0")

class ToolExecution(Base):
    """Audit record of every tool invocation."""
    __tablename__ = "tool_executions"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(nullable=True, index=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(nullable=True, index=True)
    input_params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output_result: Mapped[dict] = mapped_column(JSONB, nullable=True)
    risk_tier: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")           # pending, executing, completed, failed, compensated
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    verification_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_data: Mapped[dict] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
