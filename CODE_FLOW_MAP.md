# Butler Backend Code Flow Map

**Version:** 3.2  
**Last Updated:** 2026-04-26  
**Scope:** backend/langchain, backend/core, backend/futureagi, backend/butler_runtime, backend/services

---

## Architecture Overview

Butler follows a **layered architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────────┐
│                         API Layer (api/)                        │
│  Routes → Schemas → HTTP/WebSocket                             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    Services Layer (services/)                   │
│  Orchestrator | Memory | Tools | ML | Gateway | Auth | Tenant   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                   Domain Layer (domain/)                        │
│  Contracts | Models | Policies | Runtime Kernel               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                Infrastructure Layer (infrastructure/)             │
│  Database | Cache | External Providers | Config                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                   Core Layer (core/)                            │
│  Base Service | Config | Errors | Logging | Observability        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Layer (core/)

**Purpose:** Cross-cutting infrastructure and base patterns

### Key Files

- **deps.py** - DependencyRegistry with application-lifetime singletons
  - MLRuntimeManager, MemoryService, ToolExecutor
  - LockManager, StateSyncer, HealthAgent
  - Tenant services (TenantResolver, CredentialBroker)
  - LangChain adapters (model factory, tool registry, memory adapter)
  - OperationRouter for admission control

- **base_service.py** - ButlerBaseService abstract class
  - Standardized FastAPI app construction
  - Lifespan management (startup/shutdown)
  - Health probes (/health/live, /health/ready)
  - Middleware registration

- **errors.py** - RFC 9457 Problem Details
  - Problem exception base class
  - NotFoundProblem, ValidationProblem, ForbiddenProblem
  - Exception handlers for FastAPI

- **base_config.py** - ButlerBaseConfig
  - SERVICE_NAME, ENVIRONMENT, VERSION
  - HOST, PORT, LOG_LEVEL
  - BUTLER_INTERNAL_KEY

### Dependency Flow

```
FastAPI Route
    ↓ Depends()
DependencyRegistry.get_*()
    ↓
Service Instance (singleton or request-scoped)
```

---

## LangChain Integration (langchain/)

**Purpose:** LangChain/LangGraph adapters preserving Butler governance

### Key Components

#### agent.py - LangGraph Agent Builder

```
create_agent_from_di()
    ↓
ButlerAgentBuilder
    ↓
ButlerChatModel (from MLRuntimeManager)
    ↓
ButlerLangChainTool (from ToolSpec)
    ↓
LangGraph StateGraph with nodes:
  - intake_node
  - plan_node
  - safety_node
  - call_model_node
  - tools_node_with_middleware
  - memory_writeback_node
    ↓
Compiled graph with Postgres checkpointer
```

**Flow:**
1. DI container provides MLRuntimeManager, ToolSpecs, ToolExecutor
2. ButlerChatModel wraps MLRuntimeManager for LangChain
3. ButlerToolFactory creates LangChain tools from ToolSpecs
4. LangGraph nodes execute with middleware (PRE_MODEL, POST_MODEL, PRE_TOOL, POST_TOOL)
5. ButlerMemoryAdapter provides 4-tier memory context
6. Postgres checkpointer enables workflow resumption

#### models.py - ButlerChatModel

```
LangChain BaseChatModel
    ↓
ButlerChatModel
    ↓
MLRuntimeManager.generate()
    ↓
Provider (OpenAI, Anthropic, etc.)
    ↓
ReasoningResponse → AIMessage
```

**Key Features:**
- Tool binding via ToolAwareButlerChatModel
- Streaming support via generate_stream()
- Multi-tenant isolation via tenant_id
- Provider routing through MLRuntimeManager

#### tools.py - ButlerLangChainTool

```
DomainToolSpec (canonical)
    ↓
ButlerLangChainTool (LangChain BaseTool)
    ↓
Hybrid Governance:
  - L0/L1: Direct dispatch with audit
  - L2/L3/L4: ToolExecutor.execute_canonical()
    ↓
ToolResultEnvelope
```

**Governance Flow:**
- RiskTier determines execution path
- L0/L1: Direct implementation with audit logging
- L2/L3/L4: Full governance (approval, sandbox, audit)

#### memory.py - ButlerMemoryAdapter

```
LangChain BaseChatMessageHistory
    ↓
ButlerMemoryAdapter
    ↓
MemoryService.build_context()
    ↓
4-Tier Memory:
  - Hot: Redis (recent turns)
  - Warm: Qdrant (relevant memories)
  - Cold: Postgres/TurboQuant (long-term)
  - Graph: Neo4j (relational context)
    ↓
ContextPack → LangChain messages
```

#### runtime.py - ButlerToolContext

```
ButlerToolContext (frozen dataclass)
    - tenant_id
    - account_id
    - session_id
    - trace_id
    - user_id
    - metadata
    ↓
Propagated through LangGraph config
```

### Middleware Layer (langchain/middleware/)

**Middleware Execution Order:**
1. PRE_MODEL - Before LLM call
2. POST_MODEL - After LLM call
3. PRE_TOOL - Before tool execution
4. POST_TOOL - After tool execution

**Available Middleware:**
- ButlerCostTrackingMiddleware - Token/cost tracking
- ButlerContentGuardMiddleware - Safety checks
- ButlerToolRetryMiddleware - Tool retry logic
- ButlerCachingMiddleware - Response caching
- ButlerHITLMiddleware - Human-in-the-loop approval
- ButlerObservabilityMiddleware - Tracing/metrics

---

## Butler Runtime (butler_runtime/)

**Purpose:** Unified agent runtime replacing standalone Hermes

### Agent Loop (butler_runtime/agent/loop.py)

```
ButlerExecutionContext
    ↓
ButlerUnifiedAgentLoop.run()
    ↓
MessageBuilder.build_*()
    ↓
ButlerModelRouter.chat()
    ↓
ToolCallingHandler.extract_tool_calls()
    ↓
ButlerToolExecutor.execute_tool_call()
    ↓
EventSink.emit_*()
    ↓
OrchestratorResult
```

**Key Components:**
- **ButlerExecutionContext** - Execution context (account, session, message, model)
- **ButlerModelRouter** - Model routing with provider logic
- **ButlerToolExecutor** - Tool execution with governance
- **ButlerMemoryContextBuilder** - Memory context from MemoryService
- **ExecutionBudget** - Token/iteration limits
- **ButlerEventSink** - Event streaming

### Hermes Integration (butler_runtime/hermes/)

```
FunctionCallHandler - Tool call normalization
ToolSchemaConverter - Hermes → Butler spec conversion
```

**Purpose:** Assimilated Hermes utilities without CLI/config dependencies

---

## Services Layer (services/)

**Purpose:** Application orchestration and business logic

### Orchestrator Service (services/orchestrator/)

#### service.py - OrchestratorService

```
API Request
    ↓
OrchestratorService.intake()
    ↓
IntakeProcessor.process()
    ↓
Safety Check (ContentGuard)
    ↓
Redaction (RedactionService)
    ↓
Session Store (ButlerSessionStore)
    ↓
ButlerBlender.blend()
    ↓
PlanEngine.create_plan()
    ↓
Workflow Creation
    ↓
DurableExecutor.execute_workflow()
    ↓
RuntimeKernel.execute_result()
    ↓
OrchestratorResult
```

**Key Flow:**
1. **Intake:** Process request, classify intent
2. **Safety:** Content guard check
3. **Redaction:** PII redaction
4. **Memory:** Build context from 4-tier memory
5. **Blender:** Federated intelligence (memory + tools + search)
6. **Planning:** Create execution plan
7. **Execution:** Durable workflow or agentic execution
8. **Response:** Strip thought tags, restore redacted output

#### executor.py - DurableExecutor

```
Workflow + Plan
    ↓
PlanLowerer.lower() → WorkflowDAG
    ↓
WorkflowEngine.step_workflow()
    ↓
RuntimeKernel.execute_result()
    ↓
TaskStateMachine.transition()
    ↓
ApprovalRequired → suspend
    ↓
WorkflowResult
```

**Execution Modes:**
- **AGENTIC:** RuntimeKernel with Hermes agent loop
- **DETERMINISTIC:** Direct tool execution
- **WORKFLOW:** DAG-based step execution

#### planner.py - PlanEngine

```
Intent + Context
    ↓
PlanEngine.create_plan()
    ↓
LLM Plan Generation
    ↓
Plan (steps, execution_mode)
    ↓
WorkflowDAG (if needed)
```

#### blender.py - ButlerBlender

```
BlenderSignal (user_id, session_id, query, context)
    ↓
ButlerBlender.blend()
    ↓
MemoryService.recall()
    ↓
ToolsService.visible_tools()
    ↓
SearchService.search()
    ↓
Ranking & Fusion
    ↓
Candidates (memory, tools, search)
```

### Memory Service (services/memory/)

#### service.py - MemoryService

```
MemoryService
    ↓
4-Tier Architecture:
  - Hot: Redis (session turns, TTL 7 days)
  - Warm: Qdrant (vector search)
  - Cold: Postgres/TurboQuant (compressed snapshots)
  - Graph: Neo4j (entities, relationships)
    ↓
Engines:
  - RetrievalFusionEngine - Search across tiers
  - MemoryEvolutionEngine - Reconciliation
  - EntityResolutionEngine - Entity resolution
  - KnowledgeExtractionEngine - Graph extraction
  - AnchoredSummarizer - Session summarization
  - ContextBuilder - Context assembly
```

**Key Methods:**
- `store()` - Write memory with reconciliation
- `recall()` - Retrieve relevant memories
- `build_context()` - Assemble ContextPack
- `store_turn()` - Record conversation turn

### Tools Service (services/tools/)

#### executor.py - ToolExecutor

```
ToolExecutionRequest
    ↓
ToolExecutor.execute_canonical()
    ↓
1. Validate RuntimeContext
2. Fetch ToolSpec from registry
3. ToolPolicy.evaluate()
4. OperationRouter.route()
5. Check approval
6. Create ledger row
7. Execute with timeout
8. SandboxManager (if required)
9. Normalize result
10. RedactionService.redact()
11. Write audit event
12. Write usage event
    ↓
ToolResultEnvelope
```

**Governance Tiers:**
- **L0:** No restrictions
- **L1:** Audit only
- **L2:** Approval required
- **L3:** Approval + sandbox
- **L4:** Full isolation

### ML Service (services/ml/)

#### runtime.py - MLRuntimeManager

```
ReasoningRequest
    ↓
MLRuntimeManager.generate()
    ↓
OperationRouter.route() (admission control)
    ↓
ModelRegistry.resolve_candidates()
    ↓
Candidate Selection (tier, health, fallback)
    ↓
Provider.generate()
    ↓
CircuitBreaker (if configured)
    ↓
ReasoningResponse
```

**Tiers:**
- **T0:** Instant (local cache)
- **T1:** Fast (small models)
- **T2:** Standard (GPT-4 class)
- **T3:** Heavy (Claude-3, GPT-4-Turbo)

**Providers:**
- OpenAI, Anthropic, Cohere, Google, Groq, Ollama, vLLM, etc.

### Gateway Service (services/gateway/)

**Components:**
- **rate_limiter.py** - Token bucket rate limiting
- **auth_middleware.py** - JWT authentication with JWKS
- **transport.py** - Hermes transport edge
- **protocol_service.py** - Mercury protocol
- **a2ui_bridge.py** - Agent-to-UI bridge

### Auth Service (services/auth/)

**Components:**
- **jwt.py** - JWKS manager, JWT validation
- **password.py** - Argon2id password hashing
- **session.py** - Session management

### Tenant Service (services/tenant/)

**Components:**
- **TenantResolver** - Resolve tenant from JWT
- **TenantContext** - Immutable tenant context
- **CredentialBroker** - Credential management
- **TenantCryptoService** - Tenant encryption
- **TenantIsolationService** - Multi-tenant isolation
- **TenantQuotaService** - Quota enforcement

---

## Future AGI Integration (futureagi/)

**Purpose:** Evaluation and guardrails with tenant isolation

### Components

- **ButlerFutureAGIClient** - API client wrapper
- **FutureAGIEvaluator** - 50+ evaluation metrics
  - Groundedness, hallucination, tool correctness, safety
- **FutureAGIGuardrails** - Real-time guardrails (<100ms latency)
  - PII detection, toxicity checks
- **ButlerPromptManager** - Prompt versioning and A/B testing
- **ButlerKnowledgeBase** - RAG knowledge base

---

## Full Request Flow

### Chat Request Flow

```
1. API Request (POST /api/v1/chat)
   ↓
2. JWT Auth Middleware (services/gateway/auth_middleware.py)
   - Validate JWT via JWKS
   - Extract tenant_id, account_id, user_id
   ↓
3. Rate Limiter (services/gateway/rate_limiter.py)
   - Token bucket check
   ↓
4. OrchestratorService.intake() (services/orchestrator/service.py)
   ↓
5. IntakeProcessor.process()
   - Classify intent
   - Determine execution mode
   ↓
6. Safety Check (services/security/safety.py)
   - ContentGuard.check()
   ↓
7. Redaction (services/security/redaction.py)
   - Redact PII from input
   ↓
8. Memory Context (services/memory/service.py)
   - ButlerSessionStore.get_context()
   - 4-tier memory retrieval
   ↓
9. Blender (services/orchestrator/blender.py)
   - Memory + Tools + Search fusion
   ↓
10. Planning (services/orchestrator/planner.py)
    - PlanEngine.create_plan()
    ↓
11. Workflow Creation
    - Workflow + Task records
    ↓
12. Execution (services/orchestrator/executor.py)
    - DurableExecutor.execute_workflow()
    ↓
13. RuntimeKernel (domain/orchestrator/runtime_kernel.py)
    - Execute with strategy:
      - HERMES_AGENT: ButlerUnifiedAgentLoop
      - DETERMINISTIC: Direct tool execution
    ↓
14. Agent Loop (butler_runtime/agent/loop.py)
    - ButlerModelRouter.chat()
    - Tool execution via ButlerToolExecutor
    ↓
15. ML Runtime (services/ml/runtime.py)
    - MLRuntimeManager.generate()
    - Provider routing
    ↓
16. Tool Execution (services/tools/executor.py)
    - ToolExecutor.execute_canonical()
    - Governance checks
    - Sandbox execution
    ↓
17. Response Processing
    - Safety check on output
    - Restore redacted content
    - Strip thought tags
    ↓
18. Memory Writeback
    - Store turn in memory
    - Trigger compression
    ↓
19. OrchestratorResult
    - Return to API
```

### LangGraph Agent Flow

```
1. create_agent_from_di() (langchain/agent.py)
   ↓
2. ButlerAgentBuilder
   - Get MLRuntimeManager from DI
   - Get ToolSpecs from HermesToolCompiler
   - Get ToolExecutor from DI
   ↓
3. ButlerChatModel (langchain/models.py)
   - Wrap MLRuntimeManager
   - Bind tools via ToolAwareButlerChatModel
   ↓
4. ButlerLangChainTool (langchain/tools.py)
   - Convert ToolSpec to LangChain tool
   - Hybrid governance (L0/L1 direct, L2/L3/L4 governed)
   ↓
5. LangGraph StateGraph
   - Nodes: intake → plan → safety → call_model → tools → memory_writeback
   - Middleware: PRE_MODEL, POST_MODEL, PRE_TOOL, POST_TOOL
   ↓
6. ButlerMemoryAdapter (langchain/memory.py)
   - Provide 4-tier memory context
   ↓
7. Postgres Checkpointer
   - Enable workflow resumption
   ↓
8. Graph Execution
   - ainvoke() with config
   - Checkpoint state persistence
   ↓
9. Response
   - Stream tokens or final result
```

---

## Dependency Injection Flow

```
core/deps.py (DependencyRegistry)
    ↓
Singleton Initialization (lazy):
    - MLRuntimeManager
    - MemoryService (request-scoped)
    - ToolExecutor (request-scoped)
    - TenantResolver
    - LockManager
    - StateSyncer
    - HealthAgent
    ↓
FastAPI Depends()
    ↓
get_tenant_context()
get_memory_service()
get_tools_service()
get_ml_runtime()
get_orchestrator_service()
    ↓
Service Instances injected into routes
```

---

## Multi-Tenant Flow

```
1. JWT Validation
   - Extract tenant_id from JWT claims
   ↓
2. TenantResolver
   - Resolve TenantContext
   - Check isolation level
   ↓
3. Tenant Namespace
   - get_tenant_namespace(tenant_id)
   - Prefix isolation for Redis keys
   ↓
4. OperationRouter
   - Route operations with tenant context
   - Admission control per tenant
   ↓
5. Service Execution
   - All DB queries filtered by tenant_id
   - All Redis keys tenant-prefixed
   - All ML inference tenant-scoped
   ↓
6. Response
   - Tenant-isolated data only
```

---

## Key Integration Points

### LangChain ↔ Butler Services

| LangChain Component | Butler Service | Purpose |
|-------------------|----------------|---------|
| ButlerChatModel | MLRuntimeManager | LLM inference with provider routing |
| ButlerLangChainTool | ToolExecutor | Tool execution with governance |
| ButlerMemoryAdapter | MemoryService | 4-tier memory context |
| ButlerMiddlewareRegistry | Various | Cost, safety, caching, HITL |

### Butler Runtime ↔ Domain

| Butler Runtime | Domain Component | Purpose |
|---------------|-----------------|---------|
| ButlerUnifiedAgentLoop | RuntimeKernel | Agent execution strategy |
| ButlerModelRouter | MLRuntimeManager | Model routing |
| ButlerToolExecutor | ToolExecutor | Tool execution |
| ButlerMemoryContextBuilder | MemoryService | Memory context |

### Services ↔ Infrastructure

| Service | Infrastructure | Purpose |
|---------|---------------|---------|
| MemoryService | Redis, Postgres, Qdrant, Neo4j | 4-tier storage |
| MLRuntimeManager | Provider APIs | LLM inference |
| ToolExecutor | SandboxManager | Isolated execution |
| OrchestratorService | Postgres | Workflow persistence |

---

## Error Handling Flow

```
Exception
    ↓
RFC 9457 Problem (core/errors.py)
    ↓
problem_exception_handler()
    ↓
JSONResponse with:
    - type: URI to problem documentation
    - title: Error title
    - status: HTTP status code
    - detail: Error detail
    - instance: Request path
    - extensions: Additional context
    ↓
Client receives structured error
```

---

## Observability Flow

```
1. Tracing (core/tracing.py)
   - OpenTelemetry integration
   - Span creation for each operation
   ↓
2. Metrics (core/observability.py)
   - ButlerMetrics (Prometheus)
   - Counter, Gauge, Histogram
   ↓
3. Logging (core/logging.py)
   - Structlog integration
   - Contextual logging (tenant_id, session_id, trace_id)
   ↓
4. Health Checks (core/health.py)
   - /health/live - Liveness probe
   - /health/ready - Readiness probe
   - /health/startup - Startup probe
   ↓
5. Event Streaming (domain/events/)
   - ButlerEvent base class
   - StreamTokenEvent, StreamFinalEvent
   ↓
Monitoring System (Prometheus + Grafana)
```

---

## Security Flow

```
1. Authentication (services/auth/)
   - JWT validation via JWKS
   - RS256 signature verification
   ↓
2. Authorization (services/tenant/)
   - TenantContext resolution
   - Scope checking
   ↓
3. Safety (services/security/)
   - ContentGuard - Content safety checks
   - RedactionService - PII redaction
   - EgressPolicy - Egress filtering
   ↓
4. Tool Governance (services/tools/)
   - RiskTier-based execution
   - ApprovalRequired for L2+
   - Sandbox execution for L3+
   ↓
5. OperationRouter (domain/orchestration/)
   - Admission control
   - Rate limiting
   - Quota enforcement
```

---

## Summary

**Architecture:** Layered with clear separation (API → Services → Domain → Infrastructure → Core)

**Key Patterns:**
- Dependency Injection via DependencyRegistry
- Hybrid governance (L0/L1 direct, L2/L3/L4 governed)
- 4-tier memory (Hot, Warm, Cold, Graph)
- Multi-tenant isolation at all layers
- RFC 9457 error handling
- LangGraph integration with Butler governance preserved

**Execution Paths:**
1. **Chat:** API → Orchestrator → Agent Loop → ML Runtime → Tools → Memory
2. **LangGraph:** ButlerAgentBuilder → LangGraph → ButlerChatModel → ButlerLangChainTool → ButlerMemoryAdapter
3. **Tool Execution:** ToolExecutor → ToolPolicy → OperationRouter → Sandbox → Audit

**Integration Points:**
- LangChain adapters preserve Butler governance
- Butler Runtime replaces Hermes standalone
- Future AGI provides evaluation/guardrails
- All services use DI container
- Multi-tenant isolation throughout

**Data Flow:**
- Request → Auth → Intake → Safety → Memory → Planning → Execution → Response → Memory Writeback
- Context propagated via RuntimeContext/ButlerToolContext
- State persisted via Postgres checkpointer
- Events streamed via Redis pub/sub
