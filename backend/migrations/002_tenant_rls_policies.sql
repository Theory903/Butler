-- Multi-tenant Row Level Security (RLS) Policies
-- This script enables RLS on tenant-owned tables and creates tenant isolation policies
-- All tenant-owned queries must include tenant_id filter enforced by RLS

-- Enable RLS on tenant-owned tables
ALTER TABLE memory_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_turns ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE explicit_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE explicit_dislikes ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_constraints ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_episodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_routines ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE tool_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflows ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_approval_requests ENABLE ROW LEVEL SECURITY;

-- Tenant-specific RLS policies

-- Memory entries: tenant can only see their own entries
CREATE POLICY memory_entries_tenant_isolation
ON memory_entries
USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- Conversation turns: tenant can only see their own turns
CREATE POLICY conversation_turns_tenant_isolation
ON conversation_turns
USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- Knowledge entities: tenant can only see their own entities
CREATE POLICY knowledge_entities_tenant_isolation
ON knowledge_entities
USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- Knowledge edges: tenant can only see their own edges
CREATE POLICY knowledge_edges_tenant_isolation
ON knowledge_edges
USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- Explicit preferences: tenant can only see their own preferences
CREATE POLICY explicit_preferences_tenant_isolation
ON explicit_preferences
USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- Explicit dislikes: tenant can only see their own dislikes
CREATE POLICY explicit_dislikes_tenant_isolation
ON explicit_dislikes
USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- User constraints: tenant can only see their own constraints
CREATE POLICY user_constraints_tenant_isolation
ON user_constraints
USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- Memory episodes: tenant can only see their own episodes
CREATE POLICY memory_episodes_tenant_isolation
ON memory_episodes
USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- Memory routines: tenant can only see their own routines
CREATE POLICY memory_routines_tenant_isolation
ON memory_routines
USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- Knowledge chunks: tenant can only see their own chunks
CREATE POLICY knowledge_chunks_tenant_isolation
ON knowledge_chunks
USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- Tool executions: tenant can only see their own executions
CREATE POLICY tool_executions_tenant_isolation
ON tool_executions
USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- Workflows: tenant can only see their own workflows
CREATE POLICY workflows_tenant_isolation
ON workflows
USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- Workflow approval requests: tenant can only see their own approvals
CREATE POLICY workflow_approval_requests_tenant_isolation
ON workflow_approval_requests
USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- Tenant-specific tables (already have tenant_id, add RLS for safety)
ALTER TABLE tenant_credentials ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_credentials_tenant_isolation
ON tenant_credentials
USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY usage_events_tenant_isolation
ON usage_events
USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY audit_events_tenant_isolation
ON audit_events
USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

ALTER TABLE approval_requests ENABLE ROW LEVEL SECURITY;
CREATE POLICY approval_requests_tenant_isolation
ON approval_requests
USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- Grant INSERT, UPDATE, DELETE permissions for tenant operations
-- These policies allow tenants to modify their own data
ALTER TABLE memory_entries FORCE ROW LEVEL SECURITY;
ALTER TABLE conversation_turns FORCE ROW LEVEL SECURITY;
ALTER TABLE knowledge_entities FORCE ROW LEVEL SECURITY;
ALTER TABLE knowledge_edges FORCE ROW LEVEL SECURITY;
ALTER TABLE explicit_preferences FORCE ROW LEVEL SECURITY;
ALTER TABLE explicit_dislikes FORCE ROW LEVEL SECURITY;
ALTER TABLE user_constraints FORCE ROW LEVEL SECURITY;
ALTER TABLE memory_episodes FORCE ROW LEVEL SECURITY;
ALTER TABLE memory_routines FORCE ROW LEVEL SECURITY;
ALTER TABLE knowledge_chunks FORCE ROW LEVEL SECURITY;
ALTER TABLE tool_executions FORCE ROW LEVEL SECURITY;
ALTER TABLE workflows FORCE ROW LEVEL SECURITY;
ALTER TABLE workflow_approval_requests FORCE ROW LEVEL SECURITY;
ALTER TABLE tenant_credentials FORCE ROW LEVEL SECURITY;
ALTER TABLE usage_events FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;
ALTER TABLE approval_requests FORCE ROW LEVEL SECURITY;
