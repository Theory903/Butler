# Butler Documentation Index
> **AI-optimized navigation**
> **Status:** Authoritative
> **Version:** 4.2
> **Updated:** 2026-04-22
---
## Metadata
- **Owner:** Architecture Team
- **Depends On:** `00-governance/platform-constitution.md`
- **Supersedes:** Version 4.1 and prior hub/index variants
- **Source of Truth Rank:** 0 (navigation + document precedence only)
---
## Purpose
This document is the authoritative navigation hub for Butler documentation.
It exists to:
- direct humans and AI agents to the correct starting point
- define documentation precedence and reading order
- summarize system structure, current implementation status, and critical constraints
- prevent random wandering through the docs like a lost intern with production access
This document does **not** redefine detailed product, architecture, or service behavior.  
It points to the documents that do.
---
# 1. For AI Agents - Start Here
If you are an AI working on Butler, read these **in order**:
## 1.1 First Read
1. [00-governance/platform-constitution.md](./00-governance/platform-constitution.md)
2. [00-governance/system-design-rules.md](./00-governance/system-design-rules.md)
3. [01-core/HLD.md](./01-core/HLD.md)
4. Relevant `02-services/{service}.md`
5. Relevant operational or reference docs if needed
## 1.2 Entry Points by Goal
| Your Goal | Start Here |
|----------|------------|
| Understand Butler | [00-governance/platform-constitution.md](./00-governance/platform-constitution.md) |
| Validate system rules | [00-governance/system-design-rules.md](./00-governance/system-design-rules.md) |
| Build features | [01-core/HLD.md](./01-core/HLD.md) |
| Implement a service | [02-services/](./02-services/) + relevant core docs |
| Fix bugs / investigate issues | [04-operations/runbooks/index.md](./04-operations/runbooks/index.md) |
| Deploy / infra work | [04-operations/deployment/DEPLOYMENT.md](./04-operations/deployment/DEPLOYMENT.md) |
| Security work | [04-operations/security/SECURITY.md](./04-operations/security/SECURITY.md) |
| Local development | [05-development/SETUP.md](./05-development/SETUP.md) |
---
# 2. What Butler Is
Butler is a **personal AI execution system**, not a chatbot wrapper.
It combines:
- personal assistance
- workflow automation
- memory-driven context
- multimodal input
- tool execution
- digital system interaction
- physical environment interaction
It is designed for:
- **1M users**
- **10K RPS**
- **P95 latency under 1.5s**
- clear service boundaries
- security-first defaults
- durable execution
- production-grade operability
### Execution Layers
| Layer | Doc | Purpose |
|-------|-----|---------|
| Macro | [03-reference/workflows/macro-engine.md](./03-reference/workflows/macro-engine.md) | Fast repeated actions |
| Routine | [03-reference/workflows/routine-engine.md](./03-reference/workflows/routine-engine.md) | Contextual behavior |
| Durable Workflow | [03-reference/workflows/durable-workflow-engine.md](./03-reference/workflows/durable-workflow-engine.md) | Long-running tasks |
---
# 3. Core Design Model
Every meaningful Butler feature should map to one or more of these foundations:
| Question | System Area | What it determines |
|----------|-------------|--------------------|
| **WHO?** | Identity | User, device, auth principal |
| **WHERE / WHEN / WHAT around?** | Context | Location, environment, timing, surrounding state |
| **WHAT is wanted?** | Intent | Command, request, question, workflow |
| **HOW should Butler respond?** | Action / Response | Tool execution, speech, notification, UI, workflow step |
Related references:
- `perfect-design.md`
- `client-server-split.md`
---
# 4. Documentation Tree
```text
docs/
├── 00-governance/            # Constitution, rules, models, precedence
│   ├── platform-constitution.md
│   ├── system-design-rules.md
│   ├── object-model.md
│   ├── event-contract.md
│   ├── request-envelope.md
│   ├── glossary.md
│   └── doc-precedence.md
│
├── 01-core/                  # BRD → PRD → TRD → HLD → LLD
│   ├── BRD.md
│   ├── PRD.md
│   ├── TRD.md
│   ├── HLD.md
│   ├── LLD.md
│   └── teams.md
│
├── 02-services/              # 18 service specifications
│   ├── gateway.md
│   ├── auth.md
│   ├── orchestrator.md
│   ├── memory.md
│   ├── ml.md
│   ├── realtime.md
│   ├── search.md
│   ├── tools.md
│   ├── communication.md
│   ├── data.md
│   ├── security.md
│   ├── observability.md
│   ├── device.md
│   ├── vision.md
│   ├── audio.md
│   ├── automation.md
│   ├── workflows.md
│   └── plugins.md
│
├── 03-reference/             # APIs, runtime, workflows, plugins, system refs
│   ├── api/
│   │   ├── public-api.md
│   │   └── problem-types.md
│   ├── workflows/
│   │   ├── macro-engine.md
│   │   ├── routine-engine.md
│   │   └── durable-workflow-engine.md
│   ├── plugins/
│   │   └── plugin-system.md
│   ├── runtime/
│   │   └── health-model.md
│   └── system/
│       ├── first-flow.md
│       └── reference-harvest-map.md
│
├── 04-operations/            # Production ops
│   ├── deployment/
│   │   └── DEPLOYMENT.md
│   ├── security/
│   │   ├── SECURITY.md
│   │   ├── SECURITY_BASELINE.md
│   │   ├── AI_SECURITY.md
│   │   ├── CRYPTOGRAPHY.md
│   │   └── DATA_CLASSIFICATION.md
│   ├── runbooks/
│   │   ├── index.md
│   │   ├── service-down.md
│   │   ├── high-latency.md
│   │   └── database-failure.md
│   └── testing/
│       └── TESTING.md
│
└── 05-development/           # Development setup and sequencing
    ├── SETUP.md
    ├── build-order.md
    └── run-local.md

⸻

5. Documentation Reading Paths

5.1 Product and System Understanding

Read in order:

1. 00-governance/platform-constitution.md
2. 00-governance/system-design-rules.md
3. 01-core/BRD.md
4. 01-core/PRD.md
5. 01-core/TRD.md
6. 01-core/HLD.md
7. 01-core/LLD.md

5.2 Building the First Working System

Read:

1. 05-development/build-order.md
2. 03-reference/system/first-flow.md
3. 02-services/gateway.md
4. 02-services/auth.md
5. 02-services/orchestrator.md
6. 02-services/memory.md
7. 02-services/tools.md

5.3 Implementing or Modifying a Service

Read:

1. relevant 02-services/{service}.md
2. 01-core/TRD.md
3. 01-core/HLD.md
4. 01-core/LLD.md
5. related security and runbook docs

5.4 Incident Investigation / Bug Fixing

Read:

1. 04-operations/runbooks/index.md
2. relevant service spec
3. relevant runtime/reference docs
4. observability/security docs if needed

⸻

6. Source of Truth Rules

When documents conflict, resolve in this order:

1. 00-governance/platform-constitution.md
2. 00-governance/system-design-rules.md
3. 00-governance/object-model.md
4. 00-governance/event-contract.md
5. 01-core/BRD.md
6. 01-core/PRD.md
7. 01-core/TRD.md
8. 01-core/HLD.md
9. 01-core/LLD.md
10. 02-services/*.md
11. 03-reference/*.md
12. 04-operations/*.md
13. Code

Code is not the source of truth when it conflicts with higher-order architecture or product intent unless the docs have been explicitly updated.

⸻

7. Knowledge Graph

                    ┌──────────────────────┐
                    │ Platform Constitution│
                    └──────────┬───────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ↓                    ↓                    ↓
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ System Design   │  │   Object Model  │  │  Event Contract │
│ Rules           │  │                 │  │                 │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                    │
         └────────┬───────────┼───────────┬────────┘
                  ↓           ↓           ↓
           ┌─────────────────────────────────────┐
           │        Core Docs (BRD → LLD)        │
           └──────────────┬──────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ↓                 ↓                 ↓
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Services   │  │  Reference   │  │  Operations  │
│   (18 docs)  │  │   (API/WF)   │  │  (Runbooks)  │
└──────────────┘  └──────────────┘  └──────────────┘

⸻

8. Critical Production Patterns

All major docs and implementations must align with these patterns:

Pattern	Description	Where
Four-state health	STARTING → HEALTHY → DEGRADED → UNHEALTHY	Governance + runtime
RFC 9457 errors	Problem Details error format	All services
RFC 9068 / JWKS	RS256/ES256 JWTs, never HS256	Auth
Argon2id	Password hashing baseline	Security
Redis Streams	Durable async event transport	System design
OpenTelemetry	Semantic tracing and metrics	Observability
Strict service boundaries	Gateway never calls Memory directly	Constitution

⸻

9. Agentic Runtime Guidelines

These rules are mandatory for any agentic execution, orchestration, workflow, or prompt assembly logic.

9.1 Deterministic Prompt Assembly

* Use deterministic ordering for tool registries, payloads, and context blocks
* Keep static prompt segments stable
* Append dynamic state below stable prefixes
* Do not rewrite historical prompt bytes unless invalidation is intentional

9.2 Context and Session Isolation

* Every run must be isolated by account_id and session_id
* No cross-session contamination
* No module-level mutable auth/session state
* Every recall/write path must verify identity context

9.3 Stable Tool Ordering

* Tool ordering must remain stable throughout a run
* Mid-run reshuffling is forbidden unless explicitly versioned and controlled

9.4 Watcher and Approval Interception

* High-risk actions must pass through policy gating
* L2+ risk actions must support suspension for human approval
* Durable executors must preserve approval checkpoints

9.5 Durable Workflow Hygiene

* Workflow nodes must be replay-safe and idempotent
* Pure state transitions must be separated from effectful activities
* Resume from last checkpoint, never from reconstructed guesswork

⸻

10. Engineering Constitution Summary

All code and documentation must align with Butler’s engineering constitution:

* PEP 8 and PEP 257 compliant
* typed public APIs
* domain logic separated from framework/infrastructure details
* SOLID applied without abstraction theater
* OOP for stateful domain behavior
* FP for deterministic transformations
* no business logic in route handlers
* no hidden mutable globals
* no fake security
* no unclear ownership of side effects
* no god classes, god services, or landfill utils.py

This index is not the full lawbook. The full rules belong in the engineering constitution / AGENTS docs.

⸻

11. 18 Services Quick Reference

#	Service	Port	Status	Key Constraint
1	Gateway	8000	✅ Active	Never calls Memory directly
2	Auth	8001	✅ Active	Identity only
3	Security	8015	✅ Active	Enforcement + PII + safety
4	Orchestrator	8002	✅ Active	Decision hub + guardrails
5	Memory	8003	✅ Active	Store/retrieve + FAISS cold tier
6	ML	8006	✅ Active	Embeddings + smart routing
7	Realtime	8004	✅ Active	WebSocket / SSE
8	Search	8012	✅ Active	RAG + deep research
9	Tools	8005	✅ Active	Tool execution
10	Communication	8013	⚪ Partial	Notifications
11	Data	8014	✅ Active	Postgres
12	Observability	8016	⚪ Partial	Logs / metrics / tracing
13	Device	8017	🟡 Partial	IoT + environment sensing
14	Vision	8018	🔲 Stub	Screen and visual pipeline
15	Audio	8019	🟡 Partial	STT / TTS + fallback
16	Automation	8020	🔲 Planned	Macros
17	Workflows	8021	🔲 Planned	Durable orchestration
18	Plugins	8022	🔲 Planned	Extensions

⸻

12. v3.1 Implementation Status Snapshot

Service	Status	What Changed
Search	✅ Active	Real providers + DeepResearchEngine
Security	✅ Active	RedactionService + ContentGuard
Orchestrator	✅ Active	Guardrails + ambient context integrated
Memory	✅ Active	FaissColdStore + cold store factory
ML	✅ Active	Smart router dependency wiring fixed
Audio	🟡 Partial	Three-tier fallback; diarization pending
Device	🟡 Partial	EnvironmentService implemented
Gateway	✅ Active	Hermes stream bridge operational
Auth	✅ Active	RS256 JWT + JWKS, Argon2id, WebAuthn
Tools	✅ Active	ToolExecutor + ToolVerifier
Realtime	✅ Active	WebSocket/SSE transport
Communication	⚪ Partial	Email/push structure present
Observability	⚪ Partial	OTEL export configured
Vision	🔲 Stub	Screen capture pipeline pending
Data	✅ Active	Postgres operational

⸻

13. Common Tasks

Task	Doc
Set up local dev	05-development/SETUP.md￼
Build in the right order	05-development/build-order.md￼
Run the system locally	05-development/run-local.md￼
Add a plugin	03-reference/plugins/plugin-system.md￼
Investigate service down	04-operations/runbooks/service-down.md￼
Investigate DB failure	04-operations/runbooks/database-failure.md￼
Investigate latency	04-operations/runbooks/high-latency.md￼

⸻

14. Reference Systems

Reference	Purpose	Doc
Reference Harvest	Capability map from external systems	03-reference/system/reference-harvest-map.md￼
First Flow	End-to-end runtime behavior	03-reference/system/first-flow.md￼

⸻

15. Protocol Standards

Protocol	Standard	Implementation
HTTP/1.1	RFC 9110	Gateway REST API
HTTP/2	RFC 9113	High-performance clients
HTTP/3	RFC 9114	Edge ingress only
WebSocket	RFC 6455	Realtime transport
SSE	HTML Standard	One-way streaming
JWT	RFC 9068	RS256 / ES256 + JWKS
Errors	RFC 9457	Problem Details
TLS	1.3	All transport
Passwords	Argon2id	OWASP-aligned baseline
MCP	Target compatibility	Tool context protocol
ACP / A2A	Butler internal control envelope	Agent control plane

⸻

16. Error Response Standard

All services must use RFC 9457 Problem Details:

{
  "type": "https://docs.butler.lasmoid.ai/problems/{error-type}",
  "title": "Error Title",
  "status": 400,
  "detail": "Human-readable description",
  "instance": "/api/v1/endpoint#req_xxx"
}

Standard problem types include:

* invalid-request
* authentication-failed
* authorization-failed
* not-found
* rate-limit-exceeded
* internal-error
* bad-gateway
* service-unavailable
* gateway-timeout

⸻

17. Metadata Required in Every Doc

Every major document must include:

## Metadata
- Version: <semver>
- Status: authoritative | draft | deprecated
- Owner: <team>
- Last Updated: YYYY-MM-DD
- Depends On:
- Supersedes:
- Source of Truth Rank:

A document without metadata is incomplete. Humans will still write it anyway, naturally, but it is still incomplete.

⸻

18. Documentation Quality Rules

A document is only useful if it clearly answers:

* what this component does
* what it does not do
* what it depends on
* what depends on it
* how it fails
* how it is secured
* how it is measured
* how it scales
* how it is tested

Good docs reduce interpretation.
Bad docs create architecture by accident.

⸻

19. Current Maturity and Next Objective

Butler is no longer in ideation stage.

It now has:

* system definition
* documented architecture
* service boundaries
* implementation sequencing
* security baseline
* runtime design direction

The next meaningful milestone is:

Build and validate the first working vertical slice.

Minimum service path:

* Gateway
* Auth
* Orchestrator
* Memory
* Tools

First real loop:
request intake → auth validation → orchestration → context retrieval → tool execution → response → memory update

When this loop works with observability and recoverable failure behavior, Butler moves from planned to proven.

⸻

20. Version History

Version	Date	Changes
4.2	2026-04-22	Merged index + hub, removed duplication, aligned precedence and navigation
4.1	2026-04-19	v3.1 feature docs and service status updates
4.0	2026-04-18	Production-grade rewrite, 18 services, governance docs
3.2	2026-04-20	Agentic hardening guidance added
3.1	2026-04-18	Durable runtime and boundary clarifications
3.0	2026-04-17	Production-ready status
2.0	2026-04-16	Implementation-ready
1.0	2026-04-15	Initial draft
