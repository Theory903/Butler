# Butler Alpha Backend MVP - 2 Day Work Plan

## TL;DR

> **Quick Summary**: Finish the Butler alpha backend in 2 days by locking to the 5-service MVP from docs, keeping a single FastAPI modular monolith, and driving all work through test-first subagent execution on one golden path: login -> chat -> session history.
>
> **Deliverables**:
> - docs-backed MVP contract and backend architecture locked
> - bootable backend runtime with health checks and docker wiring
> - production-shaped Auth, Gateway, Orchestrator, Memory, Tools path
> - executable automated tests and curl smoke script for alpha launch
>
> **Estimated Effort**: Medium
> **Parallel Execution**: YES - 4 waves
> **Critical Path**: contract lock -> runtime wiring -> auth -> memory -> tools -> orchestrator -> gateway -> final verification

---

## Context

### Original Request
Create a perfect plan to proceed using `/Users/abhishekjha/CODE/Butler/docs`, using Ralph loop and subagents, and complete the MVP in 2 days as alpha backend only.

### Interview Summary
**Key Discussions**:
- The target is **alpha backend only**, not full product completion.
- MVP should come from docs, not from current partial backend boilerplate.
- The safest implementation shape is a **modular monolith** with strict service boundaries preserved for later extraction.
- Hermes Agent is an approved MIT-licensed reference project and may be copied from directly where that improves Butler's MVP implementation quality without expanding scope.

**Research Findings**:
- `docs/product/mvp-services.md` defines the MVP as **5 services only**: Gateway, Auth, Orchestrator, Memory, Tools.
- `docs/dev/build-order.md` and `docs/system/first-flow.md` define the fastest first working loop.
- Current backend already contains a starter foundation, but docs must win when contracts differ.
- Hermes reference patterns worth adapting: centralized config loading and permissioning in `hermes_cli/config.py`, idempotent structured logging in `hermes_logging.py`, non-fatal provider orchestration in `agent/memory_manager.py`, runtime-health surfacing in `tests/hermes_cli/test_gateway_runtime_health.py`, and tool-gateway resolution seams in `tools/managed_tool_gateway.py`.
- Hermes issue review adds explicit Butler guardrails: never persist resolved secrets back to config, avoid single-slot pending-message state, fail startup loudly with exact reason, keep runtime health human-readable, and prevent silent message-drop paths.

### Metis Review
**Identified Gaps** (addressed):
- Need explicit acceptance criteria for alpha launch -> added executable acceptance and QA scenarios.
- Need scope lock to avoid service explosion -> plan limits production-grade work to MVP 5 services.
- Need disclosed assumptions -> included below under guardrails/defaults.

---

## Work Objectives

### Core Objective
Ship a docs-conformant alpha backend that boots reliably, passes automated tests, and satisfies the documented MVP flow for login, chat, and session history within 2 days.

### Concrete Deliverables
- `docs/AGENTS.md` and backend knowledge base aligned as source of truth
- `backend/` modular-monolith architecture aligned to MVP docs
- working `/api/v1/auth/login`, `/api/v1/chat`, `/api/v1/session/{id}`
- one real starter tool path in Tools service
- Docker/runtime path for alpha backend launch
- automated tests + alpha smoke script

### Definition of Done
- [ ] `pytest backend/tests/test_mvp_flow.py -q` passes
- [ ] `python -m compileall backend` succeeds
- [ ] `docker-compose up -d db cache api` boots alpha backend stack
- [ ] documented curl flow in `docs/dev/run-first-system.md` works against backend contract

### Must Have
- Docs precedence honored over conflicting code
- Thin routes + DI + service/domain separation
- No duplicate auth implementations
- No fake crypto in security-sensitive code paths
- No in-memory auth/session persistence for the alpha golden path

### Must NOT Have (Guardrails)
- No expansion to full 16/17-service production behavior in this sprint
- No frontend scope in this plan
- No new optional libraries unless they remove blockers
- No route/business-logic mixing
- No direct Gateway -> Memory coupling
- No config rewrite path that persists runtime-expanded secrets or merged defaults back to disk
- No single-slot pending message state that can overwrite earlier in-flight requests
- No silent startup failures, silent tool failures, or silent message drops in the alpha golden path

### Hermes-Derived Implementation Guidance

- **Copy/adapt allowed** from `/Users/abhishekjha/CODE/Butler/.ref/hermes-agent` where useful because Hermes is MIT-licensed.
- Best direct-copy candidates for implementation tasks:
  - `hermes_logging.py` patterns for idempotent centralized logging, rotating handlers, and correlation/session context
  - `tools/managed_tool_gateway.py` helper structure for explicit env/config resolution and token freshness checks
  - `tests/hermes_cli/test_config_env_expansion.py` style tests for env placeholder handling and unresolved-placeholder preservation
- Best adapt-only patterns:
  - `agent/memory_manager.py` provider orchestration and non-fatal provider isolation (adapt to Butler service seams, do not copy the whole memory stack)
  - `gateway/config.py` typed config normalization/null-guard behavior (adapt to Butler settings and request contracts)
- Avoid copying Hermes features that exceed Butler MVP scope: messaging platform adapters, multi-platform gateway behavior, full provider matrix, cron/session reset platform logic, profile management, skin/CLI systems.

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** - all verification is agent-executed.

### Test Decision
- **Infrastructure exists**: YES
- **Automated tests**: YES (TDD / tests-first for remaining work)
- **Framework**: pytest
- **Agent-Executed QA**: REQUIRED for every task

### QA Policy
- API verification: Bash + curl
- Runtime verification: Bash + docker-compose / python entrypoint
- Backend unit/integration verification: pytest
- Evidence paths: `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`

---

## Execution Strategy

### Parallel Execution Waves

```text
Wave 1 (Contract + runtime lock)
├── Task 1: Lock MVP source-of-truth references and acceptance matrix
├── Task 2: Normalize backend package layout and dependency wiring
├── Task 3: Fix docker/runtime assets for backend-only alpha launch
└── Task 4: Add/normalize service health and smoke endpoints

Wave 2 (Core MVP service hardening)
├── Task 5: Finish Auth contract and persistence
├── Task 6: Finish Memory/session history contract
├── Task 7: Finish Tools starter tool contract
└── Task 8: Finish Orchestrator golden-path coordination

Wave 3 (Gateway + integration)
├── Task 9: Finish Gateway contract alignment and request flow
├── Task 10: Wire security/dependencies/config for alpha launch
├── Task 11: Add alpha smoke script + docker-compose verification
└── Task 12: Add placeholder-only secondary service registry sanity checks

Wave FINAL (Parallel review wave)
├── F1: Plan compliance audit
├── F2: Code quality + diagnostics review
├── F3: Real API QA against golden flow
└── F4: Scope fidelity check
```

### Ralph Loop Guidance

- Use Ralph loop only at the **orchestration level**, not as permission to expand scope.
- Each loop iteration must terminate on a verifiable checkpoint: failing test -> passing test -> reviewed diff.
- Ralph loop should stop immediately on contract mismatch, failing diagnostics, or unmet acceptance criteria.
- Never let Ralph loop invent work outside the MVP 5-service alpha boundary.

### Subagent Strategy

- `quick`: package cleanup, health endpoints, smoke scripts, docs alignment
- `deep`: auth, memory, orchestrator, gateway integration
- `unspecified-high`: runtime wiring, docker, diagnostics cleanup
- `oracle`: final plan compliance review

### Hermes Risk Register (apply during execution)

- **Config corruption / secret leakage**: Hermes issue patterns show the danger of saving runtime-expanded config; Butler must keep raw env placeholders/raw config separate from resolved runtime settings.
- **Gateway startup ambiguity**: Hermes runtime-health issues show startup can fail without a clear surface; Butler must expose exact startup failure reason in logs and health output.
- **Message loss under load**: Hermes pending-message overwrite issues show queue semantics matter; Butler must preserve ordered processing per session and never overwrite earlier pending work.
- **Observability duplication**: Hermes logging history shows setup must be idempotent; Butler must initialize logging once and include correlation/request IDs.
- **Managed tool seam drift**: Hermes tool-gateway helpers show environment resolution can silently drift; Butler tool execution/config resolution must be explicit and test-backed.

---

## TODOs

- [ ] 1. Lock alpha MVP acceptance matrix

  **What to do**:
  - Create a single acceptance matrix mapping docs contracts to backend endpoints for login, chat, and session history.
  - Normalize expected request/response shapes against `docs/product/mvp-services.md`, `docs/system/first-flow.md`, and `docs/dev/run-first-system.md`.
  - Record explicit alpha exclusions so subagents do not expand into post-MVP services.
  - Add a Hermes-derived risk checklist covering config rewrite, startup failure surfacing, message ordering, and silent-drop prevention.

  **Must NOT do**:
  - Do not redefine MVP beyond 5 services.
  - Do not invent contracts not backed by docs.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: docs alignment and acceptance matrix are high-value, low-code tasks.
  - **Skills**: [`writing-plans`]
    - `writing-plans`: keeps execution atomic and explicit.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: 5, 6, 7, 8, 9
  - **Blocked By**: None

  **References**:
  - `docs/AGENTS.md` - source-of-truth ordering and implementation defaults
  - `docs/product/mvp-services.md` - MVP scope, endpoints, infra expectations
  - `docs/system/first-flow.md` - golden path and session-history behavior
  - `docs/dev/run-first-system.md` - executable curl contract for alpha launch
  - `/Users/abhishekjha/CODE/Butler/.ref/hermes-agent/tests/hermes_cli/test_gateway_runtime_health.py` - concrete example of surfacing fatal startup reason in a compact health/readiness-oriented format
  - `/Users/abhishekjha/CODE/Butler/.ref/hermes-agent/tests/hermes_cli/test_config_env_expansion.py` - concrete example of guarding config/env expansion behavior with focused tests

  **Acceptance Criteria**:
  - [ ] one written acceptance matrix exists in project docs or plan adjunct notes
  - [ ] login/chat/history contract is unambiguous
  - [ ] explicit alpha exclusions listed
  - [ ] Hermes-derived failure modes are translated into Butler-specific guardrails

  **QA Scenarios**:
  ```
  Scenario: acceptance matrix matches docs
    Tool: Bash (grep/read)
    Preconditions: docs present locally
    Steps:
      1. Read `docs/product/mvp-services.md`, `docs/system/first-flow.md`, `docs/dev/run-first-system.md`
      2. Compare endpoint/method/payload/response expectations
      3. Assert the matrix contains `/api/v1/auth/login`, `/api/v1/chat`, `/api/v1/session/{id}`
    Expected Result: one consistent alpha contract exists
    Evidence: .sisyphus/evidence/task-1-acceptance-matrix.txt
  ```

- [ ] 2. Normalize backend package and dependency wiring

  **What to do**:
  - Finish package-level `__init__.py` and import layout so the backend is analyzable and runnable.
  - Keep routes thin and inject auth/memory/tools/orchestrator via dependency providers.
  - Ensure backend package structure matches `backend/AGENTS.md` direction even if domain/infrastructure split is staged.

  **Must NOT do**:
  - Do not reintroduce duplicate auth paths.
  - Do not let route files own business logic.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: structural cleanup and import normalization.
  - **Skills**: [`test-driven-development`]
    - `test-driven-development`: locks behavior while cleaning structure.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: 5, 6, 7, 8, 9, 10
  - **Blocked By**: 1

  **References**:
  - `backend/AGENTS.md` - target package rules and dependency direction
  - `backend/main.py` - current assembly point
  - `backend/core/dependencies.py` - service injection pattern

  **Acceptance Criteria**:
  - [ ] backend packages import cleanly at runtime
  - [ ] no duplicate auth route/service behavior remains
  - [ ] dependency wiring is explicit

  **QA Scenarios**:
  ```
  Scenario: package imports resolve at runtime
    Tool: Bash
    Preconditions: backend venv installed
    Steps:
      1. Run `python -c "import backend.main; print('ok')"` from repo root
      2. Run `python -m compileall backend`
    Expected Result: import succeeds and compileall completes
    Evidence: .sisyphus/evidence/task-2-imports.txt
  ```

- [ ] 3. Fix backend-only alpha runtime assets

  **What to do**:
  - Make Docker/runtime match alpha backend only.
  - Ensure backend launch path is clear even if frontend/app service exists in repo.
  - Add missing backend Dockerfile/entrypoint/runtime notes if absent.
  - Add startup-failure surfacing so broken env/config/runtime issues fail loudly with actionable logs.

  **Must NOT do**:
  - Do not force frontend into the alpha backend critical path.
  - Do not introduce extra infrastructure beyond MVP needs.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: runtime wiring is cross-cutting and easy to break.
  - **Skills**: [`careful`]
    - `careful`: runtime config changes can create hidden launch failures.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: 11, F3
  - **Blocked By**: 1

  **References**:
  - `docker-compose.yml` - current runtime topology
  - `docs/dev/run-first-system.md` - expected alpha run path
  - `docs/product/mvp-services.md` - MVP infra requirements
  - `/Users/abhishekjha/CODE/Butler/.ref/hermes-agent/hermes_cli/config.py` - concrete examples of secure file/directory handling, canonical config-path ownership, and managed/runtime separation
  - `/Users/abhishekjha/CODE/Butler/.ref/hermes-agent/tests/hermes_cli/test_gateway_runtime_health.py` - concrete example of preserving last startup issue in runtime status output

  **Acceptance Criteria**:
  - [ ] backend launch instructions are executable
  - [ ] db/cache/api stack can boot without frontend dependency
  - [ ] runtime docs match actual launch method
  - [ ] startup failure path emits explicit reason instead of generic/non-diagnostic failure

  **QA Scenarios**:
  ```
  Scenario: backend-only docker stack boots
    Tool: Bash
    Preconditions: Docker available
    Steps:
      1. Run `docker-compose up -d db cache api`
      2. Run `docker-compose ps`
      3. Assert api, db, cache are Up
    Expected Result: alpha backend stack starts cleanly
    Evidence: .sisyphus/evidence/task-3-docker.txt
  ```

- [ ] 4. Add health and smoke verification endpoints

  **What to do**:
  - Ensure health checks exist for backend app and key service namespaces used in alpha.
  - Keep them lightweight and deterministic.
  - Add one smoke endpoint or scriptable route inventory if needed for launch checks.
  - Include degraded/failure detail sufficient to debug startup/runtime issues without inspecting source code.

  **Must NOT do**:
  - Do not expose fake operational guarantees.
  - Do not turn health checks into business logic tests.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: narrow surface area, easy verification.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: 11, F3
  - **Blocked By**: 2, 3

  **References**:
  - `docs/dev/run-first-system.md` - expected health-check behavior
  - `backend/main.py` - route assembly
  - `/Users/abhishekjha/CODE/Butler/.ref/hermes-agent/tests/hermes_cli/test_gateway_runtime_health.py` - reference for including fatal platform/startup reason in operator-facing runtime health output

  **Acceptance Criteria**:
  - [ ] `/health` responds 200
  - [ ] route inventory or smoke path is scriptable
  - [ ] readiness/health output includes actionable startup failure detail when unhealthy

  **QA Scenarios**:
  ```
  Scenario: health endpoint works
    Tool: Bash (curl)
    Preconditions: backend running on localhost:8000
    Steps:
      1. Run `curl http://localhost:8000/health`
      2. Assert status 200 and JSON contains `status`
    Expected Result: health returns stable response
    Evidence: .sisyphus/evidence/task-4-health.txt
  ```

- [ ] 5. Finish Auth alpha contract

  **What to do**:
  - Make `/api/v1/auth/login` match docs exactly for JSON email/password login.
  - Use PostgreSQL-backed or alpha-stable persisted auth storage, not module-level in-memory auth state.
  - Keep JWT issuance/validation aligned to docs and reusable by Gateway/Chat/Memory routes.
  - Keep auth/config secret handling raw-vs-resolved safe so no secret expansion is ever written back into persisted config/state.

  **Must NOT do**:
  - Do not use OAuth or 2FA in MVP.
  - Do not hardcode secrets inside service modules.

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: auth is central and failure-prone.
  - **Skills**: [`test-driven-development`]
    - `test-driven-development`: auth contract must be locked by tests first.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: 9, 10, 11, F3
  - **Blocked By**: 1, 2, 3

  **References**:
  - `docs/product/mvp-services.md:92-105` - auth MVP expectations
  - `docs/dev/run-first-system.md:103-128` - exact login request/response
  - `backend/tests/test_mvp_flow.py` - current red/green contract base
  - `/Users/abhishekjha/CODE/Butler/.ref/hermes-agent/tests/hermes_cli/test_config_env_expansion.py` - reference for keeping unresolved placeholders verbatim and only resolving at runtime

  **Acceptance Criteria**:
  - [ ] valid email/password returns token + user_id
  - [ ] invalid credentials return 401
  - [ ] token can be consumed by chat and history routes
  - [ ] auth/config path never persists resolved secrets or hardcoded credentials into MVP state files

  **QA Scenarios**:
  ```
  Scenario: login works with docs contract
    Tool: Bash (curl)
    Preconditions: backend running
    Steps:
      1. POST `/api/v1/auth/login` with `{"email":"test@example.com","password":"test123"}`
      2. Assert status 200
      3. Assert JSON contains `token` and `user_id`
    Expected Result: valid token issued
    Evidence: .sisyphus/evidence/task-5-login.txt

  Scenario: login fails with wrong password
    Tool: Bash (curl)
    Preconditions: backend running
    Steps:
      1. POST `/api/v1/auth/login` with wrong password
      2. Assert status 401
    Expected Result: credentials rejected
    Evidence: .sisyphus/evidence/task-5-login-error.txt
  ```

- [ ] 6. Finish Memory session-history contract

  **What to do**:
  - Implement stable session history persistence for alpha.
  - Ensure the golden flow saves user and assistant messages by `session_id`.
  - Align `/api/v1/session/{id}` with docs response expectations.
  - Guard against stale overwrite patterns by making persistence append-only for the MVP chat transcript path.

  **Must NOT do**:
  - Do not let Gateway bypass Orchestrator to write directly in the request path.
  - Do not use fake/no-op storage in the production-grade alpha path.

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: memory persistence is core to the MVP loop.
  - **Skills**: [`test-driven-development`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: 8, 9, 11, F3
  - **Blocked By**: 1, 2, 3

  **References**:
  - `docs/system/first-flow.md:103-128` - session storage behavior
  - `docs/dev/run-first-system.md:159-175` - session history curl contract
  - `docs/product/mvp-services.md:61-72` - memory MVP data model
  - `/Users/abhishekjha/CODE/Butler/.ref/hermes-agent/agent/memory_manager.py` - reference for non-fatal provider orchestration and defensive separation between recall and sync paths
  - `/Users/abhishekjha/CODE/Butler/.ref/hermes-agent/tests/gateway/test_flush_memory_stale_guard.py` - reference for stale-overwrite prevention mindset and explicit memory safety checks

  **Acceptance Criteria**:
  - [ ] session history returns ordered messages
  - [ ] same session_id survives across request sequence within alpha runtime
  - [ ] missing/empty history is handled cleanly
  - [ ] memory persistence path is append-ordered and does not overwrite previously persisted golden-path messages

  **QA Scenarios**:
  ```
  Scenario: session history returns saved chat
    Tool: pytest / Bash (curl)
    Preconditions: valid token and one completed chat call
    Steps:
      1. GET `/api/v1/session/test123` with Bearer token
      2. Assert JSON contains user then assistant messages in order
    Expected Result: ordered history is returned
    Evidence: .sisyphus/evidence/task-6-history.txt
  ```

- [ ] 7. Finish Tools starter-tool contract

  **What to do**:
  - Implement the starter tools documented for MVP: `send_message`, `get_time`, and optionally placeholder `search_web` behind a stable interface.
  - Ensure the registry can list and execute at least one real tool successfully.
  - Keep tool config resolution explicit and testable so environment/token/runtime drift is easy to diagnose.

  **Must NOT do**:
  - Do not expand into broad external integrations.
  - Do not hide errors behind generic success payloads.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: constrained interfaces, straightforward validation.
  - **Skills**: [`test-driven-development`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: 8, 9, F3
  - **Blocked By**: 1, 2

  **References**:
  - `docs/product/mvp-services.md:74-90` - tool list and interface
  - `backend/services/tools/service.py` - current starter implementation
  - `/Users/abhishekjha/CODE/Butler/.ref/hermes-agent/tools/managed_tool_gateway.py` - reference for explicit gateway/token resolution seams and token freshness checks
  - `/Users/abhishekjha/CODE/Butler/.ref/hermes-agent/tests/tools/test_managed_tool_gateway.py` - reference for focused env override / gateway resolution tests

  **Acceptance Criteria**:
  - [ ] tools list endpoint returns expected starter tools
  - [ ] at least one tool executes successfully
  - [ ] nonexistent tool returns deterministic error
  - [ ] tool execution/config resolution failures are explicit and never silently downgraded to fake success

  **QA Scenarios**:
  ```
  Scenario: tool executes through registry
    Tool: Bash (curl)
    Preconditions: backend running
    Steps:
      1. GET `/tools/`
      2. POST `/tools/get_time/execute` with `{}`
      3. Assert JSON contains time payload
    Expected Result: real starter tool works
    Evidence: .sisyphus/evidence/task-7-tools.txt
  ```

- [ ] 8. Finish Orchestrator golden-path coordination

  **What to do**:
  - Ensure orchestrator owns classify -> build context -> generate response flow.
  - Make it use Memory and Tools via clean interfaces.
  - Keep classification simple per MVP docs.
  - Preserve ordered per-session processing semantics so future queued work cannot overwrite earlier pending turns.

  **Must NOT do**:
  - Do not pull in ML/embeddings for MVP behavior.
  - Do not let chat route duplicate orchestration logic.
  - Do not use a single mutable pending-message slot that can overwrite earlier messages for the same session.

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: orchestrator is the central coordination point.
  - **Skills**: [`test-driven-development`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: 9, 11, F3
  - **Blocked By**: 5, 6, 7

  **References**:
  - `docs/product/mvp-services.md:48-59` - orchestrator responsibilities
  - `docs/system/first-flow.md:63-101` - exact process flow
  - `backend/services/orchestrator/service.py` - current orchestrator entrypoint
  - `/Users/abhishekjha/CODE/Butler/.ref/hermes-agent/agent/memory_manager.py` - reference for central coordination through stable provider interfaces with non-fatal subsystem failures

  **Acceptance Criteria**:
  - [ ] greeting path returns expected greeting
  - [ ] tool path uses tools service
  - [ ] messages are persisted through memory for the golden flow
  - [ ] orchestration path preserves message order and does not silently drop or overwrite prior pending work

  **QA Scenarios**:
  ```
  Scenario: orchestrator handles greeting path
    Tool: pytest / Bash (curl)
    Preconditions: valid token
    Steps:
      1. POST `/api/v1/chat` with message `hello`
      2. Assert response text is `Hi! How can I help you today?`
      3. Assert request_id exists and intent type is `simple`
    Expected Result: orchestrator owns the golden path
    Evidence: .sisyphus/evidence/task-8-orchestrator.txt
  ```

- [ ] 9. Finish Gateway contract alignment

  **What to do**:
  - Make the externally visible alpha contract match docs for `/api/v1/chat`, `/api/v1/auth/login`, and `/api/v1/session/{id}`.
  - Keep Gateway responsible for auth validation, request normalization, and forwarding semantics only.
  - Ensure chat/history/login are reachable through the documented API surface.
  - Add runtime-status and request-correlation behavior that makes gateway failures diagnosable from logs and health outputs.

  **Must NOT do**:
  - Do not let Gateway own orchestration or memory business rules.
  - Do not expose alternative duplicate endpoint shapes.

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: this is the user-facing contract boundary.
  - **Skills**: [`test-driven-development`]

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3
  - **Blocks**: 11, F1, F3, F4
  - **Blocked By**: 5, 6, 8

  **References**:
  - `docs/product/mvp-services.md:35-47` - gateway MVP endpoints
  - `docs/system/first-flow.md:20-61` - gateway request/response flow
  - `docs/dev/run-first-system.md:103-175` - login/chat/history curl path
  - `/Users/abhishekjha/CODE/Butler/.ref/hermes-agent/gateway/config.py` - reference for typed/null-guard config normalization and explicit runtime policy modeling
  - `/Users/abhishekjha/CODE/Butler/.ref/hermes-agent/tests/hermes_cli/test_gateway_runtime_health.py` - reference for surfacing exact startup/runtime failure reasons to operators

  **Acceptance Criteria**:
  - [ ] all three alpha endpoints are reachable and docs-conformant
  - [ ] invalid token returns 401
  - [ ] chat flow uses documented request/response format
  - [ ] gateway/runtime failures emit actionable reason strings tied to request_id or startup status

  **QA Scenarios**:
  ```
  Scenario: gateway alpha contract works end to end
    Tool: Bash (curl)
    Preconditions: backend running, valid token available
    Steps:
      1. POST `/api/v1/chat` with Bearer token and `{ "message": "hello", "session_id": "test123" }`
      2. Assert status 200
      3. Assert response includes `response`, `request_id`, `intent`
    Expected Result: docs-backed chat contract works
    Evidence: .sisyphus/evidence/task-9-gateway.txt

  Scenario: invalid token rejected
    Tool: Bash (curl)
    Preconditions: backend running
    Steps:
      1. POST `/api/v1/chat` with `Bearer bad-token`
      2. Assert status 401
    Expected Result: invalid token rejected consistently
    Evidence: .sisyphus/evidence/task-9-gateway-error.txt
  ```

- [ ] 10. Harden config, security, and dependency injection for alpha

  **What to do**:
  - Centralize secrets/config in settings.
  - Ensure dependency injection is the only way routes access auth/memory/tools/orchestrator services.
  - Remove insecure leftovers like fake crypto or hardcoded secrets from MVP path.
  - Add centralized logging bootstrap with correlation/request context and idempotent setup.
  - Keep raw config loading separate from resolved runtime settings and always read config with explicit UTF-8 handling.

  **Must NOT do**:
  - Do not overbuild full production security platform.
  - Do not add non-MVP security threat-detection scope.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: security/config mistakes create high-risk failures.
  - **Skills**: [`careful`, `test-driven-development`]
    - `careful`: protects against hidden risky changes.
    - `test-driven-development`: verifies behavior stays locked.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: 11, F2, F3
  - **Blocked By**: 5, 6, 7, 8

  **References**:
  - `backend/core/config.py` - settings shape
  - `backend/core/security.py` - JWT and password handling
  - `backend/core/dependencies.py` - injection hub
  - `docs/services/AGENTS.md` - security and ownership conventions
  - `/Users/abhishekjha/CODE/Butler/.ref/hermes-agent/hermes_cli/config.py` - reference for canonical config path ownership, file-permission hardening, and runtime/config separation
  - `/Users/abhishekjha/CODE/Butler/.ref/hermes-agent/hermes_logging.py` - reference for idempotent centralized logging, rotating handlers, and per-session correlation tags
  - `/Users/abhishekjha/CODE/Butler/.ref/hermes-agent/tests/hermes_cli/test_config_env_expansion.py` - reference for env expansion behavior and unresolved-placeholder preservation

  **Acceptance Criteria**:
  - [ ] no hardcoded secret in MVP auth path
  - [ ] DI is used by all alpha routes
  - [ ] security-sensitive helpers are centralized
  - [ ] config loader uses explicit UTF-8, separates raw-vs-resolved values, and never writes resolved secrets back to disk
  - [ ] logging setup is idempotent and correlation/request context is present for MVP request flow

  **QA Scenarios**:
  ```
  Scenario: auth path uses centralized config
    Tool: Bash / Read
    Preconditions: source code available
    Steps:
      1. Search backend for hardcoded auth secrets in MVP path
      2. Assert settings and security modules are the source of secret usage
    Expected Result: no duplicate hardcoded secret remains in alpha path
    Evidence: .sisyphus/evidence/task-10-security.txt
  ```

- [ ] 11. Finalize alpha launch assets and smoke script

  **What to do**:
  - Make launch steps for backend-only alpha deterministic.
  - Add or fix smoke script that performs login -> chat -> session history.
  - Ensure docker-compose and local commands reflect backend-only alpha scope.
  - Capture runtime-health evidence alongside smoke output so launch failures show exact reason, not just a failing exit code.

  **Must NOT do**:
  - Do not assume frontend availability.
  - Do not leave launch instructions split across conflicting docs.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: final wiring and script checks.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3
  - **Blocks**: F3
  - **Blocked By**: 3, 4, 5, 6, 8, 9, 10

  **References**:
  - `docs/dev/run-first-system.md` - expected launch and smoke commands
  - `docker-compose.yml` - runtime topology
  - `/Users/abhishekjha/CODE/Butler/.ref/hermes-agent/tests/hermes_cli/test_gateway_runtime_health.py` - reference for exact failure surfaces to preserve in smoke/runtime evidence

  **Acceptance Criteria**:
  - [ ] one smoke script validates alpha backend launch
  - [ ] launch docs and actual runtime match
  - [ ] login -> chat -> history works from script
  - [ ] smoke evidence captures health/readiness detail sufficient to explain startup failures without manual source inspection

  **QA Scenarios**:
  ```
  Scenario: smoke script proves alpha launch
    Tool: Bash
    Preconditions: Docker available, backend stack booted
    Steps:
      1. Run backend smoke script
      2. Assert login succeeds
      3. Assert chat succeeds
      4. Assert session history contains user + assistant messages
    Expected Result: full alpha MVP flow passes unattended
    Evidence: .sisyphus/evidence/task-11-smoke.txt
  ```

- [ ] 12. Keep secondary services as non-blocking placeholders only

  **What to do**:
  - Ensure non-MVP services remain present in structure but do not block alpha backend launch.
  - Verify placeholder packages do not break imports, startup, or tests.
  - Document that these are deferred beyond alpha launch.

  **Must NOT do**:
  - Do not expand Realtime, ML, Search, Communication, Device, Vision, Audio, Observability, Security threat detection, Workflows beyond minimal placeholders.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: structure validation, not feature buildout.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: F4
  - **Blocked By**: 2

  **References**:
  - `docs/product/mvp-services.md:109-126` - explicit non-MVP services
  - `backend/services/` - current package inventory

  **Acceptance Criteria**:
  - [ ] placeholder services do not block runtime
  - [ ] plan explicitly marks them deferred

  **QA Scenarios**:
  ```
  Scenario: non-MVP placeholders do not break startup
    Tool: Bash
    Preconditions: backend environment installed
    Steps:
      1. Run `python -m compileall backend`
      2. Run `python -c "import backend.main; print('ok')"`
    Expected Result: placeholder packages are structurally safe
    Evidence: .sisyphus/evidence/task-12-placeholders.txt
  ```

---

## Final Verification Wave

- [ ] F1. **Plan Compliance Audit** — `oracle`
- [ ] F2. **Code Quality Review** — `unspecified-high`
- [ ] F3. **Real API QA** — `unspecified-high`
- [ ] F4. **Scope Fidelity Check** — `deep`

### Hermes-Specific Final Checks

- [ ] No resolved secret values are written back to persisted config/state during any MVP flow
- [ ] No single pending-message overwrite path exists in gateway/orchestrator request handling
- [ ] `/health` and startup logs surface actionable failure reasons
- [ ] Logging bootstrap is idempotent and correlation/request identifiers appear in golden-path evidence

---

## Commit Strategy

- 1: `chore(docs): lock backend MVP source of truth`
- 2: `test(auth): add login contract coverage`
- 3: `feat(auth): complete alpha login and token flow`
- 4: `test(memory): add session history coverage`
- 5: `feat(memory): complete session persistence`
- 6: `test(tools-orchestrator): add golden-path coverage`
- 7: `feat(orchestrator): complete alpha execution flow`
- 8: `feat(gateway): align chat/history routes with docs`
- 9: `chore(runtime): finalize docker and alpha smoke flow`

---

## Success Criteria

### Verification Commands
```bash
cd /Users/abhishekjha/CODE/Butler/backend && source .venv/bin/activate && pytest tests/test_mvp_flow.py -q
cd /Users/abhishekjha/CODE/Butler && python -m compileall backend
cd /Users/abhishekjha/CODE/Butler && docker-compose up -d db cache api
```

### Final Checklist
- [ ] MVP 5-service alpha scope only
- [ ] Login works with JSON email/password contract
- [ ] Chat works with Bearer token
- [ ] Session history returns persisted conversation
- [ ] One real starter tool path works through orchestrator
- [ ] Docker/runtime path is launchable for alpha backend
