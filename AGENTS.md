# Butler AI - Agent Knowledge Base
> **For:** Future OpenCode sessions
> **Version:** 3.2 (Oracle-Grade v2.1)
> **Updated:** 2026-04-22

---

## ⚠️ IMPORTANT: Read These Before Any Task

**This is the next phase architecture. All other docs/ references are deprecated.**

**Read these documents in order before starting any work:**

1. **[premble.md](premble.md)** - BIS v2 Complete Technical Architecture: Birth to Death, 0 → 100%
   - PART 0: What This System Is
   - PART 1: The Absolute Domain Law
   - PART 2: System Architecture Overview
   - PART 3-16: All domains, encryption, storage, build sequence, and privacy principles

2. **[bis-v2-production-architecture-dfe18c.md](bis-v2-production-architecture-dfe18c.md)** - Production Implementation Specification
   - Architectural Corrections (critical context)
   - 7-Plane Architecture
   - Encryption Layer (E2E Data Privacy)
   - Control Plane, Context System, Tool System
   - Deliberation Engine, Council Engine, Domain Crews
   - Knowledge System, Memory System, Multi-Tenant Architecture
   - Reliability Layer, Model System, User Mode System
   - Implementation Phases (18 phases)

**These documents replace all previous docs/ references.**

---

## What This Project Is
**Butler** = Personal AI system (not a chatbot wrapper):
- Modular AI execution with **18 services**
- Crosses digital (API/email/search) + physical (IoT devices) environments
- Production target: 1M users, 10K RPS, P95 <1.5s
- Three execution layers: Macro / Routine / Durable Workflow
---
## Project Structure
```text
Butler/
├── app/              # React Native (Expo) mobile app
├── backend/          # FastAPI modular monolith
│   ├── api/          # HTTP routes + schemas
│   ├── domain/       # Auth, orchestrator, memory, tools...
│   ├── services/     # 16 service implementations
│   ├── core/         # Config, security, logging, deps
│   └── tests/
├── docs/             # Documentation (v3.2)
├── docker-compose.yml
└── test-mvp.sh

⸻

Commands

Start System

docker-compose up -d
curl http://localhost:8000/health

Test MVP

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "test123"}'
# Chat
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "hello", "session_id": "test"}'

Backend Dev

cd backend
source .venv/bin/activate
pip install -r requirements.txt
pytest
ruff check .

Mobile App

cd app
npx expo start -- --tunnel

⸻

Documentation

Start here for ANY work in docs/:

* docs/index.md￼ - AI-optimized navigation for docs/
* docs/AGENTS.md￼ - Implementation defaults
* docs/README.md￼ - System overview

Docs follow v2.1 Oracle-grade patterns:

* Four-state health: STARTING → HEALTHY → DEGRADED → UNHEALTHY
* JWT with JWKS (RS256, RFC 9068) - never HS256
* RFC 9457 error format (Problem Details)
* MCP-first plugins
* No VACUUM FULL (use autovacuum)

⸻

System Design Rules

Reference: docs/rules/SYSTEM_RULES.md￼ - v2.1 Oracle-Grade

Key v2.1 updates:

* RFC 9457 Problem Details (not custom envelopes)
* No universal success envelopes
* Split health probes (/health/live, /health/ready, /health/startup)
* JWT: RS256/ES256 with JWKS, NO HS256, validate issuer/audience
* Password hashing: Argon2id (OWASP minimum)
* OpenTelemetry semantic conventions for tracing

⸻

Critical Service Boundaries

Rule	Why
Gateway NEVER calls Memory directly	Always via Orchestrator
Auth + Security stay separate	Defense in depth
Memory uses ML for embeddings, not vice versa	Clean dependency
Routes inject domain services	Testability
Domain must NOT import FastAPI	Boundary enforcement

⸻

Backend Architecture (from backend/AGENTS.md)

backend/
├── api/routes/       # HTTP only - NO business logic
├── api/schemas/      # Request/response DTOs
├── domain/*/         # Business rules + contracts
├── infrastructure/   # Redis, Postgres, external providers
├── services/*/       # Application orchestration
└── main.py           # App assembly ONLY

⸻

Key Files for Context

Need	File
Service specs	docs/services/{service}.md
Runbooks	docs/runbooks/
Security	docs/security/SECURITY.md
Dev setup	docs/dev/SETUP.md
Build sequence	docs/dev/build-order.md

⸻

Do NOT Do

* No business logic in route files
* No fake encryption in security service
* No hardcoded secrets in service modules
* No module-level mutable state for auth/session
* No service coupling through route imports

⸻

First Production Slice (per backend/AGENTS.md)

1. auth login + JWT (RS256)
2. authenticated chat entrypoint
3. session history persistence
4. one real starter tool
5. orchestrator uses memory + tools through interfaces

⸻

External Technology Research

Reference: .ref/EXTERNAL_TECH.md - Research on external libraries

Technology	License	Butler Fit	Status
pyturboquant	MIT	RECOMMENDED	Direct integration
TriAttention	Apache-2.0	RECOMMENDED	Direct integration
twitter/the-algorithm	AGPL-3.0	Design only	Legal review needed
twitter/the-algorithm-ml	AGPL-3.0	Design only	Legal review needed
twitter-server	Apache-2.0	Patterns	Service templates

Adoption Roadmap

Phase 1 (Immediate):

* Add TurboQuantMemoryBackend to Memory service (compressed recall tier)
* Add TriAttention vLLM provider to ML Runtime

Phase 2 (Near-term):

* Candidate retrieval layer
* User signal store
* Lightweight ranker

Phase 3 (Future):

* Heavy ranker
* ButlerHIN embeddings
* Action Mixer layer

⸻

Butler Engineering Constitution

This section is the default engineering law for all future Butler code.
Not optional. Not “best effort.” Not something to ignore because a deadline hurt your feelings.

1. Prime Directive

Every code change must be:

* correct before clever
* readable before compressed
* explicit before magical
* testable before extensible
* maintainable before impressive
* performant where it matters
* production-safe by default

If another senior engineer cannot understand a module in one pass, the work is not finished.

⸻

2. Core Python Standards

2.1 Style

* Follow PEP 8 consistently
* Use PEP 257 docstrings for public modules, classes, and functions
* Prefer line lengths in the 88-100 char range
* Use parentheses for line wrapping, not backslashes
* Keep one statement per line
* No wildcard imports

2.2 Naming

* variables/functions/modules: snake_case
* classes/exceptions: CapWords
* constants: UPPER_SNAKE_CASE
* internal/protected members: _leading_underscore

2.3 Explicitness

* Avoid hidden mutation
* Avoid hidden side effects
* Avoid “smart” helpers that do multiple unrelated things
* Avoid ambiguous booleans in APIs where an enum, config object, or separate method is clearer

2.4 Imports

Import order must always be:

1. standard library
2. third-party packages
3. local Butler modules

Prefer module-level imports over symbol soup unless direct import meaningfully improves clarity.

⸻

3. Butler Python Design Rules

3.1 Domain First

* Business logic belongs in domain/
* Application orchestration belongs in services/
* External integrations belong in infrastructure/
* HTTP, websocket, and schema concerns belong in api/
* main.py is assembly only

3.2 Frameworks Stay at the Edge

* Domain code must not depend on FastAPI
* Domain code must not depend on ORM models directly
* Domain code must not depend on Redis/Postgres clients directly
* All infrastructure must enter through explicit interfaces or contracts

3.3 Dependency Direction

Allowed direction:

api -> services -> domain
infrastructure -> domain
main -> all for assembly

Forbidden direction:

domain -> api
domain -> FastAPI
domain -> route handlers
services -> route imports

3.4 Abstractions Must Earn Their Existence

Do not introduce:

* wrapper classes with no behavior
* giant “manager” classes
* generic utils.py dumping grounds
* inheritance hierarchies without real substitutability
* decorators or metaprogramming that obscure flow

If abstraction does not reduce complexity, remove it.

⸻

4. OOP and FP Usage Rules

4.1 Use OOP when:

* state and lifecycle matter
* domain invariants must be protected
* a service owns meaningful collaboration and internal policy
* you are modeling durable concepts like sessions, memories, auth principals, workflow executions, policy evaluators

4.2 Use FP when:

* transforming data
* validating DTOs
* normalizing payloads
* computing derived values
* building deterministic pipelines
* doing ranking, filtering, scoring, formatting, parsing

4.3 Composition Over Inheritance

Default to composition.
Use inheritance only when:

* relationship is truly is-a
* subtype fully honors parent contract
* replacement is behaviorally safe

4.4 Stateful Code Must Be Deliberate

* mutable state must have a clear owner
* cross-request shared mutable state is forbidden unless explicitly designed
* module-level mutable state is forbidden for sessions, auth, caches, workflow context

⸻

5. Function Rules

5.1 Functions Must Be Sharp

A function should do one thing well.

5.2 Signatures Must Be Clear

* avoid *args and **kwargs unless truly necessary
* avoid more than 4-5 parameters when a typed config/value object is clearer
* prefer explicit named parameters for non-obvious arguments

5.3 Return Values Must Be Coherent

Prefer:

* one meaningful value
* a dataclass
* a typed result object

Avoid mystery tuples and raw dict contracts for core flows.

5.4 Side Effects Must Be Visible

Any function that writes to DB, sends messages, calls tools, or mutates state must make that obvious by name and placement.

⸻

6. Class Rules

6.1 Classes Must Model Real Responsibilities

Do not create classes just to group functions.

6.2 Constructors Must Be Lightweight

__init__ should establish valid state, not do network I/O or expensive orchestration.

6.3 Invariants Must Be Enforced

Objects should be hard to construct in an invalid state.

6.4 Prefer Dataclasses for Structured Data

Use @dataclass for:

* DTOs
* command/query payloads
* config objects
* value objects
* immutable domain records where appropriate

Use frozen=True when immutability improves safety.

⸻

7. Complexity and Data Structure Rules

7.1 Use the Right Data Structure

* dict for keyed access
* set for membership/uniqueness
* list for ordered sequences
* deque for queues
* heapq for priority work
* iterators/generators for streaming pipelines

7.2 Complexity Awareness Is Mandatory

Engineers must know the rough time and space cost of hot paths.
No accidental O(n²) loops in orchestration, ranking, memory retrieval, or event processing.

7.3 Optimize Only Where It Matters

* measure before micro-optimizing
* optimize critical paths aggressively once proven
* prefer simpler code for cold paths

7.4 Avoid Unnecessary Copies

Large memory snapshots, embeddings, transcripts, and tool payloads should be streamed or chunked where possible.

⸻

8. Typing Rules

8.1 Public Code Must Be Typed

All public functions, methods, and interfaces require type hints.

8.2 Types Are Design Contracts

Do not sprinkle types like decorative parsley. Use them to define stable interfaces.

8.3 Prefer Protocols for Behavior

Use Protocol where Butler needs swappable backends:

* memory backends
* tool providers
* auth resolvers
* ranking engines
* storage providers

8.4 Avoid Any

Use Any only when unavoidable at integration boundaries and narrow it quickly.

8.5 Avoid Raw Dict Soup

If a payload shape matters, model it with:

* dataclasses
* typed dicts where justified
* pydantic DTOs at API boundaries

⸻

9. Error Handling Rules

9.1 Errors Must Never Disappear

Do not swallow exceptions.
Do not use broad except Exception: unless:

* you log context
* you re-raise or map to a known domain/system error
* you are at a boundary layer

9.2 Validate at Trust Boundaries

Validate:

* request bodies
* auth claims
* config
* external provider responses
* file inputs
* tool outputs
* DB-to-domain translations

9.3 Domain Errors and Infra Errors Must Be Distinct

Examples:

* invalid session state -> domain error
* Redis timeout -> infrastructure error
* malformed JWT -> auth/security error
* provider 500 -> integration error

9.4 Preserve Error Context

Use exception chaining when wrapping lower-level failures:

raise MemoryWriteError("Failed to persist memory item") from err

9.5 API Errors Must Use RFC 9457

No custom error envelopes for convenience theater.

⸻

10. Testing Rules

10.1 Test Real Behavior

Tests must verify contracts and outcomes, not internal trivia.

10.2 Every Bug Fix Needs a Regression Test

If production suffered once, the test suite should remember.

10.3 Test Pyramid for Butler

* unit tests for domain logic
* integration tests for DB/Redis/provider boundaries
* API tests for transport contracts
* workflow tests for orchestrator paths

10.4 No Fake Comfort Tests

Tests that merely assert 200 OK without meaningful behavior validation are noise.

10.5 Determinism Required

No flaky timing-based nonsense.
Stabilize time, IDs, randomness, and environment-dependent behavior.

⸻

11. Production Engineering Rules

11.1 Observability Is Part of Done

Every critical flow must expose:

* structured logs
* tracing spans
* metrics
* request/correlation IDs where relevant

11.2 Security Is Default

* no hardcoded secrets
* no insecure crypto shortcuts
* no plaintext credential logging
* least privilege for providers and tokens
* strict JWT validation
* Argon2id for passwords
* sanitize logs and traces

11.3 Config Must Be Centralized

Use typed configuration objects.
Do not scatter os.getenv() across the codebase like confetti.

11.4 Reliability Matters More Than Elegance

Critical workflows must consider:

* retries
* timeouts
* idempotency
* partial failure
* compensating behavior
* degraded mode

11.5 Async Must Be Used Correctly

* use async for I/O concurrency, not vanity
* do not block event loops
* isolate slow external calls
* control fan-out and cancellation behavior

⸻

12. Butler-Specific Non-Negotiables

12.1 Route Layer

* route files are transport only
* no orchestration logic in handlers
* no direct persistence in handlers
* schemas define boundary contracts, not business rules

12.2 Service Layer

* coordinates use cases
* calls domain contracts
* handles transaction/application flow
* does not become a god layer dumping ground

12.3 Domain Layer

* owns core rules and invariants
* framework-agnostic
* testable without web server or DB boot
* no FastAPI imports
* no direct infra clients

12.4 Infrastructure Layer

* adapts external systems to Butler contracts
* contains provider-specific quirks
* never leaks external SDK weirdness deep into the domain

12.5 Orchestrator

* is the only lawful coordinator between memory, tools, workflows, and execution policy
* gateway never bypasses it to call memory directly
* all continuation, approval, and workflow progression must respect this boundary

⸻

13. Forbidden Patterns

Never introduce:

* business logic in route handlers
* service coupling through imports across transport boundaries
* generic utils.py landfills
* hidden global registries unless explicitly designed and documented
* module-level mutable auth/session state
* fake encryption or fake security placeholders
* hardcoded provider credentials
* “temporary” hacks without TODO owner and removal intent
* giant classes that validate, fetch, mutate, log, serialize, and retry all at once

⸻

14. Definition of Done for Butler Code

A change is only done when it is:

* correct
* typed
* readable
* PEP 8 compliant
* boundary-safe
* failure-aware
* test-backed
* observable
* security-conscious
* easy to change later

If it merely works on your laptop, congratulations, you have achieved the lowest form of software existence.

⸻

15. Code Review Standard

Every PR or generated patch must be judged by these questions:

1. Is the business logic in the correct layer?
2. Are dependencies flowing in the correct direction?
3. Is the abstraction earned or decorative?
4. Are names specific and honest?
5. Is the function/class doing one job?
6. Is state ownership clear?
7. Are failure modes explicit?
8. Is type information strong enough?
9. Will this survive production load and future edits?
10. Would a serious staff engineer sign off without embarrassment?

If the answer to the last question is no, keep working.

⸻

16. Default Build Quality for All Future OpenCode Sessions

When modifying Butler, always produce code that is:

* production-grade
* senior-level
* strongly typed
* modular
* explicit
* low-magic
* boundary-clean
* SOLID without overengineering
* Pythonic without cleverness theater

Target standard:
“A real SWE-5 / Staff-level engineer wrote this for a long-lived production system.”

⸻

When in doubt: read docs/index.md first. When coding: obey this constitution first.
