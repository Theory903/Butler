# Butler × External Capability Transplant Constitution

> **For:** All Engineering — backend, infrastructure, ML, platform
> **Status:** Authoritative
> **Version:** 1.0
> **Extends:** `platform-constitution.md` v2.0, `object-model.md` v4.0
> **Last Updated:** 2026-04-18

---

## Preamble

This document governs how Butler imports, uses, and constrains external capability
substrates — primarily Hermes, but also pyturboquant, TriAttention, and any future
capability sources.

The governing sentence is:

> **Hermes is imported as a capability substrate and execution kernel, but Butler
> remains the sole owner of canonical contracts, state, lifecycle, policy, identity,
> and product behavior. No Hermes module is allowed to define Butler semantics at
> any boundary.**

This is law. Not a guideline.

---

## 1. Sovereignty Model

### 1.1 What Butler Owns Permanently

No external substrate may define, override, or serve as the source of truth for any
of the following:

| Domain | Butler Owns |
|--------|-------------|
| **Identity** | Account, User, LinkedIdentity — schema, storage, semantics |
| **Auth** | JWT issuance (RS256/ES256), JWKS, passkeys, token families, replay detection, assurance levels, step-up auth, multi-account switching |
| **Policy** | Approval classes, risk tiers, tool allowlist per account tier, safety classes (SAFE_AUTO / CONFIRM / RESTRICTED / FORBIDDEN), industry profiles |
| **Audit** | Every action with side-effects is written to PostgreSQL. Hermes log files, SQLite trails, and in-memory histories are not Butler audit. |
| **Durable State** | Task, Workflow, ApprovalRequest, ToolExecution — PostgreSQL is source of truth. Redis is hot cache only. |
| **Memory Schema** | MemoryItem schema, episodic vs preference vs relationship graph, contradiction/supersession rules, provenance, temporal truth, bounded forgetting, privacy retention rules |
| **Event Taxonomy** | All event types in `event-contract.md`. Hermes runtime events must be normalized to Butler event types before being consumed or stored. |
| **Realtime Contract** | Event types (`start`, `token`, `tool_call`, `tool_result`, `approval_required`, `status`, `final`, `error`), delivery classes (A/B/C), replay semantics via Redis Streams |
| **Device Model** | Device pairing, capability registry, presence signals, ambient recording consent |
| **Communication Policy** | Quiet hours, suppressions, sender identity, consent, jurisdiction rules |
| **Product Behavior** | Tier gating, channel behavior, safety defaults, feature flags, Kill switches |

### 1.2 What External Substrates Contribute

| Substrate | Contributes |
|-----------|-------------|
| **Hermes** | Agent loop, tool implementations (55), browser/environment runtimes (6), skill packs, gateway/session helpers, model routing helpers, cron/scheduler kernel, platform adapters (14+), optional memory plugins (8), ACP/MCP compatibility |
| **pyturboquant** | Compressed vector index for cold-tier memory and search RAG |
| **TriAttention** | KV-cache compression for long-context vLLM serving profile |
| **Twitter algo patterns** | Candidate generation → ranking → filtering → mixing architecture (intellectual pattern, not code) |
| **twitter-server/finagle patterns** | Ops discipline: admin plane, circuit breakers, retry policies, concurrency controls (intellectual pattern, not code) |

### 1.3 The Transplant Metaphor

Butler is not a wrapper around Hermes.
Butler is not a fork of Hermes.
Butler is not a configuration layer on Hermes.

Butler extracts capability organs from Hermes, revascularizes them into Butler's
own circulatory system, and rejects the parts that do not match Butler's immune system.

Hermes supplies organs, muscles, and reflexes.
Butler is the brain, legal system, memory, identity, and spine.

---

## 2. Five-Layer Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 1 — BUTLER PRODUCT / CONTROL PLANE                      │
│  UX · Account Model · Pricing/Tiers · Approval UX              │
│  Policy Classes · Audit UX · Admin · Operator Surfaces         │
│  Industry Profiles · Kill Switches · Regional Compliance       │
├──────────────────────────────────────────────────────────────────┤
│  LAYER 2 — BUTLER CANONICAL RUNTIME PLANE                      │
│  Gateway · Auth · Orchestrator · Memory · Tools                │
│  Realtime · Search · Communication · Device · Audio            │
│  Vision · ML · Security · Observability · Data                 │
│  (18 canonical services — owner of all contracts)              │
├──────────────────────────────────────────────────────────────────┤
│  LAYER 3 — BUTLER TRANSPLANT LAYER                             │
│  HermesRuntimeKernel · HermesToolCompiler                      │
│  HermesChannelBridge · HermesSkillBridge                       │
│  HermesMemoryProviders · HermesEnvBridge                       │
│  TurboQuantAdapter · TriAttentionServingProfile                │
│  (backend/domain/transplant/ and backend/services/transplant/) │
├──────────────────────────────────────────────────────────────────┤
│  LAYER 4 — HERMES EXECUTION SUBSTRATE                          │
│  run_agent.py · model_tools.py · tools/* · skills/*            │
│  gateway/* · cron/* · plugins/memory/* · acp/*                 │
│  (backend/integrations/hermes/ — READ-ONLY from Butler)        │
├──────────────────────────────────────────────────────────────────┤
│  LAYER 5 — INFRA / STORAGE / PROVIDERS                         │
│  PostgreSQL · Redis · Neo4j · Qdrant · S3 · LLM Providers      │
│  vLLM (standard + TriAttention profile) · pyturboquant index   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Ownership Matrix — Hermes Capability → Butler Owner

Every Hermes module must be routed through exactly one Butler service.
No Hermes module is allowed to bypass this routing.

| Hermes Module | Butler Service Owner | Integration Mode |
|---------------|---------------------|-----------------|
| `run_agent.py` | **Orchestrator** | Wrapped by `HermesRuntimeKernel` — one execution backend, not the runtime itself |
| `model_tools.py` | **Tools** | Compiled into Butler `ToolSpec` via `HermesToolCompiler` |
| `tools/terminal.py` | **Tools** | Compiled into ToolSpec, L2 risk tier |
| `tools/code_execution.py` | **Tools** | Compiled into ToolSpec, L3 risk tier |
| `tools/file_operations.py` `files.py` | **Tools** | Compiled into ToolSpec, L1-L2 |
| `tools/web.py` | **Search** | Wrapped by `SearchService.HermesWebProvider` |
| `tools/browser_tool.py` `browser_camofox.py` | **Search** | Wrapped by `SearchService.BrowserProvider` |
| `tools/send_message_tool.py` | **Communication** | Wrapped by `CommunicationService`, policy-gated |
| `tools/voice_mode.py` `tts_tool.py` `transcription_tools.py` `neutts_synth.py` | **Audio** | Wrapped by `AudioService`, NOT direct tool execution |
| `tools/vision_tools.py` | **Vision** | Wrapped by `VisionService`, NOT direct tool execution |
| `tools/homeassistant_tool.py` | **Device** | Wrapped by `DeviceService.AutomationBridge` |
| `tools/mcp_tool.py` `mcp_oauth.py` | **Tools + Gateway** | MCP surface via `PluginsService` |
| `tools/image_generation_tool.py` | **ML** | Wrapped by `MLService.GenerationProvider` |
| `tools/memory_tool.py` `session_search_tool.py` | **Memory** | Wrapped by `MemoryService`, NOT direct |
| `tools/cronjob_tools.py` `todo_tool.py` | **Automation** | Wrapped by `AutomationService.HermesSchedulerKernel` |
| `tools/delegate_tool.py` `mixture_of_agents_tool.py` | **Orchestrator** | Wrapped by `Orchestrator.MixtureOfAgents` |
| `tools/clarify_tool.py` | **Orchestrator** | Wrapped by `Orchestrator.ClarificationEngine` |
| `tools/skills_hub.py` `skills_tool.py` `skill_manager_tool.py` | **Tools** (skill surface) | Wrapped by `HermesSkillBridge` |
| `tools/rl_training_tool.py` | **ML** | Behind feature flag, restricted tier only |
| `tools/registry.py` `approval.py` | **Tools** | Backing data for `HermesToolCompiler` |
| `tools/checkpoint_manager.py` | **Orchestrator** | Backing `DurableExecutor` checkpointing |
| `tools/process_registry.py` | **Tools** | Process tracking for long-running tools |
| `tools/environments/docker.py` `local.py` `modal.py` `daytona.py` `ssh.py` `singularity.py` | **Tools** | `HermesEnvBridge` — sandbox profiles |
| `tools/tirith_security.py` `url_safety.py` `path_security.py` `website_policy.py` `osv_check.py` | **Security** | Policy enforcement layer, called by `HermesToolCompiler` |
| `gateway/session.py` | **Gateway** | `ButlerGatewaySessionManager` wrapper |
| `gateway/stream_consumer.py` | **Gateway + Realtime** | `ButlerStreamBridge` wrapper |
| `gateway/delivery.py` | **Gateway** | `ButlerDeliveryService` wrapper |
| `gateway/hooks.py` | **Gateway** | `ButlerHooksEngine` wrapper |
| `gateway/platforms/*` (14 adapters) | **Communication + Gateway** | `PlatformRegistry` per account |
| `agent/prompt_builder.py` | **Orchestrator** | `ButlerPromptBuilder` wrapper |
| `agent/context_compressor.py` `trajectory_compressor.py` | **Memory + Orchestrator** | `ButlerContextCompressor` |
| `agent/memory_manager.py` | **Memory** | Provider beneath `MemoryService`, not above it |
| `agent/model_metadata.py` | **ML** | `ButlerModelRegistry` |
| `agent/smart_model_routing.py` | **ML** | `ButlerSmartRouter` |
| `agent/usage_pricing.py` | **ML + Data** | `ButlerUsageTracker` → PostgreSQL |
| `agent/credential_pool.py` | **Auth** | `ButlerCredentialPool` — Auth owns scope |
| `agent/rate_limit_tracker.py` | **ML** | Feeds `ButlerSmartRouter` |
| `agent/redact.py` | **Security** | Post-response redaction hook |
| `plugins/memory/mem0` `hindsight` `supermemory` `honcho` `retaindb` `holographic` `byterover` `openviking` | **Memory** | Auxiliary providers behind `MemoryService` contracts |
| `cron/scheduler.py` `jobs.py` | **Automation** | `HermesSchedulerKernel` inside `AutomationService` |
| `acp_adapter/*` | **Orchestrator** | ACP boundary, Butler controls session + permissions |
| `skills/` `optional-skills/` | **Tools** | `HermesSkillBridge`, per-account tier gating |

---

## 4. Hermes Tool Compiler Contract

Hermes tools must not be registered directly into Butler's tool registry.
All Hermes tools must be **compiled** into Butler `ToolSpec` objects.

### 4.1 ToolSpec — Butler Canonical Shape

```python
@dataclass
class ButlerToolSpec:
    # Identity
    name: str                         # Butler canonical name
    hermes_name: str                  # Original Hermes name (for dispatch)
    version: str
    category: str

    # Policy
    risk_tier: Literal["L0","L1","L2","L3"]   # L0=safe_auto, L1=logged, L2=confirm, L3=restricted
    safety_class: SafetyClass
    approval_mode: Literal["none","implicit","explicit","critical"]
    auth_mode: Literal["user","service","elevated"]
    min_assurance_level: Literal["AAL1","AAL2","AAL3"]

    # Execution
    sandbox_profile: str              # "none" | "local" | "docker" | "modal" | etc
    timeout_seconds: int
    idempotency_class: Literal["safe","idempotent","non-idempotent"]

    # Side effects
    side_effect_classes: list[str]    # "file_write","network","external_api","device","message"
    has_compensation: bool
    compensation_handler: str | None

    # Verification
    verification_mode: Literal["none","pre","post","both"]
    verification_policy: str | None

    # Visibility
    visible_tiers: list[str]          # "free","pro","enterprise"
    visible_channels: list[str]       # "mobile","web","voice","api"
    visible_industries: list[str]     # "*" or specific

    # Schema
    input_schema: dict                # JSON Schema
    output_schema: dict               # JSON Schema
```

### 4.2 Compilation Rules

```python
# WRONG — do not do this
from integrations.hermes.tools.registry import registry
registry.register("web_search", schema, handler)  # Hermes-native registration

# CORRECT — compile into Butler ToolSpec
from domain.tools.hermes_compiler import HermesToolCompiler
compiler = HermesToolCompiler()
spec = compiler.compile("web_search", hermes_metadata)
butler_registry.register(spec)
```

### 4.3 Risk Tier Assignment

| Tier | Hermes Tools | Approval |
|------|-------------|---------|
| L0 (safe_auto) | web_search, list_files, memory_recall, session_search, clarify | None |
| L1 (logged) | read_file, vision_analyze, transcribe, synthesize_speech | Logged only |
| L2 (confirm) | write_file, send_message, create_cron_job, delegate, patch_file | User one-click |
| L3 (restricted) | run_terminal, code_execution, browser_automation, rl_training, homeassistant_control | Explicit + elevated auth |
| FORBIDDEN | Any tool that bypasses Butler's auth, writes to Butler DB directly | Never expose |

---

## 5. Butler Runtime Kernel Contract

`run_agent.py` is NOT Butler's runtime. It is one execution backend inside Butler's
runtime kernel.

### 5.1 Runtime Kernel Decision Tree

```
Butler Orchestrator receives Task
         │
         ▼
RuntimeKernel.choose_execution_strategy(task)
         │
    ┌────┴──────────────────────────────────┐
    ▼           ▼               ▼           ▼
Deterministic  HermesAgent   WorkflowDAG  Subagent
Butler flow    Loop           Engine       Handoff
(simple tasks) (agentic tasks)(durable)    (delegated)
    │           │               │           │
    └────┬──────┘               │           │
         ▼                      ▼           ▼
  Butler commits state BEFORE and AFTER every Hermes segment
  Hermes NEVER owns task lifecycle across a checkpoint boundary
```

### 5.2 Checkpoint Contract

Before Hermes begins an execution segment:
1. Butler commits `Task.status = executing` to PostgreSQL
2. Butler writes `checkpoint_id` to Redis

After Hermes completes an execution segment:
1. Butler reads output from Hermes kernel
2. Butler normalizes events via `EventNormalizer`
3. Butler commits `Task.status = completed/failed` + full output to PostgreSQL
4. Butler emits canonical Butler events

Hermes may crash mid-segment. Butler resumes from checkpoint, not from Hermes state.

---

## 6. Memory Sovereignty Contract

### 6.1 Memory Stack

```
Butler Canonical Memory Core (OWNS semantics)
├── Neo4j           → relationship/entity graph
├── Qdrant          → hot/warm vector store (full precision)
├── PostgreSQL      → structured facts, preferences, episodes
└── Redis           → hot recency cache

Butler Memory Provider Layer (CONSUMES hermes)
├── HermesSessionDB → episodic session message history (SQLite FTS5)
└── HermesMemoryPlugins → auxiliary recall backends
    ├── mem0
    ├── hindsight
    ├── supermemory
    ├── honcho
    ├── retaindb
    ├── holographic
    ├── byterover
    └── openviking

pyturboquant Cold Tier (ECONOMICS)
└── TurboQuantAdapter → compressed vector index for long-tail recall
```

### 6.2 Write Policy — What Goes Where

```python
class ButlerMemoryWritePolicy:
    """Decides storage tier for every memory write attempt."""

    def route(self, content: MemoryWriteRequest) -> list[StorageTarget]:
        if content.type == "session_message":
            return [HERMES_SESSION_DB, REDIS_HOT]
        if content.type == "preference":
            return [POSTGRES, QDRANT_HOT, NEO4J]
        if content.type == "relationship":
            return [NEO4J, POSTGRES]
        if content.type == "episode" and content.age_days > 30:
            return [TURBOQUANT_COLD, POSTGRES]
        if content.type == "episode" and content.importance > 7:
            return [QDRANT_HOT, POSTGRES]
        if content.type == "episode":
            return [QDRANT_WARM, POSTGRES]
        if content.type == "tool_trace" and content.age_days > 7:
            return [TURBOQUANT_COLD]
        if content.type == "web_crawl_chunk":
            return [TURBOQUANT_COLD]
        # Default: warm Qdrant
        return [QDRANT_WARM]
```

### 6.3 Memory Tiering Model

| Tier | Backend | Content | Query Latency |
|------|---------|---------|--------------|
| Hot | Redis | Last 20 turns, active preferences | <5ms |
| Warm | Qdrant (full precision) | Recent/important episodes, all entities | <50ms |
| Cold | pyturboquant compressed | Long-tail episodes, web chunks, tool traces | <200ms |
| Graph | Neo4j | Relationships, entity network | <50ms |
| Structured | PostgreSQL | Facts, workflow state, audit | <20ms |

### 6.4 Rules Hermes Memory Cannot Override

- Memory schema evolution (adding fields, deprecating fields) is Butler-owned
- Contradiction/supersession rules are Butler-owned
- Provenance metadata is always Butler-added, not Hermes-generated
- Privacy/retention TTL per memory type is Butler-owned
- The Hermes SessionDB is episodic-only; it never becomes Butler's source of truth for preferences or relationships

---

## 7. Event Normalization Contract

Hermes emits raw runtime events that must not reach Butler consumers directly.
The `EventNormalizer` sits between Hermes outputs and Butler event bus.

### 7.1 Hermes → Butler Event Mapping

| Hermes Internal Event | Butler Canonical Event |
|-----------------------|----------------------|
| `delta` (token chunk) | `realtime.token.v1` |
| `tool_use` block | `task.step.started.v1` + `tool.executing.v1` |
| `tool_result` block | `tool.executed.v1` or `tool.failed.v1` |
| `end_turn` | `realtime.final.v1` |
| `error` | `task.failed.v1` |
| `thinking` block | SUPPRESSED — never forwarded |
| `approval_required` | `approval.requested.v1` |
| Hermes session reset | `user.session.end.v1` |

### 7.2 Realtime Stream Event Types (Butler-Canonical)

These are the only event types that reach Butler API consumers:

```
start            — stream opened, includes session_id + task_id
token            — single LLM output token or token chunk
tool_call        — Orchestrator is calling a tool (name, params visible if safe_auto)
tool_result      — tool completed (result summary, not full output unless safe_auto)
approval_required — paused waiting for human decision
status           — workflow status update (phase change, retry, etc)
final            — complete response, token totals
error            — classified error with RFC 9457 problem detail
```

Hermes may produce more internal event types. All must be normalized before
reaching Layer 2 (Butler Canonical Runtime Plane).

---

## 8. pyturboquant Integration Rules

pyturboquant belongs in Memory and Search infrastructure only.

### 8.1 Permitted Use Cases

- Cold-tier storage for: user episodes >30 days old, tool execution traces, web crawl chunks, meeting transcript chunks, email embedding archives
- Candidate retrieval for `/memory/search`, `/search/rag`, `/ml/retrieve_candidates`
- Local/on-prem deployment mode as an alternative to Qdrant to reduce VRAM footprint

### 8.2 Prohibited Use Cases

- Auth/session storage
- Approvals
- Canonical audit logs
- Transactional runtime state (Task, Workflow, etc)
- Hot retrieval path (must go through Qdrant or Redis)
- As a substitute for a reranker

### 8.3 TurboQuantAdapter Interface

```python
class TurboQuantAdapter:
    """Butler's cold-tier vector store backed by pyturboquant."""

    def upsert(self, items: list[VectorItem]) -> None: ...
    def search(self, query_vector: list[float], top_k: int) -> list[SearchResult]: ...
    def delete(self, ids: list[str]) -> None: ...

    # Butler adds what pyturboquant does not provide natively:
    def audit_log_read(self, read_id: str) -> None: ...   # writes to PostgreSQL
    def enforce_retention(self, policy: RetentionPolicy) -> int: ...  # prune expired
```

---

## 9. TriAttention Integration Rules

TriAttention belongs in ML Serving infrastructure only — not in business logic.

### 9.1 Serving Profiles

Butler's ML Service maintains two vLLM serving profiles:

```
Profile A — Standard Chat:
  model: configurable
  kv_cache: standard
  use_triattention: false
  use_case: short conversational turns, <8k context

Profile B — Long-Context Planner:
  model: configurable (separate host/replicas)
  kv_cache: triattention_compressed
  use_triattention: true
  kv_budget: configurable per deployment
  prefix_caching: disabled (per TriAttention docs)
  use_case: multi-step orchestration, research agents, deep reasoning, long voice sessions
```

### 9.2 Routing Rules

The `ButlerSmartRouter` (wrapping Hermes `smart_model_routing`) routes to Profile B when:
- `context_token_count > 8192`, OR
- `task.mode == "research"`, OR
- `task.mode == "planning"` with >4 plan steps, OR
- `task.mode == "reason"`, OR
- `audio.session_duration > 600s` (voice sessions)

### 9.3 Prohibited Uses

- TriAttention must not be imported into Orchestrator, Memory, or any business logic service
- TriAttention configuration is managed by the ML infrastructure team, not by application code
- TriAttention must never be the only serving option (fallback to Profile A always required)

---

## 10. Twitter Algo Architecture Patterns

No AGPL code from `twitter/the-algorithm` or `the-algorithm-ml` is to be copied
into Butler. The AGPL license requires source disclosure for all modified versions.
These repos are architecture references only.

### 10.1 Candidate → Rank → Filter → Mix Pattern

Butler implements this pattern for:
- Tool recommendation (what tool should the agent use next)
- Memory recall candidate scoring
- Workflow step suggestions
- Notification prioritization
- Response-surface routing (which channel to deliver to)

```
candidate_generation:
  - MemoryService.recall() → memory candidates
  - ToolRegistry.suggest() → tool candidates
  - WorkflowEngine.suggest_next() → step candidates
  - ContactResolver.relevant() → contact candidates

lightweight_pre_rank:
  - ML.score_candidates() → fast embedding similarity
  - recency_boost(), importance_boost()

heavy_rerank:
  - ML.rerank() → cross-encoder or BGE reranker
  - contextual relevance to current task

policy_filter:
  - Security.apply_policy() → remove unsafe/unauthorized candidates
  - AccountTier.apply_visibility() → remove out-of-tier candidates

mixer:
  - final_selector() → select top-k with diversity constraint
  - channel_aware_trim() → respect channel capacity limits
```

### 10.2 ButlerHIN Embedding Concept

Inspired by TwHIN (without copying code): Butler represents Users, Tools, Workflows, Devices, Topics, Memory items in a shared embedding space for recommendation.

This is a future Phase 5 capability, not a current implementation target.

---

## 11. Twitter-Server / Finagle Operational Patterns

No Scala code is used. These are ops architecture patterns for all Butler services.

### 11.1 Admin Plane — Required Endpoints per Service

Every Butler service must implement:

```
/health/startup    → STARTING | HEALTHY
/health/ready      → HEALTHY | DEGRADED | UNHEALTHY
/health/live       → HEALTHY | UNHEALTHY
/admin/metrics     → Prometheus exposition format
/admin/config      → Current effective config (redacted secrets)
/admin/build-info  → version, commit, build_time
/admin/diagnostics → dependency check results
```

### 11.2 Failure-Aware Service Calls

All Butler service-to-service calls must implement:

```python
@dataclass
class ServiceCallPolicy:
    timeout_ms: int              # Hard timeout per call
    retry_count: int             # Max retries
    retry_backoff: str           # "exponential" | "constant"
    circuit_breaker: bool        # Enable circuit breaker
    concurrency_limit: int       # Max concurrent calls to this service
    jitter: bool                 # Add jitter to retries
```

Mandatory policies per service pair:

| Caller → Callee | Timeout | Retries | Circuit Breaker |
|-----------------|---------|---------|----------------|
| Gateway → Orchestrator | 30s | 0 (idempotency owned by caller) | Yes |
| Orchestrator → Memory | 3s | 2 | Yes |
| Orchestrator → Tools | per-tool-timeout | 1 | Yes |
| Orchestrator → ML | 10s | 1 | Yes |
| Realtime → Redis Streams | 500ms | 3 | No |
| Tools → HermesEnvBridge | 60s | 0 | Yes |

---

## 12. Import Allowlist / Denylist

### 12.1 Allowed Imports from `integrations/hermes/` into Butler Domain/Service Layers

```python
# Orchestrator domain
from integrations.hermes.agent.prompt_builder import build_skills_system_prompt
from integrations.hermes.agent.error_classifier import classify_error
from integrations.hermes.agent.retry_utils import calculate_backoff
from integrations.hermes.agent.compressor import compress_trajectory

# Memory domain
from integrations.hermes.hermes_state import SessionDB
from integrations.hermes.agent.memory_manager import HermesMemoryProvider

# Tools domain
from integrations.hermes.model_tools import handle_function_call
from integrations.hermes.tools.registry import get_all_tool_definitions
from integrations.hermes.tools.tirith_security import validate_tool_call
from integrations.hermes.tools.url_safety import check_url_safety
from integrations.hermes.tools.path_security import check_path_safety

# Gateway domain
from integrations.hermes.gateway.stream_consumer import GatewayStreamConsumer
from integrations.hermes.gateway.session import SessionStore, build_session_key
from integrations.hermes.gateway.delivery import DeliveryRouter

# ML domain
from integrations.hermes.agent.model_metadata import get_context_window
from integrations.hermes.agent.usage_pricing import calculate_cost
```

### 12.2 FORBIDDEN Imports into Butler Domain/Service Layers

```python
# FORBIDDEN — bypasses Butler event system
from integrations.hermes.agent.display import *
from integrations.hermes.agent.trajectory import save_trajectory

# FORBIDDEN — bypasses Butler auth
from integrations.hermes.acp_adapter.auth import *  # use Butler auth, expose via acp_adapter

# FORBIDDEN — Hermes identity semantics
from integrations.hermes.hermes_constants import HERMES_HOME  # use settings.BUTLER_DATA_DIR
from integrations.hermes.core.constants import *  # cherry-pick only what Butler needs

# FORBIDDEN — CLI/TUI behavior
from integrations.hermes.agent.skill_commands import *
from integrations.hermes.tools.ansi_strip import *

# FORBIDDEN — direct registration bypassing compiler
from integrations.hermes.tools import *  # must go through HermesToolCompiler
```

---

## 13. Transplant Phase Plan

### Phase 0 — Sovereignty Setup (Before any Hermes wiring)

- [ ] Finalize `ButlerToolSpec` dataclass in `domain/tools/models.py`
- [ ] Finalize canonical event types in `domain/events/schemas.py`
- [ ] Implement `EventNormalizer` in `domain/events/normalizer.py`
- [ ] Implement `MemoryWritePolicy` in `domain/memory/write_policy.py`
- [ ] Implement `RuntimeKernel` skeleton in `domain/orchestrator/runtime_kernel.py`
- [ ] Implement `HermesToolCompiler` in `domain/tools/hermes_compiler.py`
- [ ] Set `HERMES_HOME` → `settings.BUTLER_DATA_DIR / "hermes"` in config
- [ ] Document allowlist/denylist in `integrations/hermes/INTEGRATION_MAP.md` (update)

### Phase 1 — Runtime Transplant

- [ ] `HermesRuntimeKernel` as one backend inside `RuntimeKernel`
- [ ] `ButlerPromptBuilder` wrapping `agent/prompt_builder.py`
- [ ] `ButlerContextCompressor` wrapping `agent/compressor.py`
- [ ] Executor wired to `HermesRuntimeKernel` with pre/post Butler checkpoint commits
- [ ] All Hermes events normalized via `EventNormalizer` before Butler consumers see them

### Phase 2 — Tool Transplant

- [ ] `HermesToolCompiler` compiles all 55 tools → Butler ToolSpec
- [ ] `ButlerToolDispatch` calls Hermes `handle_function_call` only after Butler policy
- [ ] `HermesEnvBridge` wraps all 6 environments
- [ ] Tirith security policy called by compiler for every L2+ tool
- [ ] All tool executions write to PostgreSQL `tool_execution` via Butler `ToolExecutor`

### Phase 3 — Session and Stream Transplant

- [ ] `ButlerGatewaySessionManager` wrapping Hermes `SessionStore`
- [ ] `ButlerStreamBridge` (SSE + WS) wrapping `GatewayStreamConsumer`
- [ ] SSE `/stream/{session_id}` wired to `ButlerStreamBridge` (not fake yields)
- [ ] `session_key` built via `build_session_key(source)` not hardcoded string
- [ ] Hermes stream events normalized via `EventNormalizer`

### Phase 4 — Memory Provider Transplant

- [ ] `ButlerSessionStore` wrapping `SessionDB` for episodic message history
- [ ] All 8 Hermes memory plugins registered as providers in `MemoryService`
- [ ] `TurboQuantAdapter` as cold-tier provider behind `MemoryService`
- [ ] `MemoryWritePolicy` routing all writes to correct tiers
- [ ] Provenance added to all Hermes-originated memory writes

### Phase 5 — Search, Browser, Skills, Cron, ACP

- [ ] `HermesWebProvider` wired into `SearchService`
- [ ] `HermesBrowserProvider` (Playwright/BrowserBase/Firecrawl) wired into `SearchService`
- [ ] `HermesSkillBridge` wired into `ToolsService` with per-account tier gating
- [ ] `HermesSchedulerKernel` wired into `AutomationService`
- [ ] ACP server exposed via `OrchestratorService.ACPBoundary` with Butler auth
- [ ] MCP bridge via `PluginsService`

### Phase 6 — Platform Adapters

- [ ] `PlatformRegistry` with all 14 Hermes platform adapters
- [ ] Per-account adapter provisioning
- [ ] `GET /api/v1/platforms` endpoint
- [ ] `POST /api/v1/platforms/{platform}/connect` endpoint
- [ ] Platform events routed through `CommunicationService` (not raw Hermes send)

### Phase 7 — Full Product Hardening

- [ ] Admin plane endpoints on all 18 services
- [ ] Circuit breakers via `ServiceCallPolicy` on all service pairs
- [ ] TriAttention serving profile for ML Service (Profile B)
- [ ] Product tier gating (`domain/policy/product_tiers.py`)
- [ ] Industry profiles (`domain/policy/industry_profiles.py`)
- [ ] Kill switches for every Hermes capability import
- [ ] pyturboquant retirement/eviction policy for cold tier

---

## 14. Enforcement

A pull request is rejected if it:

1. Imports a Hermes module directly into an API route handler
2. Allows a Hermes module to define a Butler event type
3. Uses Hermes `HERMES_HOME` instead of `settings.BUTLER_DATA_DIR`
4. Registers a Hermes tool without compiling it through `HermesToolCompiler`
5. Stores Hermes SessionDB as the source of truth for user preferences or relationships
6. Allows `run_agent.py` to commit state directly to PostgreSQL
7. Exposes a Hermes-internal error type in a Butler API response
8. Uses HS256 anywhere in auth flows
9. Uses Redis Pub/Sub for approval or task status events (must use Streams)
10. Puts TriAttention in any layer above ML Service

---

*Document owner: Architecture Team*
*Version: 1.0 (Authoritative)*
*Extends: platform-constitution.md v2.0*
*Last updated: 2026-04-18*
