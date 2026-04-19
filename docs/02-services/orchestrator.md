# Orchestrator Service - Technical Specification

> **For:** Engineering  
> **Status:** Active (v3.1) — Security guardrails and ambient context integrated
> **Version:** 3.1
> **Reference:** Butler durable, policy-governed agent runtime  
> **Last Updated:** 2026-04-19

---

## 0. v3.1 Pipeline Upgrades

> **Completed in v3.1 (2026-04-19)**

### Full Request Pipeline (v3.1)

Every message processed by `OrchestratorService` now flows through:

```
1. ContentGuard.check(input)         ← heuristic + OpenAI Moderation
   ↓ blocked? return error
2. RedactionService.redact(input)    ← PII masked before any LLM call
3. IntakeProcessor.process()         ← intent classify + EnvironmentService snapshot
4. SmartRouter.route()               ← T0–T3 tier selection
   ↓ T0/T1 early return
5. ButlerBlender.blend()             ← parallel memory + tool + knowledge candidates
6. PlanEngine.create_plan()          ← structured workflow plan
7. DurableExecutor.execute()         ← tool calls, memory reads, LLM inference
8. ContentGuard.check(output)        ← output safety screen
   ↓ blocked? replace with safety notice
9. RedactionService.restore(output)  ← exact PII values restored before memory write
10. ButlerSessionStore.flush()        ← episodic write to WARM + COLD tiers
```

### Key Additions in v3.1
| Feature | Component | Description |
|---------|-----------|-------------|
| Input Safety | `ContentGuard` | Blocks requests matching heuristic or moderation categories |
| PII Redaction | `RedactionService` | Masks email/phone/CC/API keys before inference |
| Output Safety | `ContentGuard` | Screens LLM output before delivery |
| PII Restore | `RedactionService` | Restores original values in memory write-back |
| Ambient Context | `EnvironmentService` | Injects time/location/platform block via `IntakeProcessor` |
| SmartRouter | `ButlerSmartRouter` | T0–T3 routing now properly provisioned via `get_smart_router()` |

### Constructor Additions (`OrchestratorService.__init__`)
Two new optional params added in v3.1:
```python
redaction_service: RedactionService | None = None  # defaults to RedactionService()
content_guard: ContentGuard | None = None          # defaults to ContentGuard()
```
Both default to their no-arg constructors if not injected — zero breaking changes.

### Key Files
| File | Role |
|------|------|
| `services/orchestrator/service.py` | Main pipeline with guardrails **[UPGRADED v3.1]** |
| `services/orchestrator/intake.py` | Intent classification + env context injection **[UPGRADED v3.1]** |
| `services/orchestrator/blender.py` | `ButlerBlender` — parallel candidate retrieval |
| `services/orchestrator/executor.py` | `DurableExecutor` — workflow execution |
| `services/security/redaction.py` | PII masking service |
| `services/security/safety.py` | Content safety guard |
| `services/device/environment.py` | Ambient context provider |
| `core/deps.py` | Full DI wiring **[UPGRADED v3.1]** |

---

## 0. Implementation Status

| Phase | Component | Status | Description |
|-------|-----------|--------|-------------|
| 1 | **IntakeProcessor** | ✅ IMPLEMENTED | Intent classification + EnvironmentService injection |
| 2 | **ButlerBlender** | ✅ IMPLEMENTED | Parallel candidate retrieval (memory + tools + knowledge) |
| 3 | **PlanEngine** | ✅ IMPLEMENTED | Structured plan creation with policy evaluation |
| 4 | **DurableExecutor** | ✅ IMPLEMENTED | Workflow execution with tool dispatch |
| 5 | **Security Guardrails** | ✅ IMPLEMENTED | ContentGuard + RedactionService full input/output gate (v3.1) |
| 6 | **SmartRouter** | ✅ IMPLEMENTED | T0–T3 tier selection; `get_smart_router()` DI fixed (v3.1) |
| 7 | **Streaming** | ✅ IMPLEMENTED | `intake_streaming()` → ButlerEvent generator for ButlerStreamDispatcher |
| 8 | **Interrupt / Resume** | ⚪ PARTIAL | Durable state checkpointing present; resume from mid-plan not yet tested |
| 9 | **Subagent Handoff** | 🔲 PLANNED | Spawning child orchestrators for parallel sub-tasks |

---

## 1. Service Overview

### 1.1 Purpose
The Orchestrator service is the **brain and runtime supervisor** of Butler. It receives normalized requests from Gateway, selects the right execution mode, assembles context and candidates, evaluates policy and approval needs, creates structured plans, executes them durably, and coordinates response streaming, verification, compensation, and memory writeback.


### 1.2 Responsibilities
- request mode selection
- intent and entity understanding
- candidate retrieval coordination
- policy and approval evaluation
- structured planning and validation
- durable workflow execution
- subagent handoff coordination
- interrupt / resume handling
- verification and compensation
- response and stream-event generation
- memory writeback orchestration

### 1.3 Boundaries
- Does NOT directly access databases (uses Memory / Data / durable stores through adapters)
- Does NOT execute tools directly (uses Tools service or normalized tool runtime)
- Does NOT own raw protocol transport (Gateway owns ingress)
- Does NOT directly invoke protocol-native MCP transport lifecycle
- Does NOT handle authentication (Gateway handles)
- Does NOT persist durable state in ephemeral cache only
- Does NOT let Hermes or any imported runtime library define Butler lifecycle semantics
- Does NOT expose raw Hermes runtime entrypoints directly to routes or clients

### 1.4 Hermes Library Integration
The Orchestrator is the **primary Butler consumer** of Hermes runtime code, but only through Butler-owned adapters.

**Use as library:**
- `backend/integrations/hermes/run_agent.py` - execution-loop substrate
- `backend/integrations/hermes/agent/*` - prompt assembly, context compression, retry, redaction, runtime helpers
- `backend/integrations/hermes/model_tools.py` - tool-call orchestration substrate through Butler Tools interfaces

**Butler ownership stays here:**
- lifecycle state machine
- structured plan schemas
- approvals and interrupts
- handoffs and bounded delegation
- service-to-service coordination
- audit trail and event log
- verification / compensation policy

See `docs/services/hermes-library-map.md` for the full path map.

---

## 2. Architecture

### 2.1 Internal Runtime Architecture

```text
┌─────────────────────────────────────────────────────────────────────┐
│                       Orchestrator Service                         │
├─────────────────────────────────────────────────────────────────────┤
│ 1. Intake Layer                                                    │
│   - Request normalizer                                              │
│   - Session binder                                                  │
│   - Mode selector                                                   │
├─────────────────────────────────────────────────────────────────────┤
│ 2. Understanding Layer                                              │
│   - Intent engine                                                   │
│   - Entity extractor                                                │
│   - Context assembler                                               │
│   - Policy / guardrail engine                                       │
├─────────────────────────────────────────────────────────────────────┤
│ 3. Planning Layer                                                   │
│   - Candidate retrieval coordinator                                 │
│   - Structured planner                                              │
│   - Plan validator                                                  │
│   - Execution strategy selector                                     │
├─────────────────────────────────────────────────────────────────────┤
│ 4. Execution Layer                                                  │
│   - Workflow runtime / DAG engine                                   │
│   - Handoff manager                                                 │
│   - Approval / interrupt manager                                    │
│   - Verifier / compensation manager                                 │
├─────────────────────────────────────────────────────────────────────┤
│ 5. State & Output Layer                                             │
│   - Durable task store                                              │
│   - Event log                                                       │
│   - Stream emitter                                                  │
│   - Response composer                                               │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Dependencies

| Dependency | Type | Purpose |
|------------|------|---------|
| Memory | Internal | context retrieval, memory writeback |
| ML | Internal | optional intent support, embeddings, candidate-generation models, rerank inference |
| Tools | Internal | normalized action execution surface |
| PostgreSQL | External | durable task store, node state, audit records |
| Redis | External | hot progress cache, pub/sub, queueing, stream fanout |
| Object storage | External | large task artifacts if needed |
| Hermes integration layer | Internal library | runtime helpers behind Butler adapters |

### 2.3 Communication Patterns

| Pattern | Usage |
|---------|-------|
| Sync REST / gRPC | quick queries to Memory / ML / Tools |
| Async queue | long-running external actions |
| Pub/Sub | live progress and stream fanout |
| Durable store polling / leasing | resumable workflow execution |

---

## 3. Durable Execution Model

### 3.1 Why Durable Execution Exists
Butler tasks may survive:
- worker restarts
- pod replacement
- approval pauses
- delayed tool results
- reconnecting clients
- handoff completion on other workers

Redis alone is not enough for this. Durable execution state must live in a persistent store.

### 3.2 Source of Truth
- **PostgreSQL:** task records, node state, transitions, event log, approval checkpoints
- **Redis:** queueing, stream fanout, hot progress cache, locks, transient coordination
- **Object storage:** large artifacts, transcripts, or serialized handoff payloads when needed

### 3.3 Runtime Guarantees
- checkpoint after each committed node boundary
- persist event log before starting external side effects
- idempotent node re-entry
- resumable from last completed or paused boundary
- approval waits survive restarts
- streaming clients can reconnect and replay progress from durable state

---

## 4. Task Lifecycle

### 4.1 Full Request Lifecycle

```text
1. Receive normalized request from Gateway
       ↓
2. Bind session and channel state
       ↓
3. Select execution mode
       ↓
4. Resolve intent and entities
       ↓
5. Retrieve ranked context and candidates
       ↓
6. Run policy / approval analysis
       ↓
7. Build structured plan
       ↓
8. Validate feasibility and side-effect policy
       ↓
9. Execute with checkpoints, interrupts, and handoffs
       ↓
10. Verify or compensate
       ↓
11. Emit final response + stream completion
       ↓
12. Write back memory and analytics events
```

### 4.2 Task States

| State | Meaning |
|-------|---------|
| `received` | request accepted |
| `classifying` | intent/entity analysis running |
| `retrieving_context` | memory + candidate retrieval active |
| `planning` | structured plan generation active |
| `awaiting_approval` | blocked on user or policy decision |
| `ready_to_execute` | validated and executable |
| `executing` | runtime nodes in progress |
| `waiting_on_dependency` | blocked on prerequisite node |
| `waiting_on_external_event` | blocked on callback / external condition |
| `handoff_running` | delegated subagent / specialist in progress |
| `verifying` | result checks running |
| `compensating` | rollback / remediation running |
| `completed` | task finished successfully |
| `failed` | unrecoverable error |
| `cancelled` | explicitly stopped |

### 4.3 Interrupt Operations

```python
class InterruptManager:
    async def interrupt(self, task_id: str, reason: str, payload: dict): ...
    async def resume(self, task_id: str, decision: dict): ...
    async def cancel(self, task_id: str, actor_id: str): ...
    async def compensate(self, task_id: str, reason: str): ...
```

---

## 5. Understanding & Planning

### 5.1 Execution Modes

Before planning, Orchestrator classifies the request into one of:
- `answer_only`
- `retrieve_only`
- `action_only`
- `reason_and_act`
- `approval_sensitive`
- `long_running_workflow`
- `handoff_required`

### 5.2 Candidate Retrieval Coordinator

The rule is: **retrieve first, reason second**.

Inputs may include:
- ranked memory candidates from Memory
- workflow candidates from ML two-tower retrieval when enabled
- tool candidates from ML / Tools prefiltering when enabled
- current policy allowlist from guardrail engine

This keeps the planner focused on plausible options instead of the entire action universe.

For the MVP path, candidate reduction may still be rule-based and retrieval-light. The durable runtime model does **not** require ML to exist on day one.

### 5.3 Structured Planner

Planning must be schema-constrained, not prose-first.

```json
{
  "mode": "workflow",
  "goal": "send reminder and prepare tomorrow schedule",
  "requires_approval": false,
  "subagents": [],
  "nodes": [
    {
      "id": "n1",
      "kind": "tool_call",
      "tool": "calendar.fetch_tomorrow",
      "depends_on": []
    },
    {
      "id": "n2",
      "kind": "reason",
      "depends_on": ["n1"]
    },
    {
      "id": "n3",
      "kind": "tool_call",
      "tool": "notification.send",
      "depends_on": ["n2"]
    }
  ],
  "verification": [
    {
      "node_id": "n3",
      "check": "delivery_ack"
    }
  ]
}
```

### 5.4 Plan Validation

Validation must check:
- tool permissions and allowlists
- auth / approval requirements
- budget and latency limits
- dependency sanity
- channel / device constraints
- side-effect class and compensation availability

### 5.5 Capability Normalization Rule

The planner should reason over a **normalized capability graph**, not raw transport details.

- MCP adapters own protocol lifecycle such as initialization, operation, and shutdown
- Tools service exposes normalized tool metadata and invocation contracts
- Orchestrator consumes only normalized capabilities, policy tags, and execution constraints

This keeps protocol trivia out of planning and preserves clean runtime boundaries.

---

## 6. Policy, Approval, and Guardrails

### 6.1 Policy / Guardrail Engine

Responsibilities:
- action eligibility
- sensitivity classification
- approval requirement decision
- tool allowlist narrowing
- response redaction
- output safety checks

### 6.2 Approval Gates

Each plan node may be tagged:
- `safe_auto`
- `user_confirm`
- `step_up_auth`
- `restricted`
- `forbidden`

Runtime behavior is deterministic:
- auto-run safe nodes
- interrupt for confirmation nodes
- require step-up auth for sensitive nodes
- hard-block forbidden nodes

### 6.3 Approval States
- `awaiting_approval`
- `approved`
- `denied`
- `expired`

---

## 7. Workflow Runtime Engine

### 7.1 Runtime Node Model

```python
@dataclass
class PlanNode:
    id: str
    kind: Literal[
        "reason",
        "tool_call",
        "subagent_handoff",
        "approval_gate",
        "wait_event",
        "verify",
        "respond",
        "memory_write",
        "compensate",
    ]
    input_schema: dict
    output_schema: dict
    depends_on: list[str]
    timeout_s: int
    retry_policy: dict
    idempotency_key: str | None
    verifier: str | None
    compensation: str | None
    policy_tag: str | None
```

### 7.2 Runtime Capabilities
- DAG execution
- parallel groups
- branch conditions
- bounded loop limits
- approval gates
- wait states
- verification nodes
- compensation hooks
- checkpoint persistence
- replay-safe retries

### 7.3 Handoff Manager

Handoffs are allowed only when:
- domain specialization is needed
- policy permits delegation
- bounded scope is defined
- audit trail is preserved

Example targets:
- vision subagent
- research subagent
- finance subagent
- automation subagent
- voice interaction subagent

### 7.4 Handoff Contract
- target must be declared and typed
- handoff input schema is explicit
- handoff may return partial or full result
- parent task remains owner of lifecycle and audit trail
- handoff failures map into parent recovery policy

---

## 8. Context Assembly

### 8.1 Context Inputs

Context assembly should combine:
- session state
- active intent
- user preference profile
- negative preferences
- relationship context
- recent episodes
- relevant graph facts
- workflow / tool candidates
- policy constraints
- channel / device state
- approval / auth state
- token budget

### 8.2 Context Outputs

The context assembler should produce:
- `raw_context`
- `ranked_context_blocks`
- `prompt_view`
- `execution_constraints`
- `response_style_hints`

---

## 9. API Contracts

### 9.1 Internal Endpoints

```yaml
POST /orchestrate/process
  Request:
    {
      "message": "string",
      "user_id": "uuid",
      "session_id": "uuid",
      "channel": "mobile|web|voice|mcp|internal",
      "context": {}
    }
  Response:
    {
      "task_id": "uuid",
      "status": "received|planning|executing|awaiting_approval|completed|failed",
      "response": "optional string",
      "stream_id": "optional"
    }

POST /orchestrate/resume
  Request:
    {
      "task_id": "uuid",
      "decision": {}
    }

POST /orchestrate/cancel
  Request:
    {
      "task_id": "uuid"
    }

GET /orchestrate/status/{task_id}
  Response:
    {
      "status": "...",
      "progress": 0.5,
      "current_node": "n3",
      "awaiting": "approval|external_event|null"
    }

GET /orchestrate/events/{task_id}
  Response: event stream or paginated event log replay
```

---

## 10. Event Log & Streaming Lifecycle

### 10.1 Task Event Log

Orchestrator keeps an append-only event stream:
- `request.received`
- `intent.resolved`
- `candidates.retrieved`
- `plan.created`
- `node.started`
- `node.completed`
- `node.failed`
- `approval.requested`
- `approval.granted`
- `approval.denied`
- `handoff.started`
- `handoff.completed`
- `task.paused`
- `task.resumed`
- `response.emitted`
- `memory.writeback.completed`

### 10.2 Stream Events

Clients should be able to receive structured lifecycle updates:
- `intent.detected`
- `context.loaded`
- `plan.created`
- `tool.started`
- `tool.completed`
- `approval.required`
- `handoff.started`
- `task.paused`
- `task.resumed`
- `final.response`
- `error`

This avoids every client inventing its own spinner theology.

---

## 11. Scaling Strategy

### 11.1 Horizontal Scaling
- workers scale on durable task backlog + queue depth
- stateless compute workers over durable orchestration state
- Redis used for coordination, not as the only source of truth

### 11.2 Throughput Guidance

| Metric | Target |
|--------|--------|
| Concurrent tasks | 10K |
| Durable paused tasks | supported independently of active workers |
| Max plan nodes (initial target) | 20 |

### 11.3 Bottlenecks

| Bottleneck | Mitigation |
|------------|-------------|
| LLM calls | candidate reduction, timeout, fallback |
| Memory retrieval | cache + ranked context budget |
| Tool execution | async execution + wait states |
| Approval pauses | durable interrupt persistence |

---

## 12. Performance Targets

Targets are conditioned on warm paths and exclude human approval wait time.

| Operation | P50 | P95 | P99 |
|-----------|-----|-----|-----|
| Intent classification | 50ms | 100ms | 200ms |
| Context + candidate retrieval | 100ms | 250ms | 500ms |
| Structured plan creation (simple) | 200ms | 500ms | 1s |
| Simple direct response | 300ms | 700ms | 1.5s |
| Complex multi-tool runtime | 2s | 5s | 10s |

Notes:
- plan-creation targets assume candidate-reduced inputs
- workflow latency excludes human approval wait time
- long-running workflows may remain paused indefinitely while preserving state

---

## 13. Failure Handling

### 13.1 Failure Modes

| Failure | Handling |
|---------|----------|
| Unknown intent | clarifying flow or fallback |
| Partial node failure | retry / compensate / continue where safe |
| All tools fail | rule-based fallback response |
| Context retrieval timeout | use ranked cached context only |
| Worker restart | resume from last committed checkpoint |
| Approval timeout | expire or cancel task per policy |

### 13.2 Retry and Compensation
- retries use exponential backoff and bounded attempts
- external side effects require idempotency keys
- compensating nodes run when rollback is defined and required

---

## 14. Security Notes

- high-risk actions require explicit approval control
- all durable state changes are auditable
- handoffs preserve parent-task ownership and audit trail
- tool and subagent execution always run through normalized, policy-filtered surfaces
- imported libraries may help execution, but they must never define Butler lifecycle semantics

---

## 15. Observability

### 15.1 Required Metrics
- task throughput
- task state distribution
- approval wait time
- handoff latency
- resume success rate
- compensation rate
- node retry count
- stream event lag

### 15.2 Debug Surfaces
- per-task event log replay
- node transition timeline
- interruption / approval audit trail
- candidate retrieval summary for planning diagnostics

---

## 16. Testing Strategy

### 16.1 Required Tests
- structured plan schema validation
- checkpoint / resume after worker restart
- approval interrupt and resume flow
- handoff lifecycle and failure mapping
- compensation behavior for side-effecting nodes
- event-log replay correctness
- stream lifecycle contract correctness
- candidate-reduced planning on plausible option sets

---

## 17. Implementation Phases

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Sync request intake, classification, and planning | [IMPLEMENTED] |
| 2 | Durable executor with checkpointing and state persistence | [IMPLEMENTED] |
| 3 | Streaming event aggregator and real-time intake | [IMPLEMENTED] |
| 4 | SmartRouter (T0-T3) integration and tier-aware intake | [IMPLEMENTED] |
| 5 | Distributed handoff coordination and subagent fan-out | [STUB] |

---

*Document owner: Orchestrator Team*  
*Last updated: 2026-04-19*  
*Version: 3.0 (Active)*
