"""Tool Execution & Registry Models.

Hardened for high-concurrency inserts, strict data integrity,
and optimized query paths.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from infrastructure.database import Base


class ToolDefinition(Base):
    """Tool registry entry — defines what a tool CAN do."""

    __tablename__ = "tool_definitions"
    __table_args__ = (
        CheckConstraint(
            "category IN ('search', 'communication', 'device', 'data', 'orchestration')",
            name="chk_tool_def_category",
        ),
        CheckConstraint(
            "risk_tier IN ('T0_safe', 'T1_low', 'T2_medium', 'T3_high')",
            name="chk_tool_def_risk_tier",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(32), nullable=False)
    
    # Server-side defaults ensure we never hit NULL pointer exceptions during fast JSON parsing
    input_schema: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    output_schema: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    idempotent: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30, server_default=text("30"))
    compensation_handler: Mapped[str | None] = mapped_column(String(64), nullable=True)
    
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    version: Mapped[str] = mapped_column(String(16), default="1.0", server_default=text("'1.0'"))


class ToolExecution(Base):
    """Audit record of every tool invocation."""

    __tablename__ = "tool_executions"
    __table_args__ = (
        # 1. Strict State Machine Guarantees
        CheckConstraint(
            "status IN ('pending', 'executing', 'completed', 'failed', 'cancelled', 'compensated')",
            name="chk_tool_exec_status",
        ),
        # 2. Race-Condition Proof Idempotency (tenant-scoped)
        UniqueConstraint(
            "tenant_id", "idempotency_key", 
            name="uq_tool_exec_tenant_idempotency"
        ),
        # 3. Optimized Composite Indices (Left-prefix optimized)
        # Note: We removed the standalone 'tenant_id' index because it is 
        # naturally covered by the left-most column of these composite indices.
        Index("idx_tool_exec_tenant_created", "tenant_id", "created_at"),
        Index("idx_tool_exec_tenant_session_created", "tenant_id", "session_id", "created_at"),
        Index("idx_tool_exec_tenant_tool_created", "tenant_id", "tool_name", "created_at"),
        Index("idx_tool_exec_tenant_account_created", "tenant_id", "account_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    task_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    
    input_params: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    output_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    
    risk_tier: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", server_default=text("'pending'"))
    
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_passed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    
    # Granular Structured Data
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_spec_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    
    sandbox_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default=text("false"))
    approval_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    degraded_mode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    compensation_handler_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    
    # DB-calculated timestamps eliminate application-side clock drift
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), 
        nullable=True
    )