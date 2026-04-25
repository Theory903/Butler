-- Multi-tenant Migration Step 1: Add tenant_id columns to existing tables
-- This adds tenant_id UUID columns to all tenant-owned tables

-- Add tenant_id columns to memory tables
ALTER TABLE memory_entries ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT uuid_generate_v4();
ALTER TABLE conversation_turns ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT uuid_generate_v4();
ALTER TABLE knowledge_entities ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT uuid_generate_v4();
ALTER TABLE knowledge_edges ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT uuid_generate_v4();
ALTER TABLE explicit_preferences ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT uuid_generate_v4();
ALTER TABLE explicit_dislikes ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT uuid_generate_v4();
ALTER TABLE user_constraints ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT uuid_generate_v4();
ALTER TABLE memory_episodes ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT uuid_generate_v4();
ALTER TABLE memory_routines ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT uuid_generate_v4();
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT uuid_generate_v4();

-- Add tenant_id columns to tool tables
ALTER TABLE tool_executions ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT uuid_generate_v4();

-- Add tenant_id columns to orchestrator tables
ALTER TABLE workflows ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT uuid_generate_v4();

-- Create tenant-specific tables that don't exist yet
CREATE TABLE IF NOT EXISTS tenant_credentials (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    tenant_slug TEXT UNIQUE,
    provider TEXT NOT NULL,
    credential_encrypted TEXT NOT NULL,
    credential_metadata JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    rotated_at TIMESTAMPTZ,
    UNIQUE (tenant_id, provider)
);

CREATE TABLE IF NOT EXISTS usage_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    account_id UUID NOT NULL,
    user_id UUID,
    request_id UUID NOT NULL,
    session_id TEXT,
    provider TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    quantity NUMERIC NOT NULL,
    unit TEXT NOT NULL,
    cost_usd NUMERIC NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    account_id UUID NOT NULL,
    user_id UUID,
    request_id UUID NOT NULL,
    session_id TEXT,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    resource TEXT,
    action TEXT NOT NULL,
    outcome TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}',
    ip_address TEXT,
    user_agent TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Rename approval_requests to workflow_approval_requests if it exists and workflow_approval_requests doesn't
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'approval_requests' AND table_schema = 'public') 
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'workflow_approval_requests' AND table_schema = 'public') THEN
        ALTER TABLE approval_requests RENAME TO workflow_approval_requests;
    END IF;
END $$;

-- Add tenant_id to approval_requests/workflow_approval_requests
ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT uuid_generate_v4();
ALTER TABLE workflow_approval_requests ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT uuid_generate_v4();

-- Update indexes to include tenant_id for better query performance
CREATE INDEX IF NOT EXISTS ix_memory_entries_tenant_id ON memory_entries(tenant_id);
CREATE INDEX IF NOT EXISTS ix_conversation_turns_tenant_id ON conversation_turns(tenant_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_entities_tenant_id ON knowledge_entities(tenant_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_edges_tenant_id ON knowledge_edges(tenant_id);
CREATE INDEX IF NOT EXISTS ix_tool_executions_tenant_id ON tool_executions(tenant_id);
CREATE INDEX IF NOT EXISTS ix_workflows_tenant_id ON workflows(tenant_id);
CREATE INDEX IF NOT EXISTS ix_usage_events_tenant_id ON usage_events(tenant_id);
CREATE INDEX IF NOT EXISTS ix_audit_events_tenant_id ON audit_events(tenant_id);

-- Update unique constraints to include tenant_id
-- This ensures data isolation between tenants
ALTER TABLE memory_entries DROP CONSTRAINT IF EXISTS memory_entries_account_id_key;
ALTER TABLE memory_entries ADD CONSTRAINT memory_entries_tenant_account_key UNIQUE (tenant_id, account_id, id);
