"""Initial schema — full Butler v2.0 Oracle-Grade data spec.
Consolidates all core identity, memory, orchestrator, tool, and cron tables.
Revision: 001
Down Revision: None
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extensions (Idempotent & Transaction-Safe) ────────────────────────
    op.execute("""
        DO $$ BEGIN
            CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";
        EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'uuid-ossp failed'; END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE EXTENSION IF NOT EXISTS pg_trgm;
        EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'pg_trgm failed'; END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE EXTENSION IF NOT EXISTS vector;
        EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'vector not available'; END $$
    """)

    # ── ENUM types ────────────────────────────────────────────────────────
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE account_status AS ENUM ('active', 'suspended', 'deleted');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$
    """)

    # =========================================================================
    # IDENTITY & AUTH DOMAIN
    # =========================================================================

    op.create_table(
        "principals",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_principals_email", "principals", ["email"], unique=True)

    op.create_table(
        "accounts",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "principal_id",
            sa.UUID(),
            sa.ForeignKey("principals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False, server_default="Personal"),
        sa.Column("settings", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    op.create_table(
        "identities",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "principal_id",
            sa.UUID(),
            sa.ForeignKey("principals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("identity_type", sa.String(32), nullable=False),
        sa.Column("identifier", sa.String(512), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=True),
        sa.Column("external_id", sa.String(256), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index(
        "uq_identities_type_identifier", "identities", ["identity_type", "identifier"], unique=True
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "principal_id",
            sa.UUID(),
            sa.ForeignKey("principals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "active_account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("auth_method", sa.String(32), nullable=False),
        sa.Column("assurance_level", sa.String(8), nullable=False, server_default="aal1"),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("device_id", sa.String(128), nullable=True),
        sa.Column("client_id", sa.String(128), nullable=True),
        sa.Column("client_type", sa.String(32), nullable=True),
        sa.Column("risk_score", sa.Numeric(5, 4), nullable=False, server_default="0.0"),
        sa.Column("workflow_id", sa.UUID(), nullable=True),
        sa.Column("idle_timeout", sa.Integer(), nullable=True),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    op.create_table(
        "refresh_token_families",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "session_id",
            sa.UUID(),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("parent_token_id", sa.String(128), nullable=True),
        sa.Column("lineage_root", sa.String(128), nullable=True),
        sa.Column("revoked_branch_root", sa.String(128), nullable=True),
        sa.Column("rotation_counter", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidation_reason", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    # ── Voice Profiles ───────────────────────────────────────────────────
    op.create_table(
        "voice_profiles",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "principal_id",
            sa.UUID(),
            sa.ForeignKey("principals.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column("sample_url", sa.String(512), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    # =========================================================================
    # MEMORY & NOTEBOOKS
    # =========================================================================

    op.create_table(
        "memory_entries",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("memory_type", sa.String(32), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("embedding", postgresql.JSONB(), nullable=True),
        sa.Column("importance", sa.Float(), server_default="0.5"),
        sa.Column("confidence", sa.Float(), server_default="1.0"),
        sa.Column("source", sa.String(32), server_default="conversation"),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("tags", postgresql.JSONB(), server_default="[]"),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "last_accessed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("access_count", sa.Integer(), server_default="0"),
    )

    op.create_table(
        "conversation_turns",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("intent", sa.String(64), nullable=True),
        sa.Column("tool_calls", postgresql.JSONB(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("ix_conversation_turns_session", "conversation_turns", ["session_id"])

    # ── Knowledge Graph Layer ──────────────────────────────────────────
    op.create_table(
        "knowledge_entities",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("name_embedding", postgresql.JSONB(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column("status", sa.String(32), server_default="active"),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    op.create_table(
        "knowledge_edges",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.UUID(),
            sa.ForeignKey("knowledge_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            sa.UUID(),
            sa.ForeignKey("knowledge_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation_type", sa.String(64), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    op.create_table(
        "memory_entity_links",
        sa.Column(
            "memory_id",
            sa.UUID(),
            sa.ForeignKey("memory_entries.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "entity_id",
            sa.UUID(),
            sa.ForeignKey("knowledge_entities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # ── User Understanding Layer ───────────────────────────────────────
    op.create_table(
        "explicit_preferences",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="1.0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    op.create_table(
        "explicit_dislikes",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("reason", postgresql.JSONB(), nullable=True),
        sa.Column("confidence", sa.Float(), server_default="1.0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    op.create_table(
        "user_constraints",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("constraint_type", sa.String(64), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    op.create_table(
        "memory_episodes",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(32)),
        sa.Column("events", postgresql.JSONB(), server_default="[]"),
        sa.Column("lessons", postgresql.JSONB(), server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    op.create_table(
        "memory_routines",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("occurrences", sa.Integer(), server_default="1"),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "last_observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("index", sa.Integer(), server_default="0"),
        sa.Column("source_type", sa.String(32)),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("embedding", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    op.create_table(
        "chunk_entity_links",
        sa.Column(
            "chunk_id",
            sa.UUID(),
            sa.ForeignKey("knowledge_chunks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "entity_id",
            sa.UUID(),
            sa.ForeignKey("knowledge_entities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "notebooks",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("archived", sa.Boolean(), server_default="false"),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    op.create_table(
        "sources",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("asset", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("full_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    op.create_table(
        "notes",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("note_type", sa.String(16), server_default="human"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    # Join tables
    op.create_table(
        "notebook_sources",
        sa.Column(
            "notebook_id",
            sa.UUID(),
            sa.ForeignKey("notebooks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "source_id",
            sa.UUID(),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "notebook_notes",
        sa.Column(
            "notebook_id",
            sa.UUID(),
            sa.ForeignKey("notebooks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "note_id", sa.UUID(), sa.ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True
        ),
    )

    # =========================================================================
    # RUNTIME & ORCHESTRATION
    # =========================================================================

    op.create_table(
        "workflows",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("plan_schema", sa.JSON(), nullable=True),
        sa.Column("state_snapshot", sa.JSON(), nullable=True),
        sa.Column("idempotency_key", sa.String(256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "workflow_id",
            sa.UUID(),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_task_id",
            sa.UUID(),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("input_data", sa.JSON(), nullable=True),
        sa.Column("output_data", sa.JSON(), nullable=True),
        sa.Column("tool_name", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    # =========================================================================
    # TOOLS & CRON
    # =========================================================================

    op.create_table(
        "tool_definitions",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("risk_tier", sa.String(32), nullable=False),
        sa.Column("input_schema", postgresql.JSONB(), nullable=False),
        sa.Column("output_schema", postgresql.JSONB(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    op.create_table(
        "butler_cron_jobs",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column(
            "account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("cron_expression", sa.String(64), nullable=False),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    # ── Vector Application ──────────────────────────────────────────────
    # For fresh databases, create embedding as vector directly if available
    # For existing databases with JSONB data, we'd need a migration with data handling
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'vector') THEN
                -- For fresh database, drop the JSONB column and recreate as vector
                ALTER TABLE memory_entries DROP COLUMN IF EXISTS embedding;
                ALTER TABLE memory_entries ADD COLUMN embedding vector(1536);
            END IF;
        END $$
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS butler_cron_jobs CASCADE")
    op.execute("DROP TABLE IF EXISTS tool_definitions CASCADE")
    op.execute("DROP TABLE IF EXISTS tasks CASCADE")
    op.execute("DROP TABLE IF EXISTS workflows CASCADE")
    op.execute("DROP TABLE IF EXISTS notebook_notes CASCADE")
    op.execute("DROP TABLE IF EXISTS notebook_sources CASCADE")
    op.execute("DROP TABLE IF EXISTS notes CASCADE")
    op.execute("DROP TABLE IF EXISTS sources CASCADE")
    op.execute("DROP TABLE IF EXISTS notebooks CASCADE")
    op.execute("DROP TABLE IF EXISTS memory_entries CASCADE")
    op.execute("DROP TABLE IF EXISTS voice_profiles CASCADE")
    op.execute("DROP TABLE IF EXISTS refresh_token_families CASCADE")
    op.execute("DROP TABLE IF EXISTS sessions CASCADE")
    op.execute("DROP TABLE IF EXISTS identities CASCADE")
    op.execute("DROP TABLE IF EXISTS accounts CASCADE")
    op.execute("DROP TABLE IF EXISTS principals CASCADE")
    op.execute("DROP TYPE IF EXISTS account_status CASCADE")
