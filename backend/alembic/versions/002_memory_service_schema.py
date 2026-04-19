"""Memory service schema — full Butler memory stack.

Adds:
  - memory_entries (canonical vector-enabled store)
  - knowledge_entities & knowledge_edges (knowledge graph tier)
  - knowledge_chunks & source links (attribution)
  - preferences, dislikes & constraints (personalization)
  - episodes & routines (interaction patterns)

Revision: 002
Down Revision: 001
"""

from __future__ import annotations
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # ── pgvector Extension (Handled gracefully) ───────────────────────────
    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    except Exception:
        pass

    # ── Memory Status ENUM ────────────────────────────────────────────────
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE memory_status AS ENUM ('active', 'deprecated', 'conflicted');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$
    """)

    # ── memory_entries ────────────────────────────────────────────────────
    op.create_table(
        "memory_entries",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("account_id", sa.UUID(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("memory_type", sa.String(32), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("embedding", sa.NullType()), # Placeholder for pgvector type
        sa.Column("importance", sa.Float(), server_default="0.5"),
        sa.Column("confidence", sa.Float(), server_default="1.0"),
        sa.Column("source", sa.String(32), server_default="conversation"),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("tags", postgresql.JSONB(), server_default="[]"),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("access_count", sa.Integer(), server_default="0"),
    )
    # Attempt to add vector type if pgvector is enabled
    try:
        op.execute("ALTER TABLE memory_entries ALTER COLUMN embedding TYPE vector(1536)")
    except Exception:
        pass

    op.create_index("ix_mem_account_id", "memory_entries", ["account_id"])
    op.create_index("ix_mem_type", "memory_entries", ["memory_type"])
    op.create_index("ix_mem_status", "memory_entries", ["status"])
    op.create_index("ix_mem_session_id", "memory_entries", ["session_id"])

    # ── conversation_turns ────────────────────────────────────────────────
    op.create_table(
        "conversation_turns",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("account_id", sa.UUID(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("intent", sa.String(64), nullable=True),
        sa.Column("tool_calls", postgresql.JSONB(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_turns_session_id", "conversation_turns", ["session_id"])
    op.create_index("ix_turns_account_id", "conversation_turns", ["account_id"])

    # ── knowledge_entities ────────────────────────────────────────────────
    op.create_table(
        "knowledge_entities",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("account_id", sa.UUID(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("name_embedding", sa.NullType()), # Vector
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    try:
        op.execute("ALTER TABLE knowledge_entities ALTER COLUMN name_embedding TYPE vector(1536)")
    except Exception:
        pass
        
    op.create_index("ix_ent_account_name", "knowledge_entities", ["account_id", "name"])
    op.create_index("ix_ent_status", "knowledge_entities", ["status"])

    # ── knowledge_edges ───────────────────────────────────────────────────
    op.create_table(
        "knowledge_edges",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("account_id", sa.UUID(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.UUID(), sa.ForeignKey("knowledge_entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_id", sa.UUID(), sa.ForeignKey("knowledge_entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.String(64), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_edges_source", "knowledge_edges", ["source_id"])
    op.create_index("ix_edges_target", "knowledge_edges", ["target_id"])

    # ── memory_entity_links ───────────────────────────────────────────────
    op.create_table(
        "memory_entity_links",
        sa.Column("memory_id", sa.UUID(), sa.ForeignKey("memory_entries.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("entity_id", sa.UUID(), sa.ForeignKey("knowledge_entities.id", ondelete="CASCADE"), primary_key=True),
    )

    # ── explicit_preferences / dislikes / constraints ─────────────────────
    op.create_table(
        "explicit_preferences",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("account_id", sa.UUID(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("uq_pref_acc_key", "explicit_preferences", ["account_id", "key"])

    op.create_table(
        "explicit_dislikes",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("account_id", sa.UUID(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("reason", postgresql.JSONB(), nullable=True),
        sa.Column("confidence", sa.Float(), server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )

    op.create_table(
        "user_constraints",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("account_id", sa.UUID(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("constraint_type", sa.String(64), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )

    # ── episodes & routines ───────────────────────────────────────────────
    op.create_table(
        "memory_episodes",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("account_id", sa.UUID(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=True),
        sa.Column("events", postgresql.JSONB(), server_default="[]"),
        sa.Column("lessons", postgresql.JSONB(), server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )

    op.create_table(
        "memory_routines",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("account_id", sa.UUID(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("occurrences", sa.Integer(), server_default="1"),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )

    # ── knowledge_chunks & attribution ────────────────────────────────────
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("account_id", sa.UUID(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("index", sa.Integer(), server_default="0"),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("embedding", sa.NullType()), # Vector
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    try:
        op.execute("ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector(1536)")
    except Exception:
        pass

    op.create_table(
        "chunk_entity_links",
        sa.Column("chunk_id", sa.UUID(), sa.ForeignKey("knowledge_chunks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("entity_id", sa.UUID(), sa.ForeignKey("knowledge_entities.id", ondelete="CASCADE"), primary_key=True),
    )

def downgrade() -> None:
    op.drop_table("chunk_entity_links")
    op.drop_table("knowledge_chunks")
    op.drop_table("memory_routines")
    op.drop_table("memory_episodes")
    op.drop_table("user_constraints")
    op.drop_table("explicit_dislikes")
    op.drop_table("explicit_preferences")
    op.drop_table("memory_entity_links")
    op.drop_table("knowledge_edges")
    op.drop_table("knowledge_entities")
    op.drop_table("conversation_turns")
    op.drop_table("memory_entries")
    
    op.execute("DROP TYPE IF EXISTS memory_status")
