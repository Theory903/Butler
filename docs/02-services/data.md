# Operational Data Service - Technical Specification

> **For:** Engineering, Data Team  
> **Status:** Active (v3.1) [ACTIVE: Postgres, Partitioning, Outbox | GAPS: Automated Archival]
> **Version:** 3.1  
> **Reference:** Butler transactional data platform - identity, runtime state, audit-grade operational truth

---

## 0. Implementation Status

| Phase | Component | Status | Description |
|-------|-----------|--------|-------------|
| 1 | **Identity Domain** | [IMPLEMENTED] | Accounts, Identities, Sessions |
| 2 | **Runtime Domain** | [IMPLEMENTED] | Workflows, Tasks, Approvals |
| 3 | **Audit Domain** | [IMPLEMENTED] | Tool Executions, Audit Events |
| 4 | **Outbox Pattern** | [IMPLEMENTED] | Transactional event propagation |
| 5 | **Partitioning** | [IMPLEMENTED] | Monthly Range partitioning |
| 6 | **Auto-Archival** | [STUB] | Cold storage rotation |

---

## 1. Service Overview

### 1.1 Purpose
The Operational Data Service is Butler's **transactional backbone** for identity, runtime state, and audit-grade operational truth.

This is NOT a generic "Data service" or "Postgres wrapper." It is the operational data platform owning:
- Identity/session domain
- Workflow/task runtime domain
- Tool/audit domain
- Config/reference domain
- Event export domain

### 1.2 Architecture Layers

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Connection** | PgBouncer | Transaction pooling, multiplexing |
| **Primary** | PostgreSQL | Writes, transactions, schema truth |
| **Replicas** | PostgreSQL | Bounded-staleness reads |
| **Cache** | Redis | Hot state, coordination |

### 1.3 Boundaries

| Service | Data Ownership |
|---------|---------------|
| Auth | Account, identity, session truth |
| Orchestrator | Workflow, task, execution truth |
| Tools | Tool execution, audit truth |
| Memory | Memory vector/entity truth |
| Device | Device registry truth |
| **Data** | Schema, migrations, operational query plane |

**Service does NOT own:**
- Vector search (Qdrant)
- Relationship graphs (Neo4j)
- Cache/coordination (Redis)
- Domain write authority (domain services own their data)

### 1.4 Hermes Library Integration
Data is **not** a direct Hermes consumer. Data may mirror compatibility-backed session/event records for legacy compatibility, but persistence ownership remains Butler Data.

---

## 2. Domain Schema Architecture

### 2.1 Domain Split

Tables are organized by domain, NOT as a single soup:

```
Identity/Auth Domain
├── accounts
├── identities
├── sessions
├── devices
├── refresh_token_families

Runtime Domain
├── workflows
├── tasks
├── task_nodes
├── task_transitions
├── approvals
├── execution_events

Tool/Audit Domain
├── tool_executions
├── tool_verifications
├── audit_events
├── canonical_events

Config Domain
├── user_settings
├── feature_flags
├── policy_overrides
└── reference_data
```

---

## 3. Identity/Auth Domain Schema

### 3.1 Accounts

```sql
CREATE TABLE accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(355) UNIQUE NOT NULL,  -- RFC 5321
    name VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    settings JSONB DEFAULT '{}',
    
    CONSTRAINT valid_email CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
);

CREATE INDEX idx_accounts_email ON accounts(email) WHERE deleted_at IS NULL;
CREATE INDEX idx_accounts_status ON accounts(status);
CREATE INDEX idx_accounts_created ON accounts(created_at);
```

### 3.2 Identities

```sql
CREATE TABLE identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    identity_type VARCHAR(50) NOT NULL,  -- password, passkey, oauth, saml
    identifier VARCHAR(500) NOT NULL,  -- email, subject, principal
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    
    UNIQUE(account_id, identity_type, identifier)
);

CREATE INDEX idx_identities_account ON identities(account_id);
CREATE INDEX idx_identities_identifier ON identities(identifier);
```

### 3.3 Sessions (Richer than v1)

```sql
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    device_id UUID,  -- Links to device registry
    device_platform VARCHAR(30),  -- mobile, web, watch, voice
    channel VARCHAR(20) NOT NULL DEFAULT 'mobile',  -- mobile, web, watch, voice, internal
    
    -- Auth context
    assurance_level VARCHAR(20) NOT NULL DEFAULT 'aal1',  -- aal1, aal2, aal3_ish
    session_class VARCHAR(30) NOT NULL DEFAULT 'interactive_user',  -- interactive_user, tool_delegation, api
    
    -- Token family reference
    token_family_id UUID,
    
    -- Lifecycle
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    revocation_reason VARCHAR(100),
    
    -- Context
    ip_address INET,
    user_agent TEXT,
    geolocation VARCHAR(100),
    
    -- State
    risk_score FLOAT DEFAULT 0.0,
    risk_state JSONB DEFAULT '{}',
    
    -- Linkage
    active_workflow_id UUID,
    active_stream_id UUID
);

CREATE INDEX idx_sessions_account ON sessions(account_id, created_at DESC);
CREATE INDEX idx_sessions_device ON sessions(device_id) WHERE revoked_at IS NULL;
CREATE INDEX idx_sessions_token_family ON sessions(token_family_id);
CREATE INDEX idx_sessions_expires ON sessions(expires_at) WHERE revoked_at IS NULL;
CREATE INDEX idx_sessions_workflow ON sessions(active_workflow_id);
```

### 3.4 Refresh Token Families

```sql
CREATE TABLE refresh_token_families (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rotated_at TIMESTAMPTZ,
    compromised_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    reason VARCHAR(100)
);

CREATE INDEX idx_token_families_account ON refresh_token_families(account_id);
```

---

## 4. Runtime Domain Schema

### 4.1 Workflows

```sql
CREATE TABLE workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    definition JSONB NOT NULL,  -- Plan schema
    version VARCHAR(20) NOT NULL DEFAULT 'v1',
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active, archived, deleted
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Metadata
    tags JSONB DEFAULT '[]',
    settings JSONB DEFAULT '{}'
);

CREATE INDEX idx_workflows_account ON workflows(account_id, created_at DESC);
CREATE INDEX idx_workflows_status ON workflows(status);
```

### 4.2 Tasks (Durable Execution)

```sql
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID REFERENCES workflows(id) ON DELETE SET NULL,
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    
    -- Task identity
    task_type VARCHAR(50) NOT NULL,  -- planning, execution, approval, handoff, compensation
    parent_task_id UUID REFERENCES tasks(id),
    
    -- State machine
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    state_data JSONB DEFAULT '{}',
    
    -- Planning
    plan_node_id VARCHAR(100),
    plan_path JSONB,  -- Full plan for this task
    
    -- Execution
    input_payload JSONB DEFAULT '{}',
    output_payload JSONB DEFAULT '{}',
    error_payload JSONB,
    error_message TEXT,
    
    -- Timing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    interrupted_at TIMESTAMPTZ,
    resume_count INT DEFAULT 0,
    
    -- Approval linkage
    approval_request_id UUID,
    
    -- Compensation
    compensation_task_id UUID REFERENCES tasks(id),
    compensating_for_task_id UUID REFERENCES tasks(id)
);

CREATE INDEX idx_tasks_workflow ON tasks(workflow_id, created_at DESC);
CREATE INDEX idx_tasks_account ON tasks(account_id, created_at DESC);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_parent ON tasks(parent_task_id);
CREATE INDEX idx_tasks_approval ON tasks(approval_request_id);
```

### 4.3 Task Nodes (Plan Structure)

```sql
CREATE TABLE task_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    node_id VARCHAR(100) NOT NULL,
    node_type VARCHAR(30) NOT NULL,  -- action, conditional, parallel, approval, handoff, tool
    
    -- Node definition
    definition JSONB NOT NULL,
    
    -- State
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    result JSONB,
    error TEXT,
    
    -- Timing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX idx_task_nodes_task_node ON task_nodes(task_id, node_id);
CREATE INDEX idx_task_nodes_status ON task_nodes(status);
```

### 4.4 Task Transitions (Event-Sourced Trail)

```sql
CREATE TABLE task_transitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    
    -- Transition
    from_status VARCHAR(30),
    to_status VARCHAR(30) NOT NULL,
    trigger VARCHAR(50) NOT NULL,  -- system, user, approval, timeout, error
    
    -- Context
    actor_id UUID,  -- account_id who triggered
    actor_type VARCHAR(20),  -- user, system, agent
    correlation_id UUID,  -- Links to Orchestrator workflow correlation
    
    -- Payload
    payload JSONB DEFAULT '{}',
    error_message TEXT,
    
    -- Timing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (created_at);

-- Partition by month
CREATE TABLE task_transitions_2026_04 PARTITION OF task_transitions
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');

CREATE INDEX idx_task_transitions_task ON task_transitions(task_id, created_at DESC);
CREATE INDEX idx_task_transitions_status ON task_transitions(to_status, created_at);
```

### 4.5 Approval Requests

```sql
CREATE TABLE approval_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    
    -- Approval details
    approval_type VARCHAR(30) NOT NULL,  -- user_confirm, step_up_auth, restricted
    requested_by VARCHAR(50) NOT NULL,  -- system, policy
    request_reason TEXT,
    
    -- State
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, approved, denied, expired
    response_message TEXT,
    
    -- Security context
    required_assurance VARCHAR(20),
    auth_method_used VARCHAR(30),
    
    -- Timing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    responded_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    
    -- Linkage
    step_up_session_id UUID REFERENCES sessions(id)
);

CREATE INDEX idx_approval_requests_task ON approval_requests(task_id);
CREATE INDEX idx_approval_requests_account ON approval_requests(account_id, created_at DESC);
CREATE INDEX idx_approval_requests_status ON approval_requests(status, expires_at);
```

---

## 5. Tool/Audit Domain Schema

### 5.1 Tool Executions

```sql
CREATE TABLE tool_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    
    -- Tool identity
    tool_name VARCHAR(100) NOT NULL,
    tool_version VARCHAR(20),
    
    -- Execution context
    idempotency_key VARCHAR(100),
    risk_tier VARCHAR(10) NOT NULL,  -- l0, l1, l2, l3
    
    -- Input/Output
    input_payload JSONB DEFAULT '{}',
    output_payload JSONB DEFAULT '{}',
    
    -- Verification
    verification_mode VARCHAR(30),
    verified_at TIMESTAMPTZ,
    verification_result JSONB,
    
    -- Compensation
    compensation_status VARCHAR(20),
    compensation_task_id UUID REFERENCES tasks(id),
    
    -- Outcome
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, running, completed, failed, compensating
    error_message TEXT,
    
    -- Timing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    latency_ms INTEGER
);

CREATE INDEX idx_tool_executions_task ON tool_executions(task_id);
CREATE INDEX idx_tool_executions_account ON tool_executions(account_id, created_at DESC);
CREATE INDEX idx_tool_executions_tool ON tool_executions(tool_name, created_at DESC);
CREATE INDEX idx_tool_executions_idempotency ON tool_executions(idempotency_key) WHERE idempotency_key IS NOT NULL;
```

### 5.2 Audit Events (Partitioned)

```sql
CREATE TABLE audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Canonical envelope
    event_version VARCHAR(10) NOT NULL DEFAULT 'v1',
    event_family VARCHAR(30) NOT NULL,  -- auth, session, workflow, task, tool, device, system
    event_type VARCHAR(50) NOT NULL,
    
    -- Actor context
    actor_id UUID,  -- account_id
    actor_type VARCHAR(20),  -- user, agent, system, service
    
    -- Session context
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
    device_id UUID,
    channel VARCHAR(20),
    
    -- Resource context
    resource_type VARCHAR(30),
    resource_id UUID,
    
    -- Correlation
    task_id UUID,
    workflow_id UUID,
    trace_id UUID,
    correlation_id UUID,
    
    -- Event data
    action VARCHAR(100) NOT NULL,
    outcome VARCHAR(20) NOT NULL,  -- success, failure, denied
    reason_code VARCHAR(50),
    risk_score FLOAT,
    
    -- Sensitivity
    sensitivity_class VARCHAR(20) DEFAULT 'normal',  -- normal, elevated, restricted
    
    -- Payload
    event_data JSONB DEFAULT '{}',
    
    -- Timing
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (observed_at);

-- Monthly partitions
CREATE TABLE audit_events_2026_04 PARTITION OF audit_events
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');

CREATE INDEX idx_audit_actor ON audit_events(actor_id, observed_at DESC);
CREATE INDEX idx_audit_session ON audit_events(session_id, observed_at DESC);
CREATE INDEX idx_audit_resource ON audit_events(resource_type, resource_id);
CREATE INDEX idx_audit_task ON audit_events(task_id);
CREATE INDEX idx_audit_trace ON audit_events(trace_id);
CREATE INDEX idx_audit_family_type ON audit_events(event_family, event_type, observed_at);
```

---

## 6. Outbox Pattern

### 6.1 Transactional Outbox Table

```sql
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Event identity
    aggregate_type VARCHAR(50) NOT NULL,  -- account, session, task, tool_execution
    aggregate_id UUID NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    
    -- Payload
    payload JSONB NOT NULL,
    
    -- Routing
    target_topic VARCHAR(100) NOT NULL,  -- analytics, ml_features, realtime, notifications
    priority INTEGER DEFAULT 0,
    
    -- State
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, published, failed
    attempts INTEGER DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    error_message TEXT,
    
    -- Timing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '7 days')
) PARTITION BY RANGE (created_at);

CREATE TABLE outbox_events_2026_04 PARTITION OF outbox_events
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');

CREATE INDEX idx_outbox_pending ON outbox_events(status, created_at) 
    WHERE status = 'pending';
CREATE INDEX idx_outbox_aggregate ON outbox_events(aggregate_type, aggregate_id);
```

### 6.2 Outbox Writer Pattern

```python
async def write_with_outbox(db, aggregate_type, aggregate_id, event_type, payload, target_topic):
    async with db.transaction():
        # 1. Write domain entity
        await db.execute("INSERT INTO tasks (...)", ...)
        
        # 2. Write outbox event (same transaction)
        await db.execute("""
            INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload, target_topic)
            VALUES ($1, $2, $3, $4, $5)
        """, aggregate_type, aggregate_id, event_type, payload, target_topic)
    
    # Async workers read outbox_events, publish to target_topic, mark published
```

---

## 7. Connection & Routing

### 7.1 PgBouncer Configuration

**Important:** Transaction pooling changes client expectations.

```yaml
# pgbouncer.ini
[databases]
butler = host=postgresql-primary port=5432 dbname=butler

[pgbouncer]
pool_mode = transaction  # NOT session
max_client_conn = 1000
default_pool_size = 25
min_pool_size = 10
reserve_pool_size = 5
max_db_connections = 100
max_user_connections = 50

# Prepared statements - disabled for transaction pooling
max_prepared_statements = 0

# Timeouts
query_timeout = 60
idle_transaction_timeout = 60
```

**Compatibility Notes:**
- Transaction pooling is fine for stateless ORM queries
- Session-dependent features (e.g., `SET LOCAL`, temp tables) must be avoided
- Prepared statements are disabled - use parameterized queries instead
- Services needing session semantics bypass PgBouncer to primary

### 7.2 Replica Routing Policy

```python
class ReplicaRouter:
    def __init__(self, primary, replicas, max_lag_seconds=5):
        self.primary = primary
        self.replicas = replicas
        self.max_lag = max_lag_seconds
    
    async def route_read(self, query_context: dict) -> str:
        """
        Route reads based on consistency requirements:
        """
        # Strong consistency → primary
        if query_context.get('consistency') == 'strong':
            return self.primary
        
        # Read-after-write sensitive → primary
        if query_context.get('read_after_write'):
            return self.primary
        
        # Bounded staleness allowed → replica if lag acceptable
        if query_context.get('allow_stale'):
            replica = await self.select_replica_within_lag()
            if replica:
                return replica
            return self.primary  # Fallback to primary if lag too high
        
        # Default → primary
        return self.primary
    
    async def select_replica_within_lag(self) -> str | None:
        """Select replica with acceptable lag"""
        for replica in self.replicas:
            lag = await self.get_replication_lag(replica)
            if lag < self.max_lag:
                return replica
        return None
```

**Consistency Rules:**
| Query Type | Consistency | Route |
|------------|------------|-------|
| Account create | Strong | Primary |
| Session validate | Strong | Primary |
| Task state read | Strong | Primary |
| Workflow list | Bounded | Replica |
| Tool execution history | Bounded | Replica |
| Audit event query | Bounded | Replica |
| Analytics aggregation | Eventual | Replica |

---

## 8. Row-Level Security (RLS)

### 8.1 RLS Policy Tables

```sql
-- Enable RLS on account-scoped tables
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE tool_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own data
CREATE POLICY session_tenant_policy ON sessions
    USING (account_id = current_setting('app.current_account_id')::uuid);

CREATE POLICY task_tenant_policy ON tasks
    USING (account_id = current_setting('app.current_account_id')::uuid);

CREATE POLICY tool_exec_tenant_policy ON tool_executions
    USING (account_id = current_setting('app.current_account_id')::uuid);

-- Audit events - more restrictive
CREATE POLICY audit_tenant_policy ON audit_events
    USING (
        actor_id = current_setting('app.current_account_id')::uuid
        OR sensitivity_class = 'normal'
    );
```

### 8.2 Service Role Bypass

For services that need cross-account access:

```sql
-- Service roles bypass RLS
ALTER TABLE sessions FORCE ROW LEVEL SECURITY;

CREATE POLICY session_service_policy ON sessions
    USING (
        current_setting('app.auth_role') = 'service'
    );
```

---

## 9. Partitioning & Retention

### 9.1 Partition Strategy

```sql
-- Partitioned tables use declarative partitioning
-- Partition key chosen per access pattern

-- task_transitions: RANGE on created_at (append-heavy, time-range queries)
-- audit_events: RANGE on observed_at (append-heavy, time-range queries)  
-- outbox_events: RANGE on created_at (append-heavy, pending→published lifecycle)
```

### 9.2 Partition Lifecycle

| Table | Partition Granularity | Retention | Archive After |
|--------|---------------------|-----------|----------------|
| task_transitions | Monthly | 1 year | 90 days to cold storage |
| audit_events | Monthly | 3 years | 1 year to cold storage |
| outbox_events | Monthly | 7 days | N/A (auto-delete) |
| tool_executions | None (partitioned by account_id if scale) | 90 days | N/A |

### 9.3 Partition Management

```python
class PartitionManager:
    async def ensure_partition_exists(self, table, partition_date):
        # Check if partition exists, create if not
        partition_name = f"{table}_{partition_date:%Y_%m}"
        
        # Run at start of each month
        await self.run_migration(f"""
            CREATE TABLE IF NOT EXISTS {partition_name} 
            PARTITION OF {table} 
            FOR VALUES FROM ({partition_date}) TO ({next_month})
        """)
    
    async def drop_old_partitions(self, table, retention_days):
        cutoff = now() - retention_days
        # Archive to cold storage before drop
        await self.archive_partition(table, cutoff)
        await self.drop_partition(table, cutoff)
```

---

## 10. JSONB Discipline

### 10.1 JSONB Usage Rules

| Field | Type | Index | When to Promote |
|-------|------|-------|----------------|
| settings | JSONB | GIN | When query patterns stabilize |
| context | JSONB | Expression | When specific keys queried |
| payload | JSONB | None | Keep flexible |
| state_data | JSONB | GIN | When hot keys identified |
| event_data | JSONB | None | Keep flexible |

### 10.2 GIN Indexes

```sql
-- For JSONB fields with key-value lookups
CREATE INDEX idx_accounts_settings_gin ON accounts USING GIN(settings);
CREATE INDEX idx_tasks_state_gin ON tasks USING GIN(state_data);

-- For specific key existence
CREATE INDEX idx_sessions_context_client ON sessions((context->>'client_id'));
```

---

## 11. Migration Governance

### 11.1 Migration Rules

1. **Backward compatibility first:** No breaking changes without migration path
2. **Zero-downtime migrations:** Use `CREATE INDEX CONCURRENTLY`, `ALTER TABLE ADD COLUMN`
3. **Rollback plan:** Document how to revert
4. **Data migration:** Separate schema + data migrations

### 11.2 Migration Template

```sql
-- 001_add_sessions_assurance_level.sql
-- Description: Add assurance_level to sessions for Auth v2.0
-- Backward Compatible: YES (adds nullable column)
-- Downtime Required: NO (use ALTER TABLE ADD COLUMN)
-- Rollback: DROP COLUMN IF EXISTS assurance_level

BEGIN;

-- Add column nullable first
ALTER TABLE sessions 
ADD COLUMN IF NOT EXISTS assurance_level VARCHAR(20) DEFAULT 'aal1';

-- Backfill existing rows (if needed)
UPDATE sessions 
SET assurance_level = 'aal1' 
WHERE assurance_level IS NULL;

-- Add constraint after backfill
ALTER TABLE sessions 
ALTER COLUMN assurance_level SET NOT NULL;

COMMIT;
```

---

## 12. Observability

### 12.1 Key Metrics

| Metric | Type | Alert Threshold |
|--------|------|----------------|
| pg_pool.connections_active | gauge | >80% |
| pg_query.latency_p99 | histogram | >500ms |
| pg_replication.lag_seconds | gauge | >5s |
| pg_partition.lag_days | gauge | >retention |
| pg_bloat.ratio | gauge | >1.2 |
| outbox.pending_count | gauge | >1000 |

### 12.2 Query Performance

```sql
-- Enable pg_stat_statements
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Query analysis
SELECT 
    query,
    calls,
    mean_time,
    total_time,
    rows
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 20;
```

---

## 13. Runbook Quick Reference

### 13.1 High Connection Usage

```bash
# Check active connections
kubectl exec -it postgresql-0 -- psql -U postgres -c "SELECT count(*) FROM pg_stat_activity"

# Kill idle >15min
kubectl exec -it postgresql-0 -- psql -U postgres -c "
    SELECT pg_terminate_backend(pid) 
    FROM pg_stat_activity 
    WHERE state = 'idle' 
    AND query_start < now() - interval '15 minutes'
"
```

### 13.2 Replication Lag

```bash
# Check lag
kubectl exec -it postgresql-0 -- psql -U postgres -c "
    SELECT now() - pg_last_xact_replay_timestamp() AS lag
"

# Restart lagging replica
kubectl delete pod postgresql-replica-0
```

### 13.3 Partition Management

```bash
# Check partitions
kubectl exec -it postgresql-0 -- psql -U postgres -c "
    SELECT schemaname, tablename, partitionname 
    FROM pg_tables 
    WHERE tablename LIKE 'audit_events%'
"

# Create next month partition
kubectl exec -it postgresql-0 -- psql -U postgres -c "
    CREATE TABLE audit_events_2026_05 PARTITION OF audit_events
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01')
"
```

---

*Document owner: Data Team*  
*Last updated: 2026-04-18*  
*Version: 2.0 (Implementation-ready)*

(End of file - 497 lines)