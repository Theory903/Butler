# Butler Production Architecture - Phased Scalability

## Corrected Target Metrics

### Realistic Scale Targets

Replace fantasy "1M concurrent users" with actual SaaS metrics:

- **Phase 1 (MVP)**: 100-1,000 users, 50 RPS, <$500/month infra
- **Phase 2 (Early Paid)**: 1,000-10,000 users, 500 RPS, <$3K/month infra
- **Phase 3 (Real SaaS)**: 10,000-100,000 users, 2K RPS, <$20K/month infra
- **Phase 4 (1M Registered)**: 1M registered, 50K+ DAU, 10K RPS peak, $20K-$150K/month infra

### Phase 4 (1M Registered) Detailed Metrics

- **Registered users**: 1,000,000
- **Monthly active users**: 100,000 to 300,000
- **Daily active users**: 20,000 to 75,000
- **Concurrent active sessions**: 5,000 to 25,000
- **Peak API RPS**: 2,000 to 10,000
- **Streaming sessions**: 1,000 to 10,000
- **P95 latency**:
  - non-LLM API: <300ms
  - cached/simple chat: <1.5s
  - tool workflow: <5s
  - deep reasoning/research: async/background

## Architecture Overview - Service Planes

Instead of 21 flat services, group them into planes for cleaner boundaries:

### Edge Plane
- gateway
- auth
- realtime

### Intelligence Plane
- orchestrator
- ml
- search
- memory

### Execution Plane
- tools
- workflow
- workspace
- cron
- plugin_ops

### Modality Plane
- audio
- vision
- meetings
- communication
- calendar
- device

### Security / SaaS Plane
- tenant
- security

### Product Experience Plane
- chat

## Correct Butler Runtime Flow

```
Client
  → Gateway
  → Auth
  → TenantResolver
  → RateLimit / Quota
  → ButlerEnvelope
  → Orchestrator
  → Memory Context Builder
  → ML Runtime / Planner
  → ToolExecutor / Search / Workflow
  → Approval if needed
  → Memory Writeback
  → Realtime Stream / Response
  → Audit + Metering
```

### Non-negotiable Rules

- Gateway never calls Memory directly
- Gateway never calls Tools directly
- Tools never call ML directly unless routed through Orchestrator or ToolExecutor policy
- Hermes tools never execute directly
- ML providers never get called outside MLRuntime
- All tenant-owned operations require TenantContext

## Database Scaling - Corrected Configuration

### Safe PostgreSQL Configuration

The previous config was too large and dangerous. work_mem = 256MB with many connections can detonate RAM.

**Safe starting production config:**

```sql
shared_buffers = '16GB'
effective_cache_size = '48GB'
work_mem = '16MB'
maintenance_work_mem = '1GB'
max_connections = 300
max_worker_processes = 16
max_parallel_workers_per_gather = 4
max_parallel_workers = 16
```

### PgBouncer Configuration

Use PgBouncer for connection pooling:

- PgBouncer max client connections: 5000
- Postgres max connections: 300
- Pool mode: transaction

### Scaling Plan

Phase 1: single primary + read replica
Phase 2: partition high-volume tables by tenant_id/hash and time
Phase 3: add Citus or application-level sharding
Phase 4: dedicated enterprise shards

### Tables to Partition Early

- conversation_turns
- memory_entries
- tenant_usage_events
- tenant_audit_events
- tool_executions
- events

## Redis Strategy - Corrected

Redis should NOT hold all important state. Use it for:

- session hot cache
- rate limits
- locks
- stream buffers
- idempotency cache
- presence

Postgres should hold:

- durable sessions
- usage
- audit
- approvals
- memory truth
- workflow state

### Redis Configuration

- Redis Cluster: 6 nodes (3 master + 3 replica)
- Memory: 64GB per node
- Persistence: AOF with fsync every second
- Connection Pooling: 50 connections per pod
- Cache Eviction: allkeys-lru with 24h TTL

### Cache Strategy

- Session Cache: Redis (7-day TTL)
- Memory Cache: Redis (24h TTL)
- Embedding Cache: Redis (7-day TTL)
- Rate Limiting: Redis (sliding window)
- Search Results: Redis (1h TTL)

## Queue Strategy - Corrected

Don't overbuild with Kafka early. Use phased approach:

### Phase 1 (MVP)
- Redis Queue / Dramatiq for task execution
- Simple retry logic
- Background jobs

### Phase 2 (Early Paid)
- Add Redpanda for audit events
- Usage metering streams
- Memory indexing

### Phase 3 (Real SaaS)
- Kafka / Redpanda:
  - audit events
  - usage metering
  - memory indexing
  - event streams
  - analytics
- RabbitMQ / Celery / Dramatiq:
  - task execution
  - retries
  - background jobs

Running Kafka before product-market fit is how founders discover new kinds of loneliness.

## ML Scaling - Corrected

8x A100 for early Butler is overkill unless you are self-hosting major models.

### Margin-First Approach

**Edge/local:**
- Gemma / small local models for classification, routing, summarization, offline assistant

**Cheap cloud:**
- fast model for normal chats

**Premium cloud:**
- Claude / Gemini / GPT only for hard reasoning

**Batch/offline:**
- embeddings
- memory summarization
- graph extraction

### GPU Cluster Only When

- Usage is predictable
- Cloud API margin is bad
- Latency needs justify it
- You have enough paid users

### Early Architecture

- No dedicated A100 cluster at launch
- Use provider APIs + local edge models + selective batch jobs
- Track margin per request from day one

### Model Routing Strategy

- T0: local/edge model
- T1: cheap fast model
- T2: balanced cloud model
- T3: premium reasoning model
- T4: premium + approval + audit

## Rate Limiting - Multi-Dimensional

Use multi-dimensional rate limits:

- system
- tenant
- account
- user
- session
- IP
- tool
- model
- provider
- risk tier

### Example Limits

**Free:**
- chat: 20/day
- premium model: 0/day
- workflows: 1 active
- storage: 2GB
- tools: read-only mostly

**Pro:**
- chat: 1000/month or fair-use
- workflows: 5 active
- sandbox: limited
- storage: 25GB

**Operator:**
- higher automation
- browser/code tools
- more storage
- premium model credits

**Enterprise:**
- custom quotas
- BYOK
- audit export
- dedicated isolation

## Cost Estimation - Phased Model

### Stage 0: Solo MVP

Users: 100 to 1,000
Infra: $100 to $500/month
Use:
- single VPS or small cloud app
- managed Postgres
- managed Redis
- object storage
- external model APIs

### Stage 1: Early Paid Users

Users: 1,000 to 10,000
Infra: $500 to $3,000/month
Use:
- containerized backend
- managed Postgres + Redis
- background workers
- model cost controls

### Stage 2: Real SaaS

Users: 10,000 to 100,000
Infra: $3,000 to $20,000/month
Use:
- Kubernetes or simpler managed container platform
- read replicas
- queue
- observability
- CDN

### Stage 3: 1M Registered Users

Users: 1M registered, 50K+ DAU
Infra: $20,000 to $150,000+/month
Depends heavily on:
- LLM usage
- voice usage
- storage
- deep research
- video/audio workloads

The real killer is not Kubernetes. It is LLM + voice + browser automation cost.

## Production-Readiness Checklist

### P0: Security
- TenantContext everywhere
- RLS on tenant-owned tables
- Redis namespace wrapper only
- CredentialBroker only
- ToolExecutor only
- MLRuntime only
- audit + metering append-only

### P1: Runtime
- Gateway thin
- Orchestrator owns execution
- LangGraph durable workflows
- Tool approvals
- Memory context builder
- Streaming response bridge

### P2: Reliability
- circuit breakers
- retry budgets
- idempotency
- graceful degradation
- background queues
- health probes

### P3: Scale
- PgBouncer
- Redis cluster
- read replicas
- queue workers
- autoscaling
- partitioning

### P4: Margin
- model router
- edge model path
- premium model budget
- per-user cost ledger
- plan limits

## Implementation Priority

### Best Next Implementation Order

1. TenantContext + ButlerEnvelope
2. ToolExecutor tenant enforcement
3. MemoryService tenant enforcement
4. MLRuntime tenant enforcement
5. Gateway request flow
6. Orchestrator LangGraph path
7. Hermes implementation wrappers
8. Sandbox/workspace manager
9. Metering + pricing
10. Load testing

### Key Files to Inspect

- backend/core/envelope.py
- backend/services/tenant/context.py
- backend/services/tools/executor.py

Those three decide whether Butler becomes a clean AI OS or a beautifully documented accident.

## Final Architecture Summary

### Butler Core
- Gateway
- Auth
- Tenant
- Orchestrator
- Memory
- ML
- Tools
- Search

### Butler Execution
- Workflow
- Workspace
- Cron
- Plugin Ops

### Butler Modalities
- Audio
- Vision
- Meetings
- Calendar
- Communication
- Device

### Butler Delivery
- Realtime
- Chat

### Butler Protection
- Security
- Audit
- Metering
- Approvals
- Sandbox

## Success Criteria

- Handle 10K RPS with P95 <1.5s (cached/simple chat)
- Support 1M registered users (50K+ DAU)
- 99.9% uptime SLA
- Database query P95 <100ms
- Redis cache hit ratio >80%
- GPU utilization >70% (if using dedicated GPUs)
- Error rate <0.1%
- Auto-scaling responds within 30s
- Margin per request tracked from day one

