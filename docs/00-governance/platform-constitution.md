# Butler Platform Constitution
> **For:** All Engineering, Product, Design  
> **Status:** Authoritative  
> **Version:** 2.1  
> **Reference:** Cross-service governance - the one document that binds all Butler services
---
## Metadata
- **Owner:** Architecture Team
- **Depends On:** None
- **Supersedes:** v2.0
- **Source of Truth Rank:** 1
---
## v2.1 Changes
- Clarified modular monolith dependency law
- Added engineering constitution alignment
- Strengthened enforcement and ownership rules
- Added runtime authority principles
- Added explicit anti-pattern prohibitions
- Tightened cross-service interaction rules
- Normalized authoritative terminology for safety, durability, and policy
---
# 1. Platform Definition
## 1.1 What Butler Is
**Butler is a durable, memory-driven, policy-governed personal AI runtime across devices, channels, and environments.**
Butler is **not**:
- a chatbot wrapper
- a tool execution engine
- a smart home app
- an ML microservice zoo
- a random agent experiment wearing enterprise clothes
It is a governed execution system that:
- understands user context
- preserves useful memory with bounded retention
- makes policy-aware decisions
- executes actions through explicit control paths
- learns from outcomes without bypassing trust, safety, or human control
## 1.2 Platform Mission
Butler exists to:
1. **Observe** and understand user context across devices, channels, and environments
2. **Remember** relationships, preferences, routines, and relevant history
3. **Decide** what actions serve the user's goals
4. **Act** across tools, devices, and integrations
5. **Learn** from outcomes to improve over time
## 1.3 Platform Non-Negotiables
Butler must always remain:
- **durable before clever**
- **policy-governed before autonomous**
- **memory-disciplined before memory-maximal**
- **human-trust-preserving before feature-rich**
- **explicitly controlled before magically inferred**
Any implementation that violates these principles is out of constitution, even if it technically works.
---
# 2. Architecture Model
## 2.1 Full-Product Modular Monolith
Butler uses **one deployable backend** with real service boundaries inside the codebase.
```text
backend/
├── app/
│   ├── main.py
│   ├── lifespan.py
│   ├── core/                    # Config, security, telemetry
│   ├── api/routers/             # Route modules
│   ├── services/                # Application services
│   ├── domain/                  # Business contracts and rules
│   ├── infrastructure/          # Storage and external adapters
│   └── tests/
├── alembic/
├── docker-compose.yml
└── pyproject.toml

2.2 Modular Monolith Definition

A modular monolith means:

* one deployable process boundary
* many internal service boundaries
* explicit contracts between modules
* no cross-layer bypassing for convenience
* internal decoupling strong enough that later extraction is possible if justified

It does not mean fake microservices inside one repo.
It means disciplined package boundaries inside one production runtime.

2.3 Dependency Law

Allowed dependency direction:

api -> services -> domain
infrastructure -> domain
main/lifespan -> api + services + infrastructure for assembly only

Forbidden dependency patterns

Pattern	Status
api → infrastructure	FORBIDDEN
api → domain bypassing services	FORBIDDEN
service A → service B internals	FORBIDDEN
infrastructure → api	FORBIDDEN
domain → api	FORBIDDEN
domain → framework runtime objects	FORBIDDEN
domain → infrastructure SDKs directly	FORBIDDEN

Clarification

The phrase “never skip layers” means do not bypass the intended responsibility chain for business behavior.
Infrastructure may implement domain contracts, but business flow must still remain service-mediated.

⸻

3. Service Catalog (18 Canonical Services)

3.1 Identity & Control

Service	Owns	Key Capabilities
Auth	Identity, sessions, tokens	Passkeys, MFA, device trust, linked identities
Security	Policy, authorization, AI gating	Crypto, approval rules, redaction, threat detection
Gateway	Transport, normalization	TLS termination, rate limiting, idempotency, protocol adapters

3.2 Intelligence Core

Service	Owns	Key Capabilities
Orchestrator	Planning, coordination	Intent understanding, structured planning, durable execution
Memory	Context, history	Session history, preferences, episodic + semantic memory
ML	Embeddings, models	Intent classification, reranking, candidate retrieval
Search	Evidence, citations	Web search, crawler orchestration, citation bundles

3.3 Action & Interaction

Service	Owns	Key Capabilities
Tools	Tool registry, execution	Schema validation, policy-gated execution, verification
Realtime	Streaming, events	WebSocket/SSE, token streaming, notifications
Communication	Messages, delivery	SMS, WhatsApp, email, push, delivery tracking
Workflows	Durable workflows	State machines, resumable execution, checkpoints

3.4 Environment & Extension

Service	Owns	Key Capabilities
Device	Device identity, control	Mobile/desktop/IoT, sensors, cross-device state
Vision	Visual understanding	OCR, object detection, screen parsing, UI elements
Audio	Voice processing	STT, TTS, wake word, speaker ID, streaming
Automation	Trigger/action rules	Event-driven automation, scheduled routines
Plugins	Extension registry	MCP/WASM/remote adapters, signed manifests

3.5 Platform Services

Service	Owns	Key Capabilities
Data	PostgreSQL persistence	Users, sessions, workflow state, audit
Observability	Telemetry	Metrics, traces, logs, alerts

⸻

4. Runtime Planes

┌─────────────────────────────────────────────────────────────┐
│                 EXPERIENCE PLANE                            │
│  API Routes | Realtime Streams | Mobile/Web/Desktop        │
├─────────────────────────────────────────────────────────────┤
│                  CONTROL PLANE                              │
│  Auth | Security | Policy | Approvals | Plugin Exposure    │
├─────────────────────────────────────────────────────────────┤
│                 INTELLIGENCE PLANE                          │
│  Orchestrator | ML | Memory | Search | Planning            │
├─────────────────────────────────────────────────────────────┤
│                    ACTION PLANE                             │
│  Tools | Communication | Device | Automation | Workflows   │
├─────────────────────────────────────────────────────────────┤
│                     DATA PLANE                              │
│  PostgreSQL | Redis | Neo4j | Qdrant | S3                  │
└─────────────────────────────────────────────────────────────┘

4.1 Plane Rule

A higher plane may coordinate with a lower plane only through lawful contracts.
A lower plane must never silently assume authority that belongs to a higher plane.

Examples:

* Tools do not decide policy
* ML does not trigger real-world actions
* Gateway does not invent business behavior
* Data plane does not define product semantics

⸻

5. Build Priority

Phase 1: Foundation (Week 1-2)

* Core: config, lifespan, security primitives, observability hooks

Phase 2: Identity & Control (Week 2-3)

* Auth → Security → Data → Gateway

Phase 3: Intelligence Core (Week 3-5)

* Memory → Tools → Orchestrator → ML

Phase 4: Interaction (Week 5-7)

* Realtime → Communication → Search → Workflows

Phase 5: Environment (Week 7-9)

* Device → Vision → Audio → Automation

Phase 6: Extension (Week 9-10)

* Plugins → Hermes adapters → MCP loaders

5.1 Vertical Slice Rule

Even though all 18 services are canonical, implementation priority is governed by the first real executable loop:

request intake → auth validation → orchestration → memory lookup → tool execution → response → memory update

A service is not “strategically important” if it delays proving the loop.

⸻

6. Service Ownership Boundaries

6.1 Canonical Rules

Rule	Service	Owns	Does NOT Own
Identity	Auth	User credentials, sessions, device trust	Policy enforcement
Policy	Security	Policy definitions, risk signals	Credential management
Transport	Gateway	HTTP ingress, protocol edge	Business logic
Execution	Orchestrator	Planning, task coordination	Credential validation
Memory	Memory	Long-term memory, entity graph	ML model training
Intelligence	ML	Embeddings, rankers, predictors	Storage backend
Realtime	Realtime	Connection lifecycle, event delivery	Credential issuing
Devices	Device	Device control, state, health ingress	User identity

6.2 Cross-Service Principles

1. Gateway NEVER calls Memory directly. Always through Orchestrator.
2. Auth owns identity; Security owns enforcement. Never merge them casually.
3. Memory stores; ML generates embeddings. Retrieval-first contract.
4. Orchestrator decides; Tools execute. Execution authority is explicit.
5. Realtime delivers; Orchestrator publishes. Delivery is not decision-making.
6. Communication delivers messages; Security classifies message risk.
7. Workflows persist execution state; Orchestrator owns decision progression.
8. Plugins expose capabilities; Security and Tools govern whether they may run.

6.3 Ownership Rule

If two services appear to own the same behavior, the design is wrong until ownership is redefined.

Shared ownership is usually just ambiguity wearing collaborative language.

⸻

7. Core Definitions

7.1 Durable

Definition: Work must survive restarts, approval pauses, and delayed dependencies. Execution resumes from a committed boundary, not from vibes.

Implications:

* all task state in PostgreSQL as source of truth
* Redis is hot-path cache and transport assist, not truth store
* event trail for replayability and debugging
* compensation or idempotency for side effects
* checkpoints for workflow continuation

7.2 Safe / Safety Class

Definition: Every action has a policy class determining approval requirements.

Class	Approval Required	Examples
low	No	search, get_memory, time
medium	No, but logged	send_message, create_event
high	Yes	payment, device_control
critical	Yes + dual control	admin_action, lock_unlock

7.3 Memory

Definition: Memory is a system capability, not an excuse to store everything forever. Memory must evolve, not merely accumulate.

Implications:

* temporal truth model
* episodic memory windows
* preference and aversion representation
* provenance on every write
* freshness scoring
* bounded raw retention
* deletion and minimization policies

7.4 Approval

Definition: A gating mechanism that pauses execution pending human decision.

Type	Trigger	Escalation
none	low risk	none
implicit	medium risk	logged for review
explicit	high risk	user notification
critical	critical risk	dual authorization

7.5 Session

Definition: A bounded conversation or execution context tied to identity, device, and channel.

Session Properties:

* account_id
* device_id
* channel
* assurance_level
* active_workflow

7.6 Policy-Governed

Definition: No meaningful external action may occur unless it passes through an explicit policy path.

That includes:

* tool execution
* communications
* device control
* workflow continuation under restricted conditions
* plugin invocation where risk classification applies

⸻

8. Design Rules

8.1 Fundamental Principles

#	Rule	Rationale
1	Retrieve first, reason second	Performance + cost control
2	Durable before clever	Production survival
3	Every side effect replay-safe or compensatable	Reliability
4	Every sensitive action has a policy class	Security enforcement
5	Memory evolves, not only accumulates	Cost + privacy
6	Realtime supports reconnect and replay	UX reliability
7	Every user-visible answer has provenance	Trust
8	Every service emits typed events	Debugging
9	Personal data defaults to least retention	Privacy
10	Low-end mode behavior is designed	Resilience
11	No silent autonomy escalation	Human trust
12	Frameworks stay at the edges	Maintainability

8.2 Architecture Rules

1. No HS256 in production. Use RS256/ES256 with JWKS.
2. No password hashing except Argon2id.
3. Redis Pub/Sub is not durable. Use Streams for durable delivery.
4. No hardcoded embedding models. Use versioned contracts.
5. No silent action-driving from ML. Predictions inform Orchestrator only.
6. No raw code upload execution. Prefer MCP-first, manifest-driven, policy-gated extensions.
7. Health is not one endpoint. Four-state model required.
8. SLO-based alerting, not threshold theater.
9. No business logic in transport adapters.
10. No framework imports inside domain packages.
11. No module-level mutable state for auth, session, or workflow coordination.
12. No direct service-internal coupling that bypasses contracts.

8.3 Engineering Rules

All Butler implementation must align with the engineering constitution:

* PEP 8 / PEP 257 disciplined Python
* strongly typed public interfaces
* explicit boundaries
* SOLID without abstraction theater
* OOP for stateful domain behavior
* FP for deterministic transformations
* replay-safe side effects
* observability as part of done
* security as part of runtime, not polish

⸻

9. Cross-Service Contracts

9.1 Event Contract

Every event must include:

{
  "event_id": "evt_...",
  "type": "...",
  "timestamp": "...",
  "session_id": "...",
  "account_id": "...",
  "durable": true,
  "payload": {}
}

9.2 Request Envelope

Every request must include:

{
  "request_id": "req_...",
  "trace_id": "trc_...",
  "channel": "mobile|web|watch|voice",
  "device": "device_id",
  "actor": { "type": "user|assistant|tool", "id": "..." },
  "timestamp": "...",
  "idempotency_key": "..."
}

9.3 Health Model (Four-State)

/health/startup   -> STARTING / HEALTHY
/health/ready     -> HEALTHY / DEGRADED / UNHEALTHY
/health/live      -> HEALTHY / UNHEALTHY
/health/degraded  -> status details

9.4 Error Contract

All service error responses must align with RFC 9457 Problem Details.

No custom “success/error envelope” format should replace the standard error model.

⸻

10. Security and Rights

10.1 Assurance Levels

Level	Auth Required	Actions
AAL1	Basic authenticated session	Basic queries
AAL2	Passkey or MFA	Tool execution
AAL3	Step-up auth	Restricted actions

10.2 Data Rights

* Minimization: collect the least data needed
* Retention: explicit TTL per data class
* Ambient recording: opt-in only, user toggle, retention-limited
* Health data: tightly consented, explicit use only
* Deletion: supported according to data class and legal constraints
* Auditability: high-risk actions must remain traceable

10.3 Security Baseline

All services must align with platform security standards, including:

* TLS 1.3
* mTLS where required for internal trust boundaries
* strong key hierarchy and envelope encryption
* Argon2id for passwords
* signed tokens with asymmetric validation
* prompt injection and unsafe tool use defenses
* redaction and least-necessary logging

⸻

11. Enforcement

Every service document must:

1. reference this Constitution for key definitions
2. document how it handles each applicable Design Rule
3. define its safety classes
4. implement the four-state health model
5. emit typed events per Event Contract
6. define replay and compensation behavior
7. state its dependencies and forbidden couplings
8. define observability expectations

11.1 Review Enforcement

Violations must be caught in:

* code review
* architecture review
* service design review
* security review
* operational readiness review

11.2 Violation Rule

If code violates the Constitution, one of two things must happen:

1. the code changes, or
2. the Constitution is formally amended

Unwritten exceptions are not real exceptions.

⸻

12. Forbidden Platform Patterns

The following are constitutionally forbidden:

* gateway directly calling memory
* auth and security collapsing into one informal blob
* ML directly triggering real-world side effects
* route handlers containing business orchestration
* service modules reaching into other service internals
* global mutable state for sessions, auth, or execution control
* fake encryption, placeholder security, or dummy approval logic in production paths
* undocumented cross-service coupling
* replay-unsafe external side effects without compensation or idempotency
* memory retention without explicit policy basis

⸻

13. Final Authority Clause

This Constitution is the highest operational authority for Butler platform behavior.

When lower-level documents conflict with this document, this document wins unless explicitly superseded by a newer constitutional version.

If implementation drifts from this document, the implementation is out of governance compliance until corrected.
