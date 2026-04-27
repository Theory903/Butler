"""add tool execution real columns, constraints, and concurrent indexes

Revision ID: 3ab515fb150ba
Revises: 8b5d0ea168c8
Create Date: 2026-04-27 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3ab515fb150ba"
down_revision: str | None = "8b5d0ea168c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# CRITICAL: Alembic runs migrations in a single transaction by default.
# PostgreSQL cannot build indexes CONCURRENTLY inside a standard DDL transaction block.
# We must disable the Alembic transaction to allow non-blocking index creation.
disable_transaction = True


def upgrade() -> None:
    # 1. Add Columns (matching strict string limits from the model)
    op.add_column("tool_executions", sa.Column("session_id", sa.String(length=128), nullable=True))
    op.add_column("tool_executions", sa.Column("tool_spec_version", sa.String(length=16), nullable=True))
    op.add_column("tool_executions", sa.Column("input_hash", sa.String(length=64), nullable=True))
    op.add_column("tool_executions", sa.Column("output_hash", sa.String(length=64), nullable=True))
    op.add_column("tool_executions", sa.Column("policy_decision", sa.String(length=32), nullable=True))
    op.add_column("tool_executions", sa.Column("sandbox_used", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("tool_executions", sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("tool_executions", sa.Column("degraded_mode", sa.String(length=64), nullable=True))
    op.add_column("tool_executions", sa.Column("compensation_handler_id", sa.String(length=64), nullable=True))

    # 2. Enforce Data Integrity Guardrails at the DB Level
    op.create_unique_constraint(
        "uq_tool_exec_tenant_idempotency",
        "tool_executions",
        ["tenant_id", "idempotency_key"]
    )
    op.create_check_constraint(
        "chk_tool_exec_status",
        "tool_executions",
        "status IN ('pending', 'executing', 'completed', 'failed', 'cancelled', 'compensated')"
    )

    # 3. Build Composite Indexes Non-Blocking
    op.create_index(
        "idx_tool_exec_tenant_session_created",
        "tool_executions",
        ["tenant_id", "session_id", "created_at"],
        unique=False,
        postgresql_concurrently=True,
    )
    op.create_index(
        "idx_tool_exec_tenant_tool_created",
        "tool_executions",
        ["tenant_id", "tool_name", "created_at"],
        unique=False,
        postgresql_concurrently=True,
    )
    op.create_index(
        "idx_tool_exec_tenant_account_created",
        "tool_executions",
        ["tenant_id", "account_id", "created_at"],
        unique=False,
        postgresql_concurrently=True,
    )

    # 4. Cleanup redundant standalone indices to save write latency/storage
    # (Assuming these were created in a prior migration based on standard practices)
    try:
        op.drop_index("ix_tool_executions_tenant_id", table_name="tool_executions", postgresql_concurrently=True)
    except Exception:
        pass  # Safe fallback if it was already dropped or named differently


def downgrade() -> None:
    # Note: Downgrades in autocommit mode must also be careful with locks.
    
    # 1. Drop Indexes Concurrently
    op.drop_index("idx_tool_exec_tenant_account_created", table_name="tool_executions", postgresql_concurrently=True)
    op.drop_index("idx_tool_exec_tenant_tool_created", table_name="tool_executions", postgresql_concurrently=True)
    op.drop_index("idx_tool_exec_tenant_session_created", table_name="tool_executions", postgresql_concurrently=True)

    # Re-add the standalone index if we drop the composite ones
    op.create_index("ix_tool_executions_tenant_id", "tool_executions", ["tenant_id"], postgresql_concurrently=True)

    # 2. Drop Constraints
    op.drop_constraint("chk_tool_exec_status", "tool_executions", type_="check")
    op.drop_constraint("uq_tool_exec_tenant_idempotency", "tool_executions", type_="unique")

    # 3. Drop Columns
    op.drop_column("tool_executions", "compensation_handler_id")
    op.drop_column("tool_executions", "degraded_mode")
    op.drop_column("tool_executions", "approval_id")
    op.drop_column("tool_executions", "sandbox_used")
    op.drop_column("tool_executions", "policy_decision")
    op.drop_column("tool_executions", "output_hash")
    op.drop_column("tool_executions", "input_hash")
    op.drop_column("tool_executions", "tool_spec_version")
    op.drop_column("tool_executions", "session_id")