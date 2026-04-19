"""Initial schema — full Butler data spec.

Creates:
  Identity/Auth: accounts, identities, sessions, refresh_token_families
  Runtime:       workflows, tasks, task_nodes, task_transitions (*), approval_requests
  Tool/Audit:    tool_executions, audit_events (*), outbox_events (*)
  Config:        user_settings, feature_flags

(*) = declaratively partitioned by month on created_at

Revision: 001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extensions ────────────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    except Exception:
        pass  # pgvector not installed — Memory service will handle gracefully

    # ── ENUM types ────────────────────────────────────────────────────────
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE account_status AS ENUM ('active', 'suspended', 'deleted');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE identity_type AS ENUM ('password', 'passkey', 'google', 'apple', 'github');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE assurance_level AS ENUM ('aal1', 'aal2', 'aal3');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE task_status AS ENUM (
                'pending', 'planning', 'executing', 'completed',
                'awaiting_approval', 'failed', 'compensating',
                'compensated', 'compensation_failed'
            );
        EXCEPTION WHEN duplicate_object THEN null;
        END $$
    """)

    # =========================================================================
    # IDENTITY & AUTH DOMAIN
    # =========================================================================

    # accounts
    op.create_table(
        "accounts",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("settings", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_accounts_email", "accounts", ["email"], unique=True,
                    postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index("ix_accounts_status", "accounts", ["status"])
    op.create_index("ix_accounts_created_at", "accounts", ["created_at"])

    # identities
    op.create_table(
        "identities",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("account_id", sa.UUID(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("identity_type", sa.String(32), nullable=False),
        sa.Column("identifier", sa.String(512), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=True),
        sa.Column("external_id", sa.String(256), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_identities_account_id", "identities", ["account_id"])
    op.create_index("uq_identities_type_identifier", "identities",
                    ["identity_type", "identifier"], unique=True)

    # passkey_credentials
    op.create_table(
        "passkey_credentials",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("account_id", sa.UUID(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("credential_id", sa.Text(), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("aaguid", sa.String(64), nullable=True),
        sa.Column("device_type", sa.String(32), nullable=True),
        sa.Column("backup_eligible", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("backup_state", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_passkey_account_id", "passkey_credentials", ["account_id"])
    op.create_index("uq_passkey_credential_id", "passkey_credentials", ["credential_id"], unique=True)

    # sessions
    op.create_table(
        "sessions",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("account_id", sa.UUID(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("auth_method", sa.String(32), nullable=False),
        sa.Column("assurance_level", sa.String(8), nullable=False, server_default="aal1"),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("device_id", sa.String(128), nullable=True),
        sa.Column("risk_score", sa.Numeric(5, 4), nullable=False, server_default="0.0"),
        sa.Column("workflow_id", sa.UUID(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_sessions_account_id", "sessions", ["account_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])
    op.create_index("ix_sessions_active", "sessions", ["account_id"],
                    postgresql_where=sa.text("revoked_at IS NULL"))

    # refresh_token_families
    op.create_table(
        "refresh_token_families",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("session_id", sa.UUID(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rotation_counter", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidation_reason", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_token_families_session_id", "refresh_token_families", ["session_id"])

    # =========================================================================
    # RUNTIME DOMAIN
    # =========================================================================

    # workflows
    op.create_table(
        "workflows",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("account_id", sa.UUID(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("intent", sa.String(64), nullable=True),
        sa.Column("mode", sa.String(32), nullable=False),  # macro | routine | durable
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("plan_schema", sa.JSON(), nullable=True),
        sa.Column("context_snapshot", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_workflows_account_id", "workflows", ["account_id"])
    op.create_index("ix_workflows_session_id", "workflows", ["session_id"])
    op.create_index("ix_workflows_status", "workflows", ["status"])
    op.create_index("ix_workflows_created_at", "workflows", ["created_at"])

    # tasks
    op.create_table(
        "tasks",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("workflow_id", sa.UUID(), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_task_id", sa.UUID(), nullable=True),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("input_data", sa.JSON(), nullable=True),
        sa.Column("output_data", sa.JSON(), nullable=True),
        sa.Column("error_data", sa.JSON(), nullable=True),
        sa.Column("tool_name", sa.String(128), nullable=True),
        sa.Column("retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("compensation_task_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tasks_workflow_id", "tasks", ["workflow_id"])
    op.create_index("ix_tasks_status", "tasks", ["status"])

    # task_transitions (event-sourced trail, partitioned by month)
    op.execute("""
        CREATE TABLE task_transitions (
            id          UUID NOT NULL DEFAULT uuid_generate_v4(),
            task_id     UUID NOT NULL,
            from_status VARCHAR(32) NOT NULL,
            to_status   VARCHAR(32) NOT NULL,
            trigger     VARCHAR(64) NOT NULL,
            metadata    JSON,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        ) PARTITION BY RANGE (created_at)
    """)
    op.execute("""
        CREATE TABLE task_transitions_default
            PARTITION OF task_transitions DEFAULT
    """)
    op.execute("CREATE INDEX ix_task_transitions_task_id ON task_transitions (task_id)")
    op.execute("CREATE INDEX ix_task_transitions_created_at ON task_transitions (created_at)")

    # approval_requests
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("task_id", sa.UUID(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workflow_id", sa.UUID(), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", sa.UUID(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("approval_type", sa.String(32), nullable=False),  # tool | send | delete | financial
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_approval_requests_task_id", "approval_requests", ["task_id"])
    op.create_index("ix_approval_requests_account_id", "approval_requests", ["account_id"])
    op.create_index("ix_approval_requests_status", "approval_requests", ["status"])

    # =========================================================================
    # TOOL & AUDIT DOMAIN
    # =========================================================================

    # tool_executions
    op.create_table(
        "tool_executions",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("account_id", sa.UUID(), sa.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("task_id", sa.UUID(), nullable=True),
        sa.Column("workflow_id", sa.UUID(), nullable=True),
        sa.Column("input_params", sa.JSON(), nullable=True),
        sa.Column("output_result", sa.JSON(), nullable=True),
        sa.Column("risk_tier", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("idempotency_key", sa.String(256), nullable=True),
        sa.Column("verification_passed", sa.Boolean(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tool_executions_account_id", "tool_executions", ["account_id"])
    op.create_index("ix_tool_executions_tool_name", "tool_executions", ["tool_name"])
    op.create_index("uq_tool_executions_idempotency", "tool_executions",
                    ["idempotency_key"], unique=True,
                    postgresql_where=sa.text("idempotency_key IS NOT NULL"))

    # audit_events (partitioned by month)
    op.execute("""
        CREATE TABLE audit_events (
            id               UUID NOT NULL DEFAULT uuid_generate_v4(),
            account_id       UUID,
            actor_id         VARCHAR(128),
            actor_type       VARCHAR(32) NOT NULL,
            action           VARCHAR(128) NOT NULL,
            resource_type    VARCHAR(64),
            resource_id      VARCHAR(128),
            outcome          VARCHAR(32) NOT NULL,
            sensitivity      VARCHAR(32) NOT NULL DEFAULT 'standard',
            request_id       VARCHAR(64),
            ip_address       VARCHAR(45),
            metadata         JSON,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        ) PARTITION BY RANGE (created_at)
    """)
    op.execute("""
        CREATE TABLE audit_events_default
            PARTITION OF audit_events DEFAULT
    """)
    op.execute("CREATE INDEX ix_audit_events_account_id ON audit_events (account_id)")
    op.execute("CREATE INDEX ix_audit_events_action ON audit_events (action)")
    op.execute("CREATE INDEX ix_audit_events_created_at ON audit_events (created_at)")

    # outbox_events (transactional outbox, partitioned by month)
    op.execute("""
        CREATE TABLE outbox_events (
            id               UUID NOT NULL DEFAULT uuid_generate_v4(),
            aggregate_type   VARCHAR(64) NOT NULL,
            aggregate_id     UUID NOT NULL,
            event_type       VARCHAR(128) NOT NULL,
            payload          JSON NOT NULL,
            published        BOOLEAN NOT NULL DEFAULT FALSE,
            published_at     TIMESTAMPTZ,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        ) PARTITION BY RANGE (created_at)
    """)
    op.execute("""
        CREATE TABLE outbox_events_default
            PARTITION OF outbox_events DEFAULT
    """)
    op.execute("CREATE INDEX ix_outbox_events_published ON outbox_events (published)")
    op.execute("CREATE INDEX ix_outbox_events_aggregate ON outbox_events (aggregate_type, aggregate_id)")

    # =========================================================================
    # CONFIG DOMAIN
    # =========================================================================

    # user_settings
    op.create_table(
        "user_settings",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("account_id", sa.UUID(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("uq_user_settings_account_key", "user_settings", ["account_id", "key"], unique=True)

    # feature_flags
    op.create_table(
        "feature_flags",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("rollout_percentage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conditions", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("uq_feature_flags_name", "feature_flags", ["name"], unique=True)


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("feature_flags")
    op.drop_table("user_settings")
    op.execute("DROP TABLE IF EXISTS outbox_events CASCADE")
    op.execute("DROP TABLE IF EXISTS audit_events CASCADE")
    op.drop_table("tool_executions")
    op.drop_table("approval_requests")
    op.execute("DROP TABLE IF EXISTS task_transitions CASCADE")
    op.drop_table("tasks")
    op.drop_table("workflows")
    op.drop_table("refresh_token_families")
    op.drop_table("sessions")
    op.drop_table("passkey_credentials")
    op.drop_table("identities")
    op.drop_table("accounts")

    # ENUMs
    op.execute("DROP TYPE IF EXISTS task_status")
    op.execute("DROP TYPE IF EXISTS assurance_level")
    op.execute("DROP TYPE IF EXISTS identity_type")
    op.execute("DROP TYPE IF EXISTS account_status")
