# The Butler Master Archive: The Grand Technical & Philosophical Blueprint (v1.0)

> **Status:** Canonical Master Archive  
> **Version:** 1.0 (Oracle-Grade)  
> **Scope:** Full-System Consolidation (5000+ Lines)  
> **Source Documents:** Consolidating ~100 files from `/docs` tree  
> **Updated:** 2026-04-20

---

## Table of Contents

1. [Chapter 1: The Butler Constitution & Philosophy](#chapter-1-the-butler-constitution--philosophy)
2. [Chapter 2: Governance & Platform Standards](#chapter-2-governance--platform-standards)
3. [Chapter 3: The Intelligence Plane (The Brain)](#chapter-3-the-intelligence-plane-the-brain)
4. [Chapter 4: The Butler Workflow Language (BWL) v1.0](#chapter-4-the-butler-workflow-language-bwl-v10)
5. [Chapter 5: Memory, Personalization & The Digital Twin](#chapter-5-memory-personalization--the-digital-twin)
6. [Chapter 6: The Action Plane & The 18 Services](#chapter-6-the-action-plane--the-18-services)
7. [Chapter 7: The Capability Matrix & Tool Registry](#chapter-7-the-capability-matrix--tool-registry)
8. [Chapter 8: Agentic Runtime & Subagent Isolation](#chapter-8-agentic-runtime--subagent-isolation)
9. [Chapter 9: The Ambient Edge (IOT, Mobile, Robotics)](#chapter-9-the-ambient-edge-iot-mobile-robotics)
10. [Chapter 10: Security, Policy & Safety Kernel](#chapter-10-security-policy--safety-kernel)
11. [Chapter 11: Operations, SRE & Observability](#chapter-11-operations-sre--observability)
12. [Chapter 12: The Master Roadmap (2026-2027)](#chapter-12-the-master-roadmap-2026-2027)

---

## Chapter 1: The Butler Constitution & Philosophy

### 1.1 The "Agent-as-OS" Paradigm

Butler is not a chatbot. It is a **Personal AI Execution Operating System**. In a traditional OS, the kernel manages physical resources (CPU, RAM, Disk). In Butler, the **Intelligence Kernel** manages **Capabilities**, **Memory**, **Identity**, and **Trust** across a modular grid of 18 services.

#### 1.1.1 The Five Pillars of Butler

1. **Durable**: Work must survive restarts, network partitions, and human-in-the-loop delays.
2. **Personal**: Butler learns, remembers, and predicts based on a high-fidelity "Digital Twin."
3. **Ambient**: Butler crosses the digital/physical boundary via IOT, Mobile, and Wearables.
4. **Governed**: Every action is policy-gated. No "hallucinated actions" occur without a capability grant.
5. **Human-Centric**: Butler serves the user's intent while respecting privacy and autonomy.

### 1.2 Platform Mission

The project's mission is to move from **Passive Support** to **Autonomous Stewardship**.

- **Observe**: Collect context from the user's environment (Sensors, APIs, Voice).
- **Remember**: Build a temporal knowledge graph of preferences, relationships, and history.
- **Decide**: Use a tiered reasoning engine (Macro -> Routine -> Durable) to select the best action.
- **Act**: Execute multi-step workflows across toolsets and devices.
- **Learn**: Self-correct based on human feedback and task success metrics.

### 1.3 Operational Philosophy (Oracle-Grade)

Butler follows the **Oracle-Grade** standard for production readiness:

- **No HS256**: All identity tokens must be RS256/ES256 with a public JWKS endpoint.
- **No Custom Envelopes**: Errors follow **RFC 9457** (Problem Details).
- **No Universal Envelopes**: APIs use standard HTTP verbs and status codes.
- **No Mock Security**: Real Argon2id hashing, RS256/ES256 validation, and least-privilege scoping are enforced from day zero.

---

## Chapter 2: Governance & Platform Standards

### 2.1 The Request Envelope (RFC-Aligned)

Every interaction in the Butler system proceeds via a canonical request envelope. This ensures traceability and auditability across service boundaries.

```json
{
  "request_id": "req_...",
  "trace_id": "trc_...",
  "channel": "mobile|web|watch|voice|system",
  "device_id": "dev_...",
  "actor": {
    "type": "user|assistant|tool|system",
    "id": "acc_..."
  },
  "timestamp": "ISO8601",
  "idempotency_key": "unique_string",
  "payload": {}
}
```

### 2.2 Global Service Catalog (The 18 Services)

The system is organized as a **Modular Monolith** with 18 distinct services.

#### 2.2.1 Identity & Control Plane

1. **Auth Service**: Identity lifecycle, session management, and JWKS distribution.
2. **Security Service**: Global policy engine, capability gating, and redaction.
3. **Gateway Service**: Edge transport layer, rate limiting, and normalization.

#### 2.2.2 Intelligence Plane (The Brain)

4. **Orchestrator Service**: Intent classification, planning, and task coordination.
5. **Memory Service**: LTM management (Episodic, Semantic, Entity).
6. **ML Service**: Embeddings, reranking, and specialized model routing.
7. **Search Service**: Evidence-backed research and content extraction.

#### 2.2.3 Action Plane (Execution)

8. **Tools Service**: Registry for 100+ native and bridged capability tools.
9. **Realtime Service**: WebSocket/SSE management and live event streaming.
10. **Communication Service**: Multi-channel delivery (SMS, Email, WA, Push).
11. **Workflows Service**: Durable state machines and BWL v1.0 execution.
12. **Automation Service**: Trigger/Action scheduler (Cron-style and event-driven).

#### 2.2.4 Perception & Environment

13. **Device Service**: IoT mesh adapter and device-specific state mirroring.
14. **Vision Service**: Image reasoning, OCR, and object grounding.
15. **Audio Service**: STT/TTS pipeline with real-time diarization.
16. **Plugins Service**: Extension manager for ClawHub and MCP servers.

#### 2.2.5 Platform Backbone

17. **Data Service**: PostgreSQL persistence layer and Alembic migrations.
18. **Observability Service**: OTel instrumentation, metrics, and tracing.

### 2.3 The Four-State Health Model

Every service MUST expose a health model that identifies its operational readiness:

- **STARTING**: Initializing resources, connecting to DB/Cache.
- **HEALTHY**: Fully operational, high-performance mode.
- **DEGRADED**: Operational but with failures in non-critical dependencies.
- **UNHEALTHY**: Critical failures; service cannot process requests.

### 2.4 Error Standards (RFC 9457)

All errors in the Butler ecosystem are returned as **Problem Details**.

```json
{
  "type": "https://docs.butler.ai/problems/insufficient-permissions",
  "title": "Forbidden",
  "status": 403,
  "detail": "Tool requires 'PAYMENT_WRITE' capability which is not in current scope.",
  "instance": "/api/v1/tools/execute/payment#req_123"
}
```

---

## Chapter 3: The Intelligence Plane (The Brain)

Butler's Intelligence Plane is the central reasoning hub that transforms raw user intent into actionable, durable plans. It operates on a "Retrieve First, Reason Second" principle to ensure cost efficiency and technical grounding.

### 3.1 The Orchestrator Service (Core Reasoning)

The Orchestrator is the conductor of the Butler 18-service grid. It manages the intake pipeline and the plan-generation lifecycle.

#### 3.1.1 The Intake Pipeline

1. **Normalization**: Every incoming request is wrapped in the canonical `ButlerEnvelope`.
2. **Context Enrichment**: The `MemoryService` and `IdentityService` provide a "Context Bundle" containing session history, user preferences, and security trust levels.
3. **Intent Classification**: The `MLService` classifies the intent into T0-T3 tiers (T0: Directive, T1: Inquiry, T2: Transaction, T3: Long-running/Amorphous).
4. **Mode Selection**: Based on intent complexity, the Orchestrator selects the execution tier (Macro, Routine, or Durable).

#### 3.1.2 The Plan Engine

The Orchestrator doesn't just guess; it constructs a **Durable Plan**.
- **Planning Loop**: Intent -> Goal Extraction -> Step Decomposition -> Dependency Mapping -> BWL Serialization.
- **Decision Trees**: Butler uses a dynamic decision tree to resolve ambiguities before action. If confidence < 0.85, a `ClarificationRequest` is emitted.

### 3.2 The Memory Service (Persistence of Context)

Memory in Butler is a system-wide capability, not just a storage backend. It uses a **Hybrid Temporal Model**.

#### 3.2.1 Episodic Memory (Turns)

- **Engine**: PostgreSQL (Partitioned).
- **Structure**: Every interaction is a "Turn" (Request/Response/Trace).
- **Utility**: Allows the Orchestrator to "Recall" what was just said or what happened in a similar context last week.

#### 3.2.2 Semantic Memory (Facts)

- **Engine**: Qdrant (Vector DB).
- **Structure**: Dense embeddings of documents, facts, and conversation summaries.
- **Utility**: RAG (Retrieval-Augmented Generation) for evidence-backed answers.

#### 3.2.3 Entity & Knowledge Memory (Graph)

- **Engine**: Neo4j.
- **Structure**: Knowledge graph nodes (User, Place, Topic, Service) and Edges (Likes, Visited, Used).
- **Utility**: Complex relationship reasoning (e.g., "Find the restaurant I liked in Seattle").

### 3.3 The ML Service (Intelligence Primitives)

The ML service provides the raw cognitive primitives used by the Orchestrator.

- **Model Tiers**: Small (Local Llama), Medium (Gemma/Mistral), and Large (Gemini/GPT-4) based on safety class and complexity.
- **Reranking**: Cross-encoding results from the Memory service to select the top 3 most relevant context pieces.
- **Confidence Calibration**: Every prediction from the ML service must include a confidence score and a "Reasoning Trace" (Reasoning tokens in the internal envelope, redacted in the final response).

---

## Chapter 4: The Butler Workflow Language (BWL) v1.0

BWL v1.0 is the definitive DSL for agentic durable execution in the Butler ecosystem. It provides a structured, versioned, and deterministic vocabulary for defining complex behaviors.

### 4.1 BWL Core Vocabulary (The 12 Primitives)

Every BWL execution is a Directed Acyclic Graph (DAG) composed of these node types:

| Node Type | Definition | Oracle-Grade Rule |
|-----------|------------|-------------------|
| **Task** | A call to a registered tool or service. | Must declare `idempotency_key_template`. |
| **Choice** | A conditional branch (If/Else or Switch). | Expressions must be deterministic and pure. |
| **Parallel** | Concurrent execution branches. | Must define a `join_policy` (All/Any/N). |
| **Wait** | A resumable time delay. | Never use `time.sleep()`; must checkpoint state. |
| **Approval** | A human-in-the-loop gate. | Suspends execution and emits a `SignalTicket`. |
| **SignalWait** | Pausing until an external event arrives. | Must match a signature in `WorkflowSignals`. |
| **Subagent** | Spawning a child Execution Kernel. | Enforces **Iron Law of Inheritance** (Least Trust). |
| **MemoryBind** | Explicitly binding LTM scope. | Filters vector/graph retrieval by CID/UID. |
| **CapabilityGate**| Enforcing security zones. | Validated against `CapabilityRegistry` at runtime. |
| **HumanInput** | Requesting a specific value/param. | Must follow canonical UI schema for mobile/web. |
| **Compensation** | Rollback logic for branch failure. | Side-effects must be reversible (e.g., Delete/Cancel). |
| **Success/Fail** | Terminal nodes. | Success requires `OutcomeSummary` and result data. |

### 4.2 The Execution Tier Hierarchy

Butler avoids "DAG Overload" by tiering execution according to the speed of the user's life.

#### 4.2.1 Tier 1: Macro Execution (Fast)

- **Engine**: `MacroRuntime`.
- **Latency**: < 100ms.
- **Behavior**: Pre-compiled BWL sequences with pre-populated slots.
- **Example**: "Goodnight Butler" -> [Turn off lights, Set alarm, Mute phone].

#### 4.2.2 Tier 2: Routine Execution (Recurring)

- **Engine**: `RoutineRuntime` (Triggered via `AutomationService`).
- **Behavior**: Context-aware workflows triggered by time, location, or telemetry indicators (Context-Aware Cron).
- **Example**: "Morning Briefing" triggered on first phone unlock after 07:00.

#### 4.2.3 Tier 3: Durable Workflow Execution (Complex)

- **Engine**: `DurableExecutor`.
- **Behavior**: Long-running, multi-day coordination tasks.
- **Durability**: Survives system reboots, server migrations, and long waits for human signal.
- **Implementation**: Uses **Deterministic Replay** involving an append-only event log.

### 4.3 The Repetition Promotion Pipeline

Butler observes user behavior and "Promotes" repeated actions up the hierarchy:

1. **Ad-hoc**: "Butler, do X."
2. **Suggested Macro**: "I've noticed you do [A -> B -> C] often. Shall I make a 'Morning Brief' macro?"
3. **Routine**: Macro promoted to a trigger-driven behavior.
4. **Durable**: Complex Routine promoted to a resumable workflow if coordination becomes reliable.

---

## Chapter 5: Memory, Personalization & The Digital Twin

Memory in Butler is not just a database; it is a **Cognitive Capability**. It provides the system with "Persistence of Self" and the ability to anticipate user needs through high-fidelity context.

### 5.1 The Hybrid Memory Model

Butler uses a multi-layered storage strategy to balance latency, recall depth, and reasoning complexity.

#### 5.1.1 Episodic Memory (The Narrative)

- **Primary Engine**: PostgreSQL (Partitioned).
- **Data Model**: Every conversation turn, side-effect (tool call), and resulting observation is a `Turn` record.
- **Metadata**: Includes timestamps, confidence scores, session IDs, and trace links.
- **Utility**: Allows the agent to "Backtrack" and understand the sequence of events leading to the current state.

#### 5.1.2 Semantic Memory (The Knowledge Base)

- **Primary Engine**: Qdrant (Vector Database).
- **Embedding Model**: BGE-Large (or user-configured Enterprise model).
- **Interaction**: RAG (Retrieval-Augmented Generation).
- **Utility**: Provides access to massive amounts of unstructured data (files, web research, old interaction summaries) via semantic similarity.

#### 5.1.3 Entity & Knowledge Memory (The Relationship Graph)

- **Primary Engine**: Neo4j (Graph Database).
- **Nodes**: Users, Entities (People, Companies, Places), Projects, Services, and Devices.
- **Edges**: `KNOWS`, `WORKS_AT`, `LOCATED_IN`, `LIKES`, `USED_BY`.
- **Utility**: Enables multi-hop reasoning (e.g., "Find the person I met last week who works at the same company as Alice").

### 5.2 The Personalization & Ranking Engine

Inspired by Twitter's recommendation pipelines (The Algorithm), Butler treats memory retrieval as a **Ranking Problem**.

#### 5.2.1 The Retrieval Pipeline

1. **Candidate Generation**: Sourcing ~200 items from Postgres (recency), Qdrant (semantic), and Neo4j (graph neighbors).
2. **Feature Hydration**: Enriching candidates with real-time features (access frequency, user interest score, session relevance).
3. **LightRanker**: A high-performance heuristic scoring function (< 5ms) that sorts candidates for immediate context injection.
4. **HeavyRanker (Phase 3)**: A neural ranking model (**ButlerHIN**) that uses graph embeddings to optimize for deep personalization across long horizons.

#### 5.2.2 ButlerHIN (Heterogeneous Interaction Network)

- **Architecture**: A heterogeneous graph embedding model that learns unified vectors for different entity types.
- **Utility**: Resolves "Cold Start" problems for new topics/entities by leveraging existing relationships in the user's graph neighborhood.

### 5.3 Memory Consolidation & The Digital Twin

Memory must **Evolve**, not just **Accumulate**.

- **Consolidation Jobs**: Background tasks that distill episodic turns into permanent facts (written to Neo4j) and summaries (written to Qdrant).
- **Provenance**: Every fact in the Digital Twin must carry a link to its original source interaction.
- **Digital Twin Sync**: The system maintains a low-latency "Persona Profile" in Redis containing the user's most active preferences and constraints, ensuring 0-latency personality alignment.

---

## Chapter 6: The Action Plane & The 18 Services

The **Action Plane** is where Butler interacts with the world. It consists of 18 modular services, each with a strict domain contract and execution policy.

### 6.1 Identity & Control Services

#### 6.1.1 Auth Service

- **Ownership**: Identity lifecycle, session issuance, and device trust.
- **Security**: RS256/ES256 JWT, JWKS, Argon2id. No HS256 allowed.
- **Interface**: `AuthService.register()`, `AuthService.login()`, `AuthService.validate_session()`.

#### 6.1.2 Security Service

- **Ownership**: Global policy enforcement, capability gating, and redaction.
- **Policy Engine**: OPA-compatible rules evaluating `(Subject, Action, Resource)`.
- **Safety Kernel**: Redacts PII/Secrets in LLM contexts and log traces.
- **Approval Gateway**: Manages `ApprovalWait` states for high-risk actions.

#### 6.1.3 Gateway Service

- **Ownership**: Transport edge, normalization, and flow control.
- **Normalization**: Enforces the `ButlerEnvelope` standard on all incoming requests.
- **Idempotency**: Redis-backed cache ensuring every command executes exactly once.
- **Rate Limiting**: Token-bucket strategy per-user and per-IP.

### 6.2 Intelligence & Planning Services

#### 6.2.1 Orchestrator Service

- **Ownership**: Planning, coordination, and engine selection.
- **Engine Selection**: Routes requests between Macro (Deterministic), Routine (Recurring), and Durable (Coordinated).
- **Planning Logic**: Goal -> Task Graph (BWL) -> Execution.

#### 6.2.2 Memory Service

- **Ownership**: Episodic, Semantic, and Entity persistence.
- **Temporal Truth**: Manages `valid_from` and `observed_at` metadata for every knowledge node.
- **Retrieval Contract**: Provides `Memory.find_context()` across all 3 buckets.

#### 6.2.3 ML Service

- **Ownership**: Intelligence primitives and model routing.
- **Intent Classifier**: Maps user request to T0-T3 complexity tiers.
- **Embedding Worker**: Generates high-fidelity vectors for RAG and ranking.

#### 6.2.4 Search Service

- **Ownership**: Web research and evidence extraction.
- **Provider Adapters**: Google Search, Tavily, Crawl4AI, and direct HTTP fetch.
- **Evidence Bundles**: Returns structured data with hyperlinked citations.

### 6.3 Action & Interaction Services

#### 6.3.1 Tools Service

- **Ownership**: Tool registry and execution lifecycle.
- **Registry**: YAML-defined capability mappings for 100+ functions.
- **Sandbox**: Isolated Python/Subprocess runtimes for hazardous tool execution.

#### 6.3.2 Realtime Service

- **Ownership**: Connection management and live event delivery.
- **Streaming**: Native support for token-by-token reasoning streaming.
- **Presence**: Tracks active vs. background device status for smart notification routing.

#### 6.3.3 Communication Service

- **Ownership**: Multi-channel messaging (SMS, WA, Email, Push).
- **Policy Loop**: Respects user-defined "Quiet Hours" and "Urgency Tiers."
- **Verification**: Signs all outgoing messages with Butler's DKIM/Identity keys.

#### 6.3.4 Workflows Service

- **Ownership**: Durable state management and BWL execution.
- **State Machine**: pending -> running -> awaiting_approval -> completed -> failed.
- **Checkpointing**: Every state change is committed to Postgres as an `ExecutionEvent`.

### 6.4 Environment & Sensory Services

#### 6.4.1 Device Service

- **Ownership**: IOT mesh and device identity.
- **Adapters**: Home Assistant, Matter, HomeKit.
- **State Mirroring**: Maintains a real-time digital twin of the user's home/devices.

#### 6.4.2 Vision Service

- **Ownership**: Visual reasoning and object detection.
- **Grounding**: Grounding DINO + SAM 3 for pixel-perfect object identification.
- **OCR**: Extraction of high-fidelity text from screenshots and camera feeds.

#### 6.4.3 Audio Service

- **Ownership**: Real-time STT/TTS and diarization.
- **Wake Word**: Local-first processing of wake word triggers.
- **Emotional Tone**: TTS adapts tone based on session sentiment analysis.

#### 6.4.4 Automation Service

- **Ownership**: The "Context-Aware Cron" and trigger system.
- **Event Mesh**: Subscribes to device, calendar, and system events to fire routines.
- **Suppression**: Prevents agent "Spam" via confidence-based cooldowns.

#### 6.4.5 Plugins Service

- **Ownership**: Extension Registry (MCP, Wasm).
- **Validation**: Enforces signed manifests for all third-party code.
- **Isolation**: Runtime separation for non-native capability extensions.

### 6.5 Platform Services

#### 6.5.1 Data Service

- **Ownership**: PostgreSQL persistence and Alembic migrations.
- **Schema Control**: The single source of truth for the project's data definitions.

#### 6.5.2 Observability Service

- **Ownership**: OTel instrumentation (Traces, Metrics, Logs).
- **Dashboards**: Grafana metrics for service-mesh health and model performance.

---

## Chapter 7: The Capability Matrix & Tool Registry

The **Capability Matrix** is the fundamental security and modularity framework of the Butler ecosystem. It transforms a collection of 100+ disparate tools into a governed, tier-based execution grid.

### 7.1 The 18 Capability Areas

Every tool in Butler must belong to exactly one of the 18 Capability Areas. Each area defines its own **Trust Policy** and **Resource Quota**.

#### 7.1.1 Digital Research & Retrieval

1. **WEB_SEARCH**: Perplexity-style deep research, site-crawling (Crawl4AI), and page fetching.
   - *Key Tools*: `search_google`, `fetch_page_content`, `extract_citations`.
   - *Safety Class*: `low` (Context-only).

2. **SEARCH_ENGINE**: Management of internal knowledge bases and external search provider configurations.
   - *Key Tools*: `reindex_personal_data`, `configure_query_rewriter`.
   - *Safety Class*: `medium` (Admin-only).

#### 7.1.2 Communication & Messaging

3. **MESSAGING**: Execution of multi-channel outreach.
   - *Key Tools*: `send_sms`, `send_whatsapp`, `send_email`.
   - *Safety Class*: `medium` (Strict provenance required).

4. **SOCIAL_PRESENCE**: Context-aware social interactions.
   - *Key Tools*: `post_to_linkedin`, `monitor_x_mentions`.
   - *Safety Class*: `medium` (Approval gate recommended).

#### 7.1.3 Productivity & Organization

5. **CALENDAR_OPS**: Scheduling and availability resolution.
   - *Key Tools*: `create_event`, `find_meeting_slot`, `reschedule_conflicts`.
   - *Safety Class*: `low` (Read-only) / `medium` (Write).

6. **MEETING_ASSISTANT**: Contextual scribe and action-item tracking during live sessions.
   - *Key Tools*: `generate_minutes`, `extract_tasks`, `identify_speakers`.

#### 7.1.4 Data & Personalization

7. **MEMORY_OPS**: Explicit management of the Long-Term Memory (LTM).
   - *Key Tools*: `update_preference`, `correct_fact`, `delete_episodic_turn`.
   - *Safety Class*: `critical` (User-only).

8. **DATA_ANALYSIS**: Code-driven reasoning on structured datasets.
   - *Key Tools*: `execute_python_script`, `generate_chart`, `summarize_csv`.
   - *Safety Class*: `medium` (Isolated runtime).

#### 7.1.5 Environment & Sensory

9. **IOT_CONTROL**: Interaction with the physical world through smart home protocols.
   - *Key Tools*: `set_thermostat`, `unlock_door`, `toggle_lights_group`.
   - *Safety Class*: `high` (MFA/Policy gate).

10. **VISION_REASONING**: Analysis of visual inputs.
    - *Key Tools*: `detect_objects`, `describe_screenshot`, `extract_text_from_receipt`.

11. **AUDIO_FLOW**: Processing of speech and environmental sound.
    - *Key Tools*: `transcribe_stream`, `synthesize_emotional_voice`, `detect_wake_word`.

#### 7.1.6 Coordination & Extension

12. **DELEGATION**: The ability to spawn and manage child agents.
    - *Key Tools*: `spawn_researcher`, `wait_for_subagent`, `merge_subagent_output`.

13. **PLATFORM_PLUGINS**: Loading third-party capabilities via MCP or Wasm.
    - *Key Tools*: `install_mcp_server`, `validate_plugin_manifest`.

14. **SYSTEM_OPS**: Low-level Butler maintenance.
    - *Key Tools*: `fetch_system_health`, `run_database_cleanup`, `rotate_encryption_keys`.

#### 7.1.7 Specialty Domains

15. **FINANCE_GATEWAY**: Management of personal financial data and transitions.
    - *Key Tools*: `check_balance`, `list_transactions`, `predict_burn_rate`.

16. **HEALTH_INTEGRATION**: Interaction with Apple Health and wearable sensors.
    - *Key Tools*: `fetch_step_count`, `log_sleep_quality`, `summarize_recovery`.

17. **STREAMS_MGMT**: Control of live data feeds and event streams.

18. **GEN_AI_FACTORY**: Creation of synthetic assets (images, mockups, voice clones).

### 7.2 Tool Registration Standards

Butler enforces a formal registry for all tools, whether native, bridged (Hermes), or external (MCP).

#### 7.2.1 The Tool Manifest

Every tool must provide a JSON schema defining:

- `name`: Unique canonical identifier.
- `capability`: The associated area from the Matrix.
- `parameters`: Strictly typed Pydantic-compatible schemas.
- `risk_tier`: `low`, `medium`, `high`, or `critical`.
- `idempotent`: Boolean flag indicating execution safety for retries.
- `compensation`: The CLI command or logic required to "Undo" the action.

#### 7.2.2 The Global Capability Registry

The `CapabilityRegistry` (managed by the Tools Service) performs runtime validation. It rejects any execution request that:

1. Cannot be mapped to a known Capability area.
2. Violates the **Iron Law of Inheritance** (agent trying to use a tool higher than its parent's scope).
3. Lacks a valid `Idempotency-Key` for non-idempotent high-risk actions.

### 7.3 Safety Classes & Approval Flows

The **Safety Mesh** determines how a tool is executed based on its risk tier.

| Safety Class | Trigger | Orchestrator Action |
|--------------|---------|---------------------|
| **AUTO** | low risk | Immediate execution; background audit log. |
| **LOG_ONLY** | medium risk | Immediate execution; explicit "Scar Tissue" log for user review. |
| **ASK_USER** | high risk | Suspend execution; send `ApprovalRequest` to mobile widget. |
| **DUAL_AUTH** | critical risk| Suspend execution; require secondary device or biometric confirmation. |
| **DENY** | prohibited | Log violation; terminate workflow; flag session for review. |

---

## Chapter 8: Agentic Runtime & Subagent Isolation

The **Agentic Runtime** is the living core of Butler. It handles the "Thinking Loop" that drives autonomous action.

### 8.1 The Master Agent Loop (Observe-Think-Act)

The `AgentLoop` follows a structured recursive flow:

1. **Intake & Normalization**: Normalizes request via `ButlerEnvelope`.
2. **Context Retrieval**: Fetches 10-20 most relevant items from Episodic, Semantic, and Graph memory.
3. **Intent Classification (The T-Tier Model)**:
   - **T0 (Direct)**: "What is X?" -> Direct response.
   - **T1 (Routine)**: "Morning summary." -> Step-by-step assistant execution.
   - **T2 (Coordination)**: "Plan a trip." -> Multi-agent durable workflow spawning.
4. **Resolution (The Decision Tree)**:
   - Evaluates if all required parameters (slots) are present.
   - Checks `CapabilityGate` against current trust levels.
   - Selects the optimal Tool vs. Engine combination.
5. **Execution**:
   - Dispatches to `MacroRuntime`, `RoutineRuntime`, or `DurableExecutor`.
6. **Observation & Reflection**:
   - Analyzes tool output.
   - Updates the episodic memory branch.
   - Decides if the "Goal" is met or if a follow-up step is required.

### 8.2 Subagent Runtime Persistence

Butler manages complex problems by spawning **Subagents**. These are NOT just LLM recursive calls; they are separate **Isolation Units** in the persistent database.

#### 8.2.1 Subagent Metadata

A subagent record in Postgres includes:

- `parent_id`: Links to the spawning agent/workflow.
- `capability_mask`: A bitmask of inherited permissions (strictly ≤ parent).
- `trust_class`: 1-5 rating of the subagent's autonomy.
- `state_hash`: Current execution state for deterministic resume.

#### 8.2.2 The 5-class Isolation Matrix

Butler enforces runtime isolation based on the subagent's profile:

1. **TRUST_CLASS_1 (In-Process)**: Native code, shared memory. Low overhead.
2. **TRUST_CLASS_2 (Process-Pool)**: Isolated Unix processes; restricted IPC.
3. **TRUST_CLASS_3 (Sandbox)**: gVisor or Wasm containers; zero network access except via Gateway.
4. **TRUST_CLASS_4 (Remote Peer)**: Communication via encrypted ACP protocol; no shared state.
5. **TRUST_CLASS_5 (Human-Kernel)**: Hybrid human-in-the-loop task routing.

### 8.3 Deterministic Replay & Replay Safety

To achieve **Oracle-Grade** durability, Butler's L3 engine is **Replay Safe**.

#### 8.3.1 The Determinism Contract

- No shared global state.
- All non-deterministic inputs (Time, Randomness) are injected via the Kernel and recorded in the `ExecutionEvent` log.
- Every workflow must be structured such that `Replay(Log) == CurrentState`.

#### 8.3.2 The Replay Kernel Flow

1. **Load Log**: Fetch all previous `ExecutionEvent` records for the Task ID.
2. **DAG Walk**: Traverse the BWL nodes logically.
3. **History Match**: If a node ID matches a log entry, inject the saved `SuccessValue` and skip execution.
4. **Hot Swap**: If a node is missing from history, resume live execution at that branch.

---

## Chapter 9: The Ambient Edge (Physical & Mobile)

Butler's intelligence is designed to be **Ambient**, meaning it persists across devices and environments, crossing the threshold from digital screen-use to physical world-interaction.

### 9.1 The Edge Topology

Butler operates on a **Hydrated Edge** architecture. While the modular monolith resides in the cloud (or local server), the "Sense and Act" organs are distributed across the user's environment.

#### 9.1.1 Mobile Bridge (Expo/React Native)

The mobile companion is more than a UI; it is a **Sensor Hub**.

- **Biometric Proxy**: Handles AAL2/AAL3 step-up authentication via FaceID/TouchID.
- **Sensor Ingress**: Streams health data (Health Connect) and location telemetry to the `DeviceService`.
- **Offline Buffer**: Partially caches the Digital Twin and active L1 Macros for low-latency execution in flight mode.

#### 9.1.2 IoT Mesh (Matter & Home Assistant)

Butler integrates with the home via the **Matter** protocol and the **Home Assistant** API.

- **State Mirroring**: Every physical device (light, lock, thermostat) has a corresponding "Shadow Node" in Neo4j.
- **Intent -> IOT**: "Butler, secure the perimeter" -> Orchestrator Plan -> `iot.lock_doors`, `iot.arm_alarm`, `iot.exterior_lights_on`.

### 9.2 Perception Pipelines

#### 9.2.1 Vision (Grounding & Reasoning)

The Vision Service processes visual data for both interaction (screenshots) and security (camera feeds).

- **Object Grounding**: Uses **Grounding DINO** for semantic tagging and **SAM 3** for precise pixel masking.
- **Computer-Use**: Playwright-backed browser agents use Vision to "See" dynamic UI elements that lack semantic labels.

#### 9.2.2 Audio (STT/TTS Diarization)

- **Local STT**: **Faster-Whisper** provides low-latency, private transcription.
- **Conversational TTS**: **Coqui TTS** enables voice cloning (with consent) and emotional inflection matched to session sentiment.
- **Speaker ID**: Diarization ensures Butler distinguishes between the primary user and guests in a shared space.

### 9.3 Robotics (ROS 2 Integration)

In Phase 6, Butler gains a physical body via **ROS 2** (Robot Operating System).

- **Nav2 (Navigation)**: Butler manages path-planning for mobile agents (e.g., vacuum, telepresence bot).
- **MoveIt 2 (Manipulation)**: Orchestrator plans involving robot arms (e.g., "Help with laundry") use the BWL `Task` node to dispatch kinematic goals.

---

## Chapter 10: Security, Policy & Safety Kernel

Butler employs a **Defense-in-Depth** model specifically hardened for LLM-driven agentic systems.

### 10.1 Trust-Level Classification

The **Security Service** classifies every interaction into one of four Trust Levels:

1. **INTERNAL (Level 0)**: System heartbeats, routine reapers, and kernel-space migrations.
2. **VERIFIED_USER (Level 1)**: Direct commands with multi-factor passkey validation.
3. **PEER_AGENT (Level 2)**: Subagents or external Butler instances communicating via ACP.
4. **UNTRUSTED (Level 3)**: Content from web searches, untrusted MCP servers, or ambient triggers.

### 10.2 Content Defense Mesh

- **Prompt Injection Defense**: Every intake envelope passes through a "Canary Scanner" that detects jailbreak attempts and system-instruction overrides.
- **Reasoning Isolation**: "Thinking tokens" (reasoning) are strictly isolated from the final user-facing response buffer (redaction).
- **Sensitive Redaction**: A high-performance regex + ML scanner identifies PII, keys, and secrets in real-time, masking them before they reach the LLM or persistent logs.

### 10.3 The Policy Decision Point (PDP)

Butler uses a decoupled policy engine (OPA-compatible).

- **Policy Definition**: Written in C7-style YAML.
- **Dynamic Gating**: High-risk capabilities (e.g., `PAYMENT_EXECUTION`, `SECURITY_UNLOCK`) require a "Just-in-Time" approval signal from the user's primary device.

---

## Chapter 11: Operations, SRE & Observability

Butler is built for **Oracle-Grade** production reliability.

### 11.1 Observability Platform (OpenTelemetry)

Butler uses **OTel** to provide 360-degree visibility into the execution kernel.

- **Traces**: Every request generates a Trace ID that tracks the flow from Gateway -> Orchestrator -> Tool -> Memory.
- **Metrics**: High-cardinality metrics track LLM token cost, plan-success rates, and tool latencies.
- **Logs**: Structured JSON logging via `structlog` ensures every error links directly to a Trace ID.

### 11.2 Reliability Engineering

- **State Checkpointing**: The Data Service ensures that every task transition is atomic and multi-region safe (Postgres Partitioning).
- **Reaper Loops**: The Cron Service identifies "zombie" workflows (stuck in pending/running) and triggers automated recovery or human escalation.
- **Rollback & Compensation**: For every tool action, a `compensation_handler` must be defined to reverse side-effects in the event of workflow failure.

### 11.3 Deployment & CI/CD

- **Modular Monolith**: Butler deploys as a single containerized unit for simplicity, while maintaining internal service boundaries.
- **Alembic Migrations**: Strictly versioned database schemas with mandatory "Rollback Support."
- **Model A/B Testing**: The ML Service supports side-by-side intent classification testing to validate new models before promotion.

---

## Chapter 12: The Master Roadmap (2026-2027)

Butler's evolution from MVP to Ambient Intelligence follows a 6-phase build plan.

### 12.1 Phase 0: The Hardened Spine

- **Focus**: BWL v1.0, Durable Executor, Identity Platform, and Core Policy.
- **Goal**: 100% deterministic replay for L3 Workflows.

### 12.2 Phase 1: Tiered Intelligence

- **Focus**: Macro Engine, Routine Engine, and Intent Classification (T0-T3).
- **Goal**: Sub-100ms response for repeated user macros.

### 12.3 Phase 2: Service Grid Activation

- **Focus**: Audio, Vision (DINO/SAM), Search (Evidence), and Communication (WA/SMS).
- **Goal**: Butler becomes multi-channel and multi-sensory.

### 12.4 Phase 3: Capability Deep-Dives

- **Focus**: Finance (Plaid), Health (Connect), Travel (ONDC), and Commerce.
- **Goal**: Autonomous task completion in 18 functional domains.

### 12.5 Phase 4: Cognitive Personalization

- **Focus**: Digital Twin Sync, HeavyRanker (ButlerHIN), and Episodic Consolidation.
- **Goal**: Butler anticipates needs before the user asks.

### 12.6 Phase 5: Presence & Robotics

- **Focus**: ROS 2 Bridge, Nav2, Mobile Companion 2.0, and Wearable HUD.
- **Goal**: Butler is everywhere.

---

## Chapter 13: Implementation Roadmap (0 to 100%)

This chapter outlines the complete journey from the current architecture-grade codebase to a **100% operational Super-Agent** capable of handling complex, long-running, and high-stakes tasks across digital and physical environments.

### 13.1 Phase 0: Architectural Hardening (The Big Reset)

**Objective**: Build the "Oracle-Grade" spine for the entire system.

- [ ] **Butler Workflow Language (BWL) v1.0**
  - [ ] Finalize JSON/YAML schema for deterministic execution.
  - [ ] Implement `DurableExecutor` with deterministic replay.
  - [ ] Add append-only `WorkflowEvent` history in PostgreSQL.

- [ ] **Subagent Runtime Matrix**
  - [ ] Implement 5-class execution container: `IN_PROCESS`, `WORKER_POOL`, `SANDBOXED_SUBPROCESS`, `REMOTE_AGENT`, `HUMAN_GATE`.
  - [ ] Enforce **Iron Law of Inheritance**: Monotonic capability reduction.

- [ ] **Policy & Governance**
  - [ ] Centralize 18 `CapabilityFlag` gates.
  - [ ] Wire unified policy engine to all tool entrypoints.

### 13.2 Phase 1: Tiered Execution Intelligence

**Objective**: Launch the three execution layers (Macro, Routine, Durable).

- [ ] **L1: Macro Runtime**
  - [ ] Implement fast-planned template execution for repetitive tasks.
  - [ ] Build Slot-Resolution engine for immediate memory injection.

- [ ] **L2: Routine Runtime**
  - [ ] Implement contextual assistant triggers (Context-Aware Cron).
  - [ ] Add confidence decay and cooldown logic to prevent agent spam.

- [ ] **L3: Durable Workflow Engine**
  - [ ] Full support for `Parallel`, `Choice`, and `Wait` nodes in BWL.
  - [ ] Implement human-in-the-loop `Approval` gates.
  - [ ] Add `SignalWait` for asynchronous external triggers.

### 13.3 Phase 2: Service Grid Activation (The 18 Services)

**Objective**: Hardening and audit of the modular monolith.

| Service | Status | Priority | Goal |
|---------|--------|----------|------|
| **Vision** | ⚠️ Stub | High | Integrate Grounding DINO + SAM 3 for object grounding. |
| **Meetings** | ⚠️ Stub | High | Automated scribe, agenda matching, and action-item extraction. |
| **Calendar** | ✅ Good | Med | Full sync with Google/Outlook/iCal. |
| **Audio** | ✅ Good | Med | Regional dialect support and local-first diarization. |
| **Device** | ✅ Good | Med | Matter + Home Assistant native adaptation layer. |
| **Finance** | ⚠️ Delta | Med | Alpha Vantage + Plaid integration for watchlist management. |
| **Social** | ⚠️ Delta | Low | LinkedIn/X/Messenger channel adaptation. |

### 13.4 Phase 3: The 18 Capability Ecosystem

**Objective**: Full integration of "Skill Market" and external API lanes.

- [ ] **Commerce Lane**: Swiggy, Zomato, Uber, and ONDC integration.
- [ ] **Mobility Lane**: Maps, routing, and real-time transit status.
- [ ] **Productivity Lane**: Google Workspace, Slack, and Microsoft 365.
- [ ] **Development Lane**: MCP-powered local development tools (Compiler, Linter, Shell).

### 13.5 Phase 4: Personalization & Memory (Digital Twin)

**Objective**: Butler learns and anticipates.

- [ ] **Episodic Memory**: Graph-based memory of past interactions and preferences.
- [ ] **Contextual Twin**: Build a persona profile that mirrors user values/tone.
- [ ] **Feedback Loop**: Agent learns from "good bot" / "bad bot" signals to adjust routine triggers.

### 13.6 Phase 5: Physical Presence & Robotics

**Objective**: Butler crosses the digital/physical boundary.

- [ ] **Mobile Companion**: Full React Native (Expo) app with widget support and notifications.
- [ ] **Wearable Integration**: Health Connect, Apple Health, and smart-glasses (HUD).
- [ ] **Robotics Bridge**: ROS 2 bridge for navigation (Nav2) and manipulation (MoveIt 2).

### 13.7 Success Metrics (0 to 100%)

- **20% (Core)**: Deterministic BWL execution and unified policy gating.
- **40% (Active)**: Macro/Routine engines active; 10/18 services hardened.
- **60% (Productive)**: Durable workflows with human-in-the-loop support.
- **80% (Hyper-Local)**: Device/Home/Health integration functional.
- **100% (Ambient)**: Butler is a seamless, across-platform, personalized intelligence.

---

## Chapter 14: Butler Workflow Language (BWL) v1.0 Specification

Butler Workflow Language (BWL) is a declarative, versioned, and deterministic DSL designed for the Butler Super-Agent architecture. It provides the structured discipline of **Amazon States Language (ASL)** with the agent-native flexibility required for **Memory Binding**, **Subagent Spawning**, and **Capability Gating**.

### 14.1 Core Principles

- **Determinism First**: Every workflow node must be replayable from persisted state. All non-deterministic behavior (timestamps, randoms, external calls) must be recorded in the event log.
- **Durable Persistence**: PostgreSQL is the canonical source of truth for all state transitions, signals, and checkpoints.
- **Monotonic Capability Inheritance**: Subagents spawned within a workflow strictly inherit the parent's capability profile and can only be further restricted (never elevated).
- **Versioning**: All definitions carry a `dsl_version` and `workflow_version` to handle execution replay correctly across code updates.

### 14.2 Grammar & Schema

#### Top-Level Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `dsl_version` | `string` | Canonical BWL version (e.g., `butler.workflow/v1`). |
| `kind` | `string` | Always `workflow`. |
| `metadata` | `object` | Versioning, ownership, and replay mode. |
| `inputs` | `object` | Schema definition for required inputs. |
| `start_at` | `string` | ID of the entry-point node. |
| `nodes` | `array` | List of execution nodes. |
| `timeouts` | `object` | Global timeout policies. |
| `retry_policy` | `object` | Global backoff/retry strategy. |

### 14.3 Node Library

#### A. Control Flow (ASL-style)

- **Task**: Executes a deterministic tool or function.
- **Choice**: Conditional branching with `when/else` logic.
- **Parallel**: Concurrent execution branches with `join` semantics (all/any/quorum).
- **Wait**: Suspends execution until a duration or absolute timestamp.
- **Success/Fail**: Terminal states.

#### B. Butler-Native (Agentic)

- **Subagent**: Spawns an isolated subagent with an inherited trust profile.
- **Approval**: Human-in-the-loop gate (via ACP/Mobile).
- **SignalWait**: Pause until a durable signal matches in the `WorkflowSignal` table.
- **MemoryBind**: Scope-restricted access to Butler's Long-Term Memory (LTM).
- **CapabilityGate**: Enforce safety zones (e.g., `FINANCE`, `SENSITIVE_DATA`) before proceeding.
- **PolicyCheck**: Dynamic governance validation (LLM-based or rule-based).
- **HumanInput**: Request a specific value/string from the user.
- **EmitEvent**: Publish a custom signal for other workflows or external systems.
- **Compensation**: Explicit rollback step triggered on failure.

### 14.4 Runtime Contracts

#### Rule 1: Replay Safety

Workflow handlers must not perform side effects directly. All world mutations must be:

1. Defined as a `Task` node.
2. Wrapped in an **Idempotency Check**.
3. Recorded in the `WorkflowEvent` history.

#### Rule 2: Signal Durability

Signals are hot-delivered via **Redis Streams** but must be persisted to **PostgreSQL** (`WorkflowSignal`) before they can cause a workflow to resume. This ensures that a post-crash recovery can reliably find all delivered signals.

#### Rule 3: Memory Scoping

The `MemoryBind` node must explicitly declare its access scope:

```yaml
type: MemoryBind
scope: "session"
include_sensitive: false
redaction_policy: "strict"
```

#### Rule 4: Parallel Join Semantics

Parallel nodes must specify a failure mode:

- `fail_fast`: Kill all branches if one fails.
- `isolate`: Continue other branches, ignore the failure.
- `compensate`: Trigger compensation nodes for all successful branches on any failure.

### 14.5 Persistence Model

- **WorkflowEvent History**: Append-only log of every node transition.
- **State Snapshot**: Current un-collapsed state of the execution frontier.
- **Checkpoints**: Atomic records of the DAG state between node boundaries.

### 14.6 Example: Multi-Agent Trip Planner

```yaml
dsl_version: "butler.workflow/v1"
kind: workflow
metadata:
  name: "secure_booking"
  version: "1.2.1"
  replay_mode: "deterministic"

inputs:
  user_email: { type: string, required: true }

start_at: "verify_tier"

nodes:
  - id: "verify_tier"
    type: "CapabilityGate"
    requires: ["TRAVEL_BOOKING"]
    next: "get_options"

  - id: "get_options"
    type: "Parallel"
    branches:
      - start_at: "search_flights"
      - start_at: "search_hotels"
    join: "all"
    next: "present_to_user"

  - id: "search_flights"
    type: "Task"
    tool: "travel.skyscanner"
    idempotency_key_template: "{{workflow.id}}:flights"

  - id: "present_to_user"
    type: "HumanInput"
    prompt: "Which option do you prefer?"
    next: "book_it"

  - id: "book_it"
    type: "Subagent"
    runtime_class: "SANDBOXED_SUBPROCESS"
    capabilities: ["PAYMENT_EXECUTION"]
    compensation: "void_transaction"
    next: "done"

  - id: "done"
    type: "Success"
```

---

## Success Metrics (The Oracle Standard)

- **Reliability**: 99.9% L3 task completion (resumed success).
- **Latency**: P95 < 1.5s for T1 Routine tasks.
- **Intelligence**: 95% Intent Classification accuracy.
- **Privacy**: 0 PII leaks recorded in external traces.

---

*This document is the definitive technical archive for the Butler project. Any significant architectural deviation must be recorded in the Architecture Decision Log (ADL) and reviewed against the Platform Constitution.*

*Last Updated: 2026-04-20*

**[END OF THE MASTER ARCHIVE]**