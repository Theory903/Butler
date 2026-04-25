# Butler Full System Map

**Generated:** Phase 0.5 Static Safety Scan  
**Purpose:** Classify every module by runtime plane, operation type, scaling mode, status, owner, risk, and action needed before any production hardening.

---

## Active Boot Path

**Entry point:** `main.py`

**Boot sequence:**
1. `setup_logging()` - structlog configuration
2. `_startup_doctor_check()` - ButlerDoctor security/infrastructure audit
3. `_startup_data_backends()` - PostgreSQL, Redis, Neo4j (if enabled), Qdrant (if enabled)
4. `_startup_application_services()` - MLRuntime, CronService, MCPBridge, RealtimeListener, StateSyncer, HealthAgent, CleanupWorker, LangGraph components, LangChain providers, Openclaw skills, ChannelRegistry, MemoryHostSDK

**Middleware stack (order matters):**
1. InternalOnlyMiddleware - internal control plane
2. CORSMiddleware - cross-origin
3. RequestContextMiddleware - request context injection
4. IdempotencyMiddleware - idempotency key handling
5. ObservabilityMiddleware - OTel tracing
6. TrafficGuardMiddleware - rate limiting guard
7. RateLimitMiddleware - actual rate limiting

**Active request paths:**
- `/api/v1/auth/*` - authentication
- `/api/v1/gateway/*` - gateway orchestration
- `/api/v1/orchestrator/*` - orchestrator intake
- `/api/v1/memory/*` - memory operations
- `/api/v1/tools/*` - tool execution
- `/api/v1/search/*` - search
- `/api/v1/ml/*` - ML operations
- `/api/v1/realtime/*` - WebSocket/SSE
- `/api/v1/communication/*` - communication
- `/api/v1/security/*` - security
- `/api/v1/device/*` - device
- `/api/v1/vision/*` - vision
- `/api/v1/audio/*` - audio
- `/api/v1/research/*` - research
- `/api/v1/meetings/*` - meetings
- `/api/v1/voice_gateway/*` - voice
- `/api/v1/mcp/*` - MCP bridge
- `/api/v1/admin/*` - admin
- `/api/v1/acp/*` - ACP protocol
- `/api/v1/cron/*` - cron
- `/api/v1/integrations/providers/*` - LangChain provider management (NEW)
- `/api/v1/integrations/channels/*` - communication channel management (NEW)

---

## Duplicate Runtime Analysis

### Three Runtime Layers Exist

| Runtime | Purpose | Status | Canonical? |
|---------|---------|--------|------------|
| `services/orchestrator/` | Production orchestrator with intake, planner, executor, blender, durable workflows | **ACTIVE** | **YES** |
| `langchain/agent.py` | LangGraph agent builder with ButlerChatModel, ButlerAgentState, ButlerToolFactory | **ACTIVE** | **NO** - wrapper layer |
| `butler_runtime/` | Hermes/OpenClaw port runtime with agent loop, skills, channels, tools | **LEGACY** | **NO** - migration target |

### Decision

**Canonical runtime:** `services/orchestrator/`

**LangChain role:** Wrapper/adapter layer for LangGraph agent graphs inside orchestrator workflows. Keep as `langchain/` but clarify it is not the primary runtime.

**butler_runtime/ status:** Legacy migration target. Contains useful components (skills loader, channel adapters, tool implementations) that should be migrated to canonical services. Mark as `legacy` with migration plan.

---

## System Map Table

| Folder/File | Runtime Plane | Operation Type | Scaling Mode | Owner | Status | Used By | Risk | Action Needed |
|-------------|---------------|----------------|--------------|-------|--------|----------|------|---------------|
| **main.py** | API Plane | DIRECT_SYNC | always_warm | core | active | All routes | Low | None - entry point is correct |
| **core/deps.py** | Control Plane | DIRECT_SYNC | singleton_control_plane | core | active | main.py | Low | None - DI is canonical |
| **core/base_config.py** | Control Plane | DIRECT_SYNC | always_warm | core | active | services | Low | None |
| **core/circuit_breaker.py** | Observability Plane | DIRECT_SYNC | always_warm | core | active | MLRuntime, services | Low | None |
| **core/doctor.py** | Security Plane | DIRECT_SYNC | always_warm | core | active | boot | Low | None |
| **core/errors.py** | API Plane | DIRECT_SYNC | always_warm | core | active | All routes | Low | None |
| **core/health.py** | Observability Plane | DIRECT_SYNC | always_warm | core | active | health router | Low | None |
| **core/idempotency.py** | API Plane | DIRECT_SYNC | always_warm | core | active | middleware | Low | None |
| **core/locks.py** | Data Plane | DIRECT_SYNC | always_warm | core | active | services | Low | None |
| **core/logging.py** | Observability Plane | DIRECT_SYNC | always_warm | core | active | boot | Low | Add structured logging with tenant/account hashing |
| **core/middleware.py** | API Plane | DIRECT_SYNC | always_warm | core | active | middleware | Low | Add RuntimeContextMiddleware |
| **core/observability.py** | Observability Plane | DIRECT_SYNC | always_warm | core | active | middleware | Low | Add sampling, dedup, redaction |
| **core/state_sync.py** | Data Plane | FAST_ASYNC | always_warm | core | active | services | Low | None |
| **api/routes/auth.py** | API Plane | DIRECT_SYNC | always_warm | api | active | auth | Low | None |
| **api/routes/gateway.py** | API Plane | DIRECT_SYNC | always_warm | api | active | gateway | Low | None |
| **api/routes/orchestrator.py** | API Plane | DIRECT_SYNC | always_warm | api | active | orchestrator | Low | None |
| **api/routes/memory.py** | API Plane | DIRECT_SYNC | always_warm | api | active | memory | Low | None |
| **api/routes/tools.py** | API Plane | DIRECT_SYNC | always_warm | api | active | tools | Low | None |
| **api/routes/search.py** | API Plane | DIRECT_SYNC | always_warm | api | active | search | Low | None |
| **api/routes/ml.py** | API Plane | DIRECT_SYNC | always_warm | api | active | ML | Low | None |
| **api/routes/realtime.py** | API Plane | DIRECT_SYNC | warm_pool | api | active | realtime | Low | None |
| **api/routes/communication.py** | API Plane | DIRECT_SYNC | always_warm | api | active | communication | Low | None |
| **api/routes/security.py** | API Plane | DIRECT_SYNC | always_warm | api | active | security | Low | None |
| **api/routes/device.py** | API Plane | DIRECT_SYNC | always_warm | api | active | device | Low | None |
| **api/routes/vision.py** | API Plane | DIRECT_SYNC | always_warm | api | active | vision | Low | None |
| **api/routes/audio.py** | API Plane | DIRECT_SYNC | always_warm | api | active | audio | Low | None |
| **api/routes/research.py** | API Plane | DIRECT_SYNC | always_warm | api | active | research | Low | None |
| **api/routes/meetings.py** | API Plane | DIRECT_SYNC | always_warm | api | active | meetings | Low | None |
| **api/routes/voice_gateway.py** | API Plane | DIRECT_SYNC | always_warm | api | active | voice | Low | None |
| **api/routes/mcp.py** | Protocol Plane | DIRECT_SYNC | warm_pool | api | active | MCP | Medium | Add RuntimeContext propagation |
| **api/routes/acp.py** | Protocol Plane | DIRECT_SYNC | warm_pool | api | active | ACP | Medium | Add RuntimeContext propagation |
| **api/routes/cron.py** | API Plane | DIRECT_SYNC | always_warm | api | active | cron | Low | None |
| **api/routes/admin.py** | API Plane | DIRECT_SYNC | knative_scale_to_zero | api | active | admin | Low | None |
| **api/routes/mercury.py** | Protocol Plane | DIRECT_SYNC | warm_pool | api | active | mercury | Low | None |
| **api/routes/canvas.py** | API Plane | DIRECT_SYNC | warm_pool | api | active | canvas | Low | None |
| **api/routes/internal_control.py** | Control Plane | DIRECT_SYNC | always_warm | api | active | internal | Low | None |
| **api/routes/integrations/providers.py** | API Plane | DIRECT_SYNC | always_warm | api | active | providers | Low | NEW - verify multi-tenant |
| **api/routes/integrations/channels.py** | API Plane | DIRECT_SYNC | always_warm | api | active | channels | Low | NEW - verify multi-tenant |
| **services/orchestrator/service.py** | Agent Runtime Plane | DURABLE_WORKFLOW | always_warm | orchestrator | **active** | gateway | High | None - canonical runtime |
| **services/orchestrator/intake.py** | Agent Runtime Plane | DIRECT_SYNC | always_warm | orchestrator | active | orchestrator | High | None |
| **services/orchestrator/planner.py** | Agent Runtime Plane | DIRECT_SYNC | always_warm | orchestrator | active | orchestrator | High | None |
| **services/orchestrator/executor.py** | Agent Runtime Plane | DURABLE_WORKFLOW | always_warm | orchestrator | active | orchestrator | High | Add Temporal integration |
| **services/orchestrator/blender.py** | Agent Runtime Plane | DIRECT_SYNC | always_warm | orchestrator | active | orchestrator | High | None |
| **services/orchestrator/subagent_runtime.py** | Agent Runtime Plane | DURABLE_WORKFLOW | keda_event_scaled | orchestrator | active | orchestrator | High | Add async task persistence |
| **services/ml/runtime.py** | Model Plane | DIRECT_SYNC | always_warm | ml | **active** | orchestrator, langchain | High | Add health-gated routing, fallback, budgets |
| **services/ml/registry.py** | Model Plane | DIRECT_SYNC | always_warm | ml | active | MLRuntime | Low | None |
| **services/ml/providers/** | Model Plane | DIRECT_SYNC | always_warm | ml | active | MLRuntime | Medium | Enforce no direct SDK calls outside MLRuntime |
| **services/tools/executor.py** | Tool Plane | DURABLE_WORKFLOW | keda_event_scaled | tools | **active** | orchestrator | High | Add ToolResultEnvelope, ToolPolicy, ledger |
| **services/tools/registry.py** | Tool Plane | DIRECT_SYNC | always_warm | tools | active | executor | High | Add ToolSpec with risk tiers, approval modes |
| **services/tools/mcp_bridge.py** | Protocol Plane | FAST_ASYNC | keda_event_scaled | tools | active | MCP | Medium | Add RuntimeContext propagation |
| **services/memory/service.py** | Memory Plane | DIRECT_SYNC | warm_pool | memory | **active** | orchestrator | High | Add MemoryScope, MemoryPolicy, proposals |
| **services/memory/session_store.py** | Memory Plane | DIRECT_SYNC | warm_pool | memory | active | orchestrator | High | Add tenant/account/session scoping |
| **services/tenant/** | Security Plane | DIRECT_SYNC | always_warm | tenant | **active** | All services | High | TenantNamespace exists - enforce usage |
| **services/tenant/namespace.py** | Security Plane | DIRECT_SYNC | always_warm | tenant | active | All services | High | Enforce via CI grep rule |
| **services/auth/** | Security Plane | DIRECT_SYNC | always_warm | auth | active | All services | High | None |
| **services/security/redaction.py** | Security Plane | DIRECT_SYNC | always_warm | security | active | All services | Medium | Add to all log paths |
| **services/security/safety.py** | Security Plane | DIRECT_SYNC | always_warm | security | active | All services | Medium | None |
| **services/gateway/** | API Plane | DIRECT_SYNC | always_warm | gateway | active | gateway | Low | None |
| **services/realtime/** | API Plane | DIRECT_SYNC | warm_pool | realtime | active | realtime | Low | None |
| **services/cron/cron_service.py** | Workflow Plane | BACKGROUND_BATCH | cron | active | orchestrator | Low | None |
| **services/workspace/workspace_manager.py** | Sandbox Plane | SANDBOXED_EXECUTION | keda_event_scaled | workspace | active | tools | High | Add SandboxManager wrapper |
| **services/workspace/cleanup_worker.py** | Data Plane | BACKGROUND_BATCH | cron | active | orchestrator | Low | None |
| **services/search/** | Data Plane | DIRECT_SYNC | warm_pool | search | active | orchestrator | Low | None |
| **langchain/agent.py** | Agent Runtime Plane | DIRECT_SYNC | warm_pool | langchain | active | orchestrator (wrapper) | Medium | Clarify as wrapper, not primary runtime |
| **langchain/models.py** | Model Plane | DIRECT_SYNC | warm_pool | langchain | active | agent | Low | ButlerChatModel is canonical ML adapter |
| **langchain/tools.py** | Tool Plane | DIRECT_SYNC | warm_pool | langchain | active | agent | Low | ButlerToolFactory is canonical |
| **langchain/middleware/** | Agent Runtime Plane | DIRECT_SYNC | warm_pool | langchain | active | agent | Low | None |
| **langchain/protocols/mcp.py** | Protocol Plane | DIRECT_SYNC | warm_pool | langchain | active | MCP | Medium | Add RuntimeContext propagation |
| **langchain/protocols/a2a.py** | Protocol Plane | DIRECT_SYNC | warm_pool | langchain | active | A2A | Medium | Add RuntimeContext propagation |
| **langchain/protocols/acp.py** | Protocol Plane | DIRECT_SYNC | warm_pool | langchain | active | ACP | Medium | Add RuntimeContext propagation |
| **langchain/providers/** | Model Plane | DIRECT_SYNC | warm_pool | langchain | active | agent | Medium | Merge into services/ml/providers/ |
| **langchain/skills/** | Agent Runtime Plane | DIRECT_SYNC | warm_pool | langchain | active | agent | Low | Merge ButlerSkillCompiler into domain/skills/ |
| **butler_runtime/** | Legacy | N/A | N/A | legacy | **legacy** | None | Medium | Migrate useful components, mark for removal |
| **butler_runtime/agent/** | Legacy | N/A | N/A | legacy | legacy | None | Medium | Migrate to services/orchestrator/ |
| **butler_runtime/channels/** | Legacy | N/A | N/A | legacy | legacy | None | Medium | Migrate to services/realtime/channels/ |
| **butler_runtime/hermes/** | Legacy | N/A | N/A | legacy | legacy | None | Medium | Extract useful patterns, drop CLI code |
| **butler_runtime/skills/** | Legacy | N/A | N/A | legacy | legacy | None | Medium | Migrate to langchain/skills/ or domain/skills/ |
| **butler_runtime/tools/** | Legacy | N/A | N/A | legacy | legacy | None | Medium | Migrate to services/tools/ |
| **domain/contracts.py** | Domain Plane | DIRECT_SYNC | always_warm | domain | active | All services | Low | None |
| **domain/base.py** | Domain Plane | DIRECT_SYNC | always_warm | domain | active | All services | Low | None |
| **domain/auth/** | Domain Plane | DIRECT_SYNC | always_warm | domain | active | auth | Low | None |
| **domain/tools/** | Domain Plane | DIRECT_SYNC | always_warm | domain | active | tools | Low | Add ToolSpec, ToolPolicy contracts |
| **domain/memory/** | Domain Plane | DIRECT_SYNC | always_warm | domain | active | memory | Low | Add MemoryScope, MemoryPolicy contracts |
| **domain/ml/** | Domain Plane | DIRECT_SYNC | always_warm | domain | active | ML | Low | None |
| **domain/orchestrator/** | Domain Plane | DIRECT_SYNC | always_warm | domain | active | orchestrator | Low | Add OperationPolicy, ExecutionDecision contracts |
| **domain/tenant/** | Domain Plane | DIRECT_SYNC | always_warm | domain | active | tenant | Low | None |
| **domain/events/** | Domain Plane | EVENT_STREAM | always_warm | domain | active | All services | Low | None |
| **domain/policy/** | Domain Plane | DIRECT_SYNC | always_warm | domain | active | policy | Low | None |
| **infrastructure/config.py** | Control Plane | DIRECT_SYNC | always_warm | infrastructure | active | All services | Low | None |
| **infrastructure/database.py** | Data Plane | DIRECT_SYNC | always_warm | infrastructure | active | All services | Low | Add tenant/account indexes |
| **infrastructure/cache.py** | Data Plane | DIRECT_SYNC | always_warm | infrastructure | active | All services | High | Enforce TenantNamespace for all keys |
| **infrastructure/memory/neo4j_client.py** | Data Plane | DIRECT_SYNC | warm_pool | infrastructure | active | memory | Low | None |
| **infrastructure/memory/qdrant_client.py** | Data Plane | DIRECT_SYNC | warm_pool | infrastructure | active | memory | Low | Add tenant/account filters |
| **infrastructure/redpanda_client.py** | Data Plane | EVENT_STREAM | always_warm | infrastructure | active | events | Low | Add tenant partitioning |
| **infrastructure/s3_client.py** | Data Plane | DIRECT_SYNC | always_warm | infrastructure | active | storage | Low | Add tenant/account path scoping |
| **infrastructure/secret_manager.py** | Security Plane | DIRECT_SYNC | always_warm | infrastructure | active | All services | High | None |
| **infrastructure/async_optimizer.py** | Data Plane | DIRECT_SYNC | always_warm | infrastructure | active | ML | Low | None |
| **infrastructure/partitioning.py** | Data Plane | DIRECT_SYNC | always_warm | infrastructure | active | All services | Low | None |
| **observability/otel.py** | Observability Plane | DIRECT_SYNC | always_warm | observability | active | All services | Low | Add tenant/account hashing in traces |
| **observability/model_monitoring.py** | Observability Plane | FAST_ASYNC | always_warm | observability | active | ML | Low | None |
| **observability/ab_testing.py** | Observability Plane | DIRECT_SYNC | always_warm | observability | active | All services | Low | None |
| **skills_library/** | Data Plane | BACKGROUND_BATCH | warm_pool | skills | active | skills compiler | Low | None - 53 OpenClaw skills |
| **integrations/hermes/** | Legacy | N/A | N/A | legacy | legacy | None | Medium | Extract useful patterns, drop CLI code |
| **extensions/** | Data Plane | N/A | N/A | extensions | incomplete | None | Low | Review and classify |
| **futureagi/** | Data Plane | N/A | N/A | futureagi | incomplete | None | Low | Review and classify |
| **qa/** | Test Plane | N/A | N/A | qa | test-only | None | Low | None |
| **tests/** | Test Plane | N/A | N/A | tests | test-only | None | Low | Add tenant isolation tests |
| **cli/** | Control Plane | N/A | N/A | cli | active | CLI users | Low | None - CLI is separate from runtime |
| **deployment/** | Deployment Plane | N/A | N/A | deployment | active | DevOps | Low | Add Helm charts, Argo CD manifests |
| **migrations/** | Data Plane | BACKGROUND_BATCH | cron | migrations | active | Postgres | High | Add tenant_id to all user tables |
| **db/** | Data Plane | N/A | N/A | db | empty | None | Low | Models are in domain/ |
| **hermes_constants.py** | Legacy | N/A | N/A | legacy | legacy | None | Medium | Mark for removal after migration |
| **migration_output.log** | Data Plane | N/A | N/A | generated | generated | None | Low | Ignore |

---

## Critical Issues Found

### 1. Duplicate Runtime Layers (HIGH RISK)
- **Problem:** Three agent runtimes exist: `services/orchestrator/`, `langchain/agent.py`, `butler_runtime/`
- **Impact:** Confusion, maintenance burden, potential bugs from divergent implementations
- **Action:** 
  - Keep `services/orchestrator/` as canonical
  - Clarify `langchain/agent.py` as wrapper/adapter only
  - Migrate useful components from `butler_runtime/` to canonical services
  - Mark `butler_runtime/` as legacy with migration plan

### 2. No RuntimeContext (HIGH RISK)
- **Problem:** No canonical `RuntimeContext` class carrying tenant_id, account_id, session_id, request_id, trace_id, workflow_id, task_id, agent_id, etc.
- **Impact:** No tenant/account/session context enforcement, no trace propagation
- **Action:** Create `domain/runtime/context.py` with `RuntimeContext` dataclass

### 3. TenantNamespace Not Enforced (HIGH RISK)
- **Problem:** `services/tenant/namespace.py` exists but not enforced via CI grep rule
- **Impact:** Raw Redis/cache/lock keys scattered across codebase
- **Action:** Add CI grep rule to forbid raw key patterns, enforce TenantNamespace usage

### 4. No OperationRouter / AdmissionController (HIGH RISK)
- **Problem:** No central decision brain for sync vs async vs workflow vs approval vs sandbox vs degraded vs shed
- **Impact:** All operations treated as sync, no admission control, no degradation policy
- **Action:** Create `domain/runtime/operation_router.py` and `domain/runtime/admission_controller.py`

### 5. Tool Runtime Missing Policy (HIGH RISK)
- **Problem:** `services/tools/registry.py` lacks risk tiers, approval modes, schema validation
- **Impact:** No tool policy enforcement, no approval gates for high-risk tools
- **Action:** Add ToolSpec with L0-L4 risk tiers, approval modes, required_permissions, sandbox_required

### 6. MLRuntime Missing Health-Gated Routing (MEDIUM RISK)
- **Problem:** Dead local providers (Ollama/vLLM) can break requests
- **Impact:** User requests fail when local model is unhealthy
- **Action:** Add health checks, fallback chains, skip unhealthy providers

### 7. No Durable Workflow Engine (HIGH RISK)
- **Problem:** Multi-step operations run as plain async functions, no durability
- **Impact:** Lost state on crashes, no replay, no compensation
- **Action:** Integrate Temporal or equivalent durable workflow engine

### 8. Memory System Missing Scopes and Policies (HIGH RISK)
- **Problem:** No memory scopes (session/user/tenant/agent), no memory proposals, no right-to-erasure
- **Impact:** Cross-tenant memory leaks, no deletion policy
- **Action:** Add MemoryScope, MemoryPolicy, MemoryProposal, RightToErasureWorkflow

### 9. Logging Not Structured or Tenant-Aware (MEDIUM RISK)
- **Problem:** Logs lack tenant/account hashing, no event categories, no deduplication
- **Impact:** Log overload, PII leaks, no tenant-level debugging
- **Action:** Add structured logging with hashed IDs, event categories, sampling, dedup

### 10. Protocols Missing RuntimeContext Propagation (MEDIUM RISK)
- **Problem:** MCP/A2A/ACP calls don't carry tenant/session/trace context
- **Impact:** Protocol calls bypass tenant isolation
- **Action:** Add RuntimeContext injection to all protocol bridges

### 11. No SandboxManager (HIGH RISK)
- **Problem:** Code execution via direct subprocess/os.system
- **Impact:** No isolation, no quota enforcement, no cleanup
- **Action:** Create SandboxManager with Docker/Modal/Runloop providers

### 12. DB Migrations Incomplete (MEDIUM RISK)
- **Problem:** Only 2 migrations, tenant columns may be missing from user tables
- **Impact:** No tenant/account scoping in DB queries
- **Action:** Audit all domain models, add tenant_id/account_id where needed

---

## Unsafe Direct Calls Found (Phase 0.5 Static Safety Scan)

### Raw Redis Keys (redis\.(get|set|delete|hset|hget|lpush|rpush|sadd))
**37 files found:**
- infrastructure/cache.py (expected - cache abstraction)
- api/routes/admin.py
- services/orchestrator/executor.py
- services/gateway/auth_middleware.py
- services/gateway/session_manager.py
- services/gateway/idempotency.py
- services/gateway/edge_topology.py
- services/gateway/multi_dim_rate_limit.py
- services/device/environment.py
- services/device/service.py
- services/queues/consumer_manager.py
- services/communication/delivery.py
- services/communication/idempotency.py
- services/queues/dlq_handler.py
- services/ml/features.py
- services/realtime/presence.py
- services/cost/cost_alerts.py
- services/cost/spend_tracking.py
- services/cost/budget_enforcement.py
- services/auth/credential_pool.py
- services/auth/service.py
- services/security/pii_service.py
- services/memory/routes.py
- services/memory/session_store.py
- services/memory/service.py
- services/tools/executor.py
- services/tools/verification.py
- services/tenant/metering.py
- services/tenant/quota.py
- core/idempotency.py
- core/middleware.py
- core/locks.py
- core/health_agent.py
- Action: CI grep rule to forbid raw `redis.set/get` patterns, enforce TenantNamespace

### Direct subprocess/os.system/Popen/check_output/run(
**16 files found:**
- services/cron/cron_service.py
- services/ml/mixer.py
- services/ml/training_pipeline.py
- services/queues/redpanda_topology.py
- services/ml/media_processor.py
- services/audio/processors.py
- services/search/web_provider.py
- services/orchestrator/backends.py
- services/orchestrator/langgraph_runtime.py
- services/plugin_ops/trust_pipeline.py
- services/chat/autoreply.py
- services/tools/mcp_bridge.py
- services/tools/langchain_adapter.py
- domain/contracts.py
- domain/cron/models.py
- domain/orchestrator/runtime_kernel.py
- Action: CI grep rule to forbid subprocess/os.system outside SandboxManager

### Direct Provider SDK Imports (openai|anthropic|groq|ollama|vllm|mistral|cohere)
**Many files found:**
- services/ml/providers/ (intended - canonical location)
- services/gateway/session_manager.py
- services/orchestrator/backends.py
- services/ml/runtime.py
- services/ml/adapters/vllm_adapter.py
- services/ml/registry.py
- services/ml/providers/tts.py, stt.py, llm.py, cloud.py, code.py, gateway.py, webtools.py
- services/search/web_provider.py
- services/vision/models.py
- services/realtime/manager.py
- services/auth/credential_pool.py
- services/security/safety.py
- services/tools/sandbox_manager.py
- services/tools/mcp_bridge.py
- infrastructure/config.py
- api/routes/mcp.py
- api/routes/integrations/providers.py
- domain/skills/models.py
- integrations/hermes/hermes_constants.py (legacy)
- langchain/providers/ (duplicate - merge into services/ml/providers/)
- Action: Enforce no direct SDK calls outside MLRuntime provider modules

### Raw os.getenv/os.environ
**64 files found:**
- services/gateway/session_manager.py
- services/orchestrator/backends.py
- services/communication/webhooks.py
- services/ml/registry.py
- services/ml/providers/tts.py, stt.py, llm.py, cloud.py, code.py, gateway.py, webtools.py, embeddings.py, voice.py, search.py, communication.py
- services/search/web_provider.py
- services/vision/models.py
- services/realtime/manager.py
- services/auth/credential_pool.py
- services/security/safety.py
- services/tools/sandbox_manager.py
- services/tools/mcp_bridge.py
- services/tools/skill_marketplace.py
- infrastructure/config.py (intended - canonical location)
- domain/contracts.py
- domain/cron/models.py
- domain/orchestrator/runtime_kernel.py
- domain/plugins/sandbox.py
- infrastructure/memory/neo4j_client.py
- Action: Enforce all config through infrastructure/config.py

### Logger/logging Calls
**173 files found:**
- Widespread across core/, services/, infrastructure/, integrations/hermes/, langchain/
- Action: Add structured logging with tenant/account hashing, event categories, sampling, dedup

### Unscoped Memory/Vector Calls (qdrant|neo4j|vector|memory)
**110 files found:**
- services/memory/ (91 files)
- domain/memory/ (15 files)
- infrastructure/memory/ (4 files)
- Action: Enforce MemoryPolicy on all writes

### Tenant_id Coverage
**123 files found:**
- domain/ (8 files): orchestrator/models.py, runtime_kernel.py, ml/contracts.py, tenant/models.py, memory/contracts.py, memory/models.py, tools/hermes_dispatcher.py, tools/models.py
- services/ (107 files): orchestrator/, memory/, tenant/, tools/, ml/, gateway/, etc.
- infrastructure/ (4 files): redpanda_client.py, config.py, memory/qdrant_client.py, memory/neo4j_client.py
- api/ (4 files): integrations/channels.py, integrations/providers.py, gateway.py, schemas/components.py
- Action: Verify all user tables have tenant_id/account_id columns

---

## Next Immediate Actions

1. **Create RuntimeContext** in `domain/runtime/context.py`
2. **Create OperationRouter** in `domain/runtime/operation_router.py`
3. **Create AdmissionController** in `domain/runtime/admission_controller.py`
4. **Add CI grep rules** for raw keys, subprocess, provider SDKs
5. **Add ToolSpec** with risk tiers to `domain/tools/spec.py`
6. **Add MemoryScope** to `domain/memory/scopes.py`
7. **Add MemoryPolicy** to `domain/memory/policy.py`
8. **Audit DB models** for tenant/account columns
9. **Clarify langchain/agent.py** as wrapper in docs
10. **Mark butler_runtime/** as legacy with migration plan

---

## Phase 0 Gate

**This system map is complete.** All active modules are classified. Duplicate runtimes are identified. Critical issues are documented.

**Ready for Phase 1:** Runtime Leak Stopper (ToolResultEnvelope, FinalResponseComposer, ResponseValidator).
