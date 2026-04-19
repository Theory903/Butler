# Butler Hermes Assimilation Map

> **Status:** Active architecture audit  
> **Purpose:** Convert the broad Hermes import into a Butler-native subsystem plan grounded in Butler docs, MVP priorities, and modular-monolith boundaries.

---

## 1. Why This Document Exists

Hermes code has already been copied into `backend/integrations/hermes/`.

The job now is **not** raw porting.

The job is to decide, with Butler’s docs as source of truth:

- what imported code is part of Butler’s **active MVP execution path**
- what imported code is **useful but deferred**
- what imported code must remain **isolated behind integration boundaries**
- what imported code still leaks **Hermes branding, CLI assumptions, or foreign architecture**
- what wrappers/contracts Butler must own so the system reads as Butler, not a renamed Hermes fork

This document is the current control map for that assimilation work.

---

## 2. Butler Documentation Rules That Override Imported Hermes Code

The following Butler docs are the implementation authority for this assimilation:

1. `docs/AGENTS.md`
2. `docs/README.md`
3. `docs/product/mvp-services.md`
4. `docs/dev/backend-architecture.md`
5. `docs/system/first-flow.md`
6. `docs/agent/agent-loop.md`
7. `docs/services/orchestrator.md`
8. `docs/services/tools.md`
9. `docs/plugins/plugin-system.md`

### Direct constraints extracted from Butler docs

| Butler rule | Assimilation consequence |
|---|---|
| Butler is **not a chatbot wrapper** | Imported runtime cannot define Butler as “message in, text out” only |
| Butler is a **personal AI system** that observes, understands, decides, acts, and learns | Imported agent/runtime code must be aligned around execution, not CLI UX |
| Butler MVP path is **Gateway → Auth → Orchestrator → Memory → Tools** | Imported code outside this slice must be deferred or isolated |
| Backend target is a **modular monolith** | Imported packages must stay behind explicit domain/integration boundaries |
| `api/routes -> core/dependencies -> domain services -> infrastructure adapters` | Imported Hermes internals must not leak into routes or cross-service logic |
| Gateway never calls Memory directly; it goes via Orchestrator | Hermes gateway patterns must not bypass Butler service boundaries |
| Tools service owns execution, validation, permission checks, auditability | Hermes tools are useful, but Butler must own tool contracts and safety policy |
| Plugins are extension points, not core identity | Imported skills/plugins must be staged intentionally, not auto-promoted into Butler core |

---

## 3. Imported Inventory Snapshot

Current imported code under `backend/integrations/hermes/`:

| Area | Files |
|---|---:|
| root runtime/utilities | 240 total in tree |
| `agent/` | 31 |
| `tools/` | 71 |
| `tools/environments/` | 11 |
| `tools/browser_providers/` | 5 |
| `gateway/` | 41 |
| `gateway/platforms/` | 24 |
| `acp_adapter/` | 9 |
| `plugins/` | 18 |
| `plugins/memory/` | 15 |
| `skills/` | 23 |
| `optional-skills/` | 18 |
| `scripts/` | 5 |
| `cron/` | 3 |

This is a **large capability import**, not a single subsystem.

Therefore the correct Butler treatment is:

- **activate only the MVP-critical path now**
- **preserve capability without polluting Butler core**
- **isolate foreign runtime surfaces**
- **document staged ownership clearly**

---

## 4. Assimilation Strategy

Every imported package belongs to exactly one current Butler mode:

### A. Keep with light rebranding
Useful now, broadly aligned, minimal conceptual conflict.

### B. Adapt for Butler
Useful and important, but must change naming, contracts, boundaries, or behavior.

### C. Defer but keep available
Valuable later, not appropriate for active MVP path.

### D. Isolate / wrap
Foreign, CLI-first, platform-specific, or awkward for Butler’s current architecture; preserve without contaminating the core.

### X. Duplicate / transitional wrapper debt
Temporary compatibility artifacts, renamed copies, or thin wrappers that need consolidation.

---

## 5. Active Butler MVP Slice vs Imported Capability Blob

### Butler active slice right now

Per `docs/product/mvp-services.md` and `docs/dev/backend-architecture.md`, the active slice is:

1. Gateway
2. Auth
3. Orchestrator
4. Memory
5. Tools

### What that means for Hermes assimilation

Only imported code that directly strengthens one of these Butler-owned domains should become active soon.

| Butler domain | Imported Hermes capability that can help now |
|---|---|
| Gateway | session routing helpers, delivery helpers, selective channel adapter isolation |
| Orchestrator | runtime loop patterns, context assembly, prompt assembly, error classification |
| Memory | session DB patterns, memory manager interfaces, redaction utilities |
| Tools | registry, terminal/file/web tools, approval/process registry, execution discipline |
| Auth/Security | selective credential/policy helpers, never full Hermes auth worldview |

Everything else must be **deferred** or **isolated** until Butler’s golden path is real. Importing code into the tree does not make it active Butler runtime behavior.

---

## 6. Area-by-Area Assimilation Map

---

## 6.1 Root runtime and integration spine

### MODULE / AREA
- **imported source:** `run_agent.py`, `model_tools.py`, `hermes_state.py`, `hermes_constants.py`, `hermes_logging.py`, `hermes_time.py`, `utils.py`, `cli.py`, `batch_runner.py`, `trajectory_compressor.py`, `toolset_distributions.py`, `mcp_serve.py`, `rl_cli.py`
- **current purpose:** Hermes runtime entrypoints, constants, state, CLI, orchestration glue
- **Butler role:** runtime substrate + compatibility layer behind Butler-owned domain wrappers
- **action chosen:** **B / D / X mixed**

### Butler classification

| File/group | Butler role | Action | Why |
|---|---|---|---|
| `run_agent.py` | imported execution engine reference | B | Valuable for orchestration logic, but Butler must own orchestration contracts |
| `model_tools.py` | imported tool-call orchestration reference | B | Useful, but Butler Tools service must remain the execution authority |
| `hermes_state.py` | imported session/history store | B | Useful for fast vertical slice, but schema and persistence contract must be Butler-owned |
| `hermes_constants.py` | foreign path/env worldview | D | Too Hermes/profile/CLI specific; preserve as compatibility layer only |
| `hermes_logging.py`, `hermes_time.py`, `utils.py` | generic utilities | A | Mostly reusable with rebranding cleanup |
| `cli.py`, `rl_cli.py`, `mcp_serve.py` | CLI/operator surfaces | D | Butler is not a CLI product surface |
| `batch_runner.py`, `trajectory_compressor.py`, `toolset_distributions.py` | support/runtime utilities | C | Potentially useful later, not in current MVP path |

Deferred root/operator support cleanup completed:

- `trajectory_compressor.py` now uses local Butler integration imports and clearer fallback behavior; remaining unresolved imports are optional external runtime dependencies (`fire`, `rich`, `transformers`, `openai`)
- `rl_cli.py` now uses local Butler integration imports and safer CLI argument normalization; remaining unresolved import is the optional external `fire` dependency

### Architectural risks

- `run_agent.py` can re-center Butler around a general-purpose chat loop instead of Butler’s documented state machine
- `model_tools.py` can make imported tool semantics dominate Butler’s service contracts
- `hermes_constants.py` pulls in `HERMES_HOME` / profile-oriented assumptions that do not match Butler docs

### Required Butler change direction

- Keep imported runtime **behind** `backend/domain/orchestrator/runtime_adapter.py`
- Rename compatibility concepts around **Butler runtime**, not Hermes identity
- Explicitly mark CLI/operator modules as **non-product compatibility assets**

---

## 6.2 `agent/` package

### MODULE / AREA
- **imported source:** 31 files under `backend/integrations/hermes/agent/`
- **current purpose:** assistant runtime internals: prompt assembly, context compression, memory routing, tool-use guidance, auxiliary clients, insights, model metadata
- **Butler role:** internal execution helpers for Butler Orchestrator and Agent runtime
- **action chosen:** **B** for core runtime helpers, **C/D** for CLI- or vendor-specific helpers

### Keep/adapt matrix

| File/group | Butler role | Action | Notes |
|---|---|---|---|
| `prompt_builder.py` | Butler prompt/context assembly support | B | Must align with Butler identity and docs-first runtime |
| `context_engine.py` | Butler context construction support | B | Useful, but must align with Butler memory + tool-state model |
| `compressor.py` / `context_compressor.py` | context budget management | B/X | Keep one Butler-owned path; remove rename debt |
| `caching.py` / `prompt_caching.py` | provider prompt caching | B/X | Consolidate naming and clarify ownership |
| `memory_manager.py`, `memory_provider.py` | memory provider orchestration | B | Useful for Memory/Orchestrator boundary |
| `error_classifier.py`, `retry_utils.py`, `rate_limit_tracker.py` | runtime resilience | A/B | Mostly useful, but some provider-specific cleanup needed |
| `model_metadata.py`, `usage_pricing.py` | model/runtime metadata | A | Useful support utilities |
| `redact.py` | security helper | A | Strong Butler fit |
| `credential_pool.py`, `anthropic_adapter.py`, `auxiliary_client.py` | provider access/auth/routing | B/C | Keep, but isolate provider assumptions from Butler domain logic |
| `skill_utils.py`, `skill_commands.py` | Hermes skill runtime | C/D | Butler has plugin + workflow docs; commands must stay deferred |
| `display.py` | CLI presentation | D | Not Butler product behavior |
| `insights.py`, `trajectory.py`, `manual_compression_feedback.py`, `subdirectory_hints.py`, `models_dev.py`, `copilot_acp_client.py` | support/analytics/CLI/editor features | C/D | Preserve, but not in active slice |

### Butler-specific interpretation

Butler’s `docs/agent/agent-loop.md` defines a richer, authoritative state machine than a generic Hermes loop:

- Received
- Classified
- Planned
- Executing
- Waiting approval
- Failed
- Completed

So the imported `agent/` package is useful **only if** it is subordinated to Butler’s state machine, policy model, approval checks, audit flow, and learn/write-back behavior.

### Rebranding changes needed

- remove “You are Hermes Agent” identity from `agent/prompt_builder.py`
- stop injecting Hermes/CLI worldview into system prompts
- convert prompt guidance toward Butler’s documented agent behavior: observe → retrieve context → understand → policy check → validate → plan → approval → execute → audit → learn

---

## 6.3 `tools/` package

### MODULE / AREA
- **imported source:** 71 files under `tools/`
- **current purpose:** registry, tool dispatch, file/web/terminal tooling, browser automation, code execution, MCP, environments, approval, background processes
- **Butler role:** strongest imported subsystem for current MVP Tools service
- **action chosen:** **A/B** for core execution path, **C** for advanced tools, **D/X** for rename/compatibility artifacts

### High-value active path

These are the best imported assets for Butler’s documented Tools service:

| File/group | Butler role | Action |
|---|---|---|
| `registry.py` | Butler tool registry substrate | A |
| `approval.py` | permission and dangerous-action gating | A |
| `process_registry.py` | background execution tracking | A |
| `terminal.py`, `files.py`, `web.py` | starter real tools for MVP and early vertical slice | A |
| `tool_backend_helpers.py`, `debug_helpers.py`, `file_operations.py`, `path_security.py`, `url_safety.py`, `tirith_security.py` | execution safety support | B |

### Defer/isolate areas

| File/group | Butler role | Action | Reason |
|---|---|---|---|
| `browser_tool.py`, `browser_providers/*`, `browser_camofox*` | future browser automation | C | valuable but beyond first vertical slice |
| `code_execution.py` | future sandbox/code-runner | C | useful but security-heavy |
| `delegate_tool.py`, `mixture_of_agents_tool.py` | advanced agent coordination | C | Butler should not activate these before core orchestrator is stable |
| `mcp_tool.py`, `mcp_oauth.py` | future integration surface | C | important later, not MVP-critical |
| `voice_mode.py`, `tts_tool.py`, `transcription_tools.py`, `vision_tools.py` | audio/vision future phases | C | aligned with long-term Butler, not active MVP |
| `skills_*` tool files | imported skill ecosystem tooling | D | must be routed through Butler plugin/workflow strategy, not auto-exposed |

### Duplicate / rename debt

| Transitional pair | Desired outcome |
|---|---|
| `terminal_tool.py` vs `terminal.py` | keep one Butler-owned canonical filename |
| `file_tools.py` vs `files.py` | keep one canonical filename |
| `web_tools.py` vs `web.py` | keep one canonical filename |
| `code_execution_tool.py` vs `code_execution.py` | keep one canonical filename |

### Butler boundary rule

Per `docs/services/tools.md`, Butler Tools service owns:

- registration
- schema validation
- safe execution
- permission checks
- verification
- audit logging

And the imported tools must ultimately comply with Butler’s execution posture:

- sandboxing/isolation expectations
- user + session + risk aware approval logic
- Butler-owned retry/idempotency policy

So imported Hermes tools must be treated as **execution primitives**, not autonomous product definitions.

---

## 6.4 `gateway/` package

### MODULE / AREA
- **imported source:** 41 files including `platforms/`
- **current purpose:** Hermes message-gateway runtime, platform connectors, sessioning, delivery, hooks, streaming
- **Butler role:** partial source material for Butler Gateway and future Communication service, but high contamination risk
- **action chosen:** **A/B** for session/delivery helpers, **D** for platform adapters

### Keep/adapt now

| File/group | Butler role | Action |
|---|---|---|
| `session.py` | session helper candidate | A/B |
| `delivery.py` | delivery routing helper candidate | A/B |
| `status.py`, `display_config.py`, `stream_consumer.py`, `hooks.py` | operational patterns/reference | B/C |

Verified cleanup completed on the likely future-active gateway helpers:

- `gateway/session.py` now uses local integration imports and normalizes optional message fields before writing to the imported SQLite backend
- `gateway/delivery.py` now resolves home/output paths through Butler-local integration helpers and uses an explicit optional adapters map
- `gateway/status.py` now uses local integration imports and explicit PID narrowing for process-state checks

Additional gateway support cleanup completed on preserved communication infrastructure:

- `gateway/config.py`, `hooks.py`, `mirror.py`, `sticker_cache.py`, `restart.py`, and `channel_directory.py` now use local Butler integration imports instead of raw Hermes package-layout imports
- optional third-party/runtime dependencies in this cluster now degrade more safely instead of poisoning local package resolution

### Isolate

All `gateway/platforms/*` remain **isolated compatibility assets**:

- `telegram.py`
- `discord.py`
- `slack.py`
- `whatsapp.py`
- `matrix.py`
- `mattermost.py`
- `email.py`
- `sms.py`
- `homeassistant.py`
- `wecom.py`
- `weixin.py`
- `dingtalk.py`
- `feishu.py`
- `qqbot.py`
- `signal.py`
- `webhook.py`
- `api_server.py`
- `bluebubbles.py`
- helper/support files

### Why isolate instead of activate

Butler docs currently say:

- MVP transport is HTTP through Gateway
- Gateway validates auth and forwards to Orchestrator
- Communication service is a later expansion

Therefore these platform adapters are **future channels/integrations**, not current Butler core.

They should be documented as:

- preserved
- off the MVP path
- available for later Communication / Channel Adapter work

Shared adapter-support cleanup completed without activating the full adapter surface:

- `gateway/platforms/helpers.py` now uses local Butler integration imports instead of raw Hermes package-layout imports
- `gateway/platforms/base.py` now uses local Butler integration imports, optional dependency loading for SOCKS proxy support, and safer hook/handler/runtime guards without changing adapter activation status

---

## 6.5 `acp_adapter/`

### MODULE / AREA
- **imported source:** 9 files
- **current purpose:** ACP server and editor integration surface
- **Butler role:** future developer/operator integration surface only
- **action chosen:** **D**

### Decision

Keep intact, but explicitly mark as:

- non-MVP
- non-core
- not part of Butler’s user-facing runtime identity

Verified local cleanup completed on the preserved ACP package:

- local Hermes/package-layout imports were normalized inside `auth.py`, `session.py`, `entry.py`, and `server.py`
- terminal and model/tool references now point at local Butler integration modules instead of raw Hermes package paths
- remaining unresolved imports are the expected external `acp` / `acp.schema` dependency, which is acceptable because ACP remains an isolated optional surface rather than an active Butler requirement

Useful later for:

- IDE integration
- operator tooling
- devtools attachment

Not useful as current product-surface code.

---

## 6.6 `plugins/` and memory plugin ecosystem

### MODULE / AREA
- **imported source:** 18 files, mostly `plugins/memory/*`
- **current purpose:** external memory backends and related plugin scaffolding
- **Butler role:** future pluggable memory/integration ecosystem
- **action chosen:** **C** for most plugins, **A/B** for plugin cataloging concepts

### Imported plugin families

| Family | Action | Butler interpretation |
|---|---|---|
| `memory/honcho` | C | optional memory backend |
| `memory/hindsight` | C | optional memory backend |
| `memory/openviking` | C | optional memory backend |
| `memory/mem0` | C | optional memory backend |
| `memory/supermemory` | C | optional memory backend |
| `memory/retaindb` | C | optional memory backend |
| `memory/holographic` | C | optional memory backend |
| `memory/byterover` | C | optional memory backend |

### Butler alignment

Per `docs/plugins/plugin-system.md`, Butler plugins are extension points that:

- expose tools or routes intentionally
- declare permissions
- load through a plugin manager

So imported Hermes plugin code should be framed as:

- **future plugin candidates**
- **not auto-loaded core dependencies**
- **available through a Butler-owned plugin manager contract later**

---

## 6.7 `skills/` and `optional-skills/`

### MODULE / AREA
- **imported source:** 23 skills + 18 optional-skills
- **current purpose:** Hermes skill ecosystem, scripts, office/research/media/productivity capabilities
- **Butler role:** future workflows, plugins, or specialized operator capabilities
- **action chosen:** **C** for most, **B** for selected high-value future workflows

### Imported skill categories

| Category | Examples | Butler action |
|---|---|---|
| productivity | powerpoint, google-workspace, ocr-and-documents | C/B |
| media | youtube-content | C |
| research | arxiv, polymarket | C |
| creative | excalidraw, meme-generation | C |
| health / blockchain / mcp / telephony | optional-skills | C |
| red-teaming | godmode | D/C depending on security strategy |

### Butler interpretation

Butler docs say the current goal is a working vertical slice, not a giant capability catalog.

Therefore imported skills should be treated as:

- **staged capability inventory**
- candidates for future Workflow / Plugin / Communication / Productivity subsystems
- preserved under integration until Butler defines the activation model

They should **not** be presented as active Butler product features today.

Related shared operator-surface cleanup completed without activating the full CLI:

- `agent/display.py` now uses local integration imports and optional dynamic loading for skin/prompt-toolkit helpers
- `agent/skill_commands.py` now uses local integration imports for skill loading/config helpers and remains suitable for deferred CLI/gateway command surfaces

---

## 6.8 `cron/` and scheduler helpers

### MODULE / AREA
- **imported source:** `cron/__init__.py`, `jobs.py`, `scheduler.py`
- **current purpose:** job scheduling and background execution cadence
- **Butler role:** future Automation / Workflow scheduling support
- **action chosen:** **B/C**

### Decision

- keep as imported scheduler substrate
- adapt naming and env assumptions later
- do not let cron semantics define Butler’s automation model yet

Useful after the first end-to-end Butler loop is running.

---

## 7. Current Highest-Priority Conflicts Found in Imported Code

The following patterns are the most important Butler/Hermes conflicts currently visible:

### 7.1 Hermes-branded runtime identity

Examples:

- `backend/integrations/hermes/agent/prompt_builder.py`
- `backend/integrations/hermes/hermes_constants.py`
- `backend/integrations/hermes/hermes_logging.py`
- `backend/integrations/hermes/hermes_state.py`
- `backend/integrations/hermes/agent/anthropic_adapter.py`
- `backend/integrations/hermes/agent/auxiliary_client.py`

Conflict:

- Butler identity is execution-first personal AI runtime
- Hermes prompt/runtime language still frames the imported system as “Hermes Agent”

### 7.2 `HERMES_*` env/path worldview

Examples:

- `HERMES_HOME`
- `HERMES_SESSION_*`
- `HERMES_CRON_*`
- `HERMES_MODEL`

Conflict:

- Butler docs do not define Hermes profile/home semantics as product architecture
- these values must either be wrapped, renamed, or confined to the compatibility layer

### 7.3 CLI-first assumptions

Examples:

- `cli.py`
- `agent/display.py`
- `skill_commands.py`
- ACP/editor operator surfaces

Conflict:

- Butler is not a CLI product
- imported CLI ergonomics must not define Butler runtime behavior

### 7.4 Tool and gateway autonomy leakage

Conflict:

- imported Hermes runtime sometimes assumes direct tool-centric or platform-centric control flows
- Butler docs require service boundaries and orchestrator-centered execution

---

## 8. Duplicate / Transitional Debt That Must Be Cleaned Up

These are not “delete imported capability” issues. They are integration hygiene issues.

| Problem | Current examples | Correct Butler move |
|---|---|---|
| rename duplicates | `terminal_tool.py` + `terminal.py` | settle one canonical filename |
| rename duplicates | `file_tools.py` + `files.py` | canonicalized with compatibility shim in `file_tools.py` |
| rename duplicates | `web_tools.py` + `web.py` | settle one canonical filename |
| rename duplicates | `code_execution_tool.py` + `code_execution.py` | settle one canonical filename |
| rename duplicates | `context_compressor.py` + `compressor.py` | canonicalized with compatibility shim in `context_compressor.py` |
| rename duplicates | `prompt_caching.py` + `caching.py` | canonicalized with compatibility shim in `prompt_caching.py` |
| thin wrappers with Hermes naming | `HermesAIAgentRuntime`, `HermesSessionDB` wrappers | shift public wrapper names toward Butler-native contracts |

---

## 9. Butler-Owned Wrapper and Boundary Targets

The imported integration should ultimately be consumed through Butler-owned contracts like:

| Butler contract | Current state | Needed direction |
|---|---|---|
| `backend/domain/orchestrator/runtime_adapter.py` | thin wrapper around `HermesAIAgentRuntime` | strengthen into Butler runtime contract |
| `backend/domain/tools/registry.py` | thin wrapper around Hermes registry | make Butler registry semantics primary |
| `backend/domain/memory/session_store.py` | thin wrapper around imported session DB | align with Butler session/history schema |
| future plugin manager | not yet Butler-owned | imported plugins/skills should route through this later |
| future channel adapter registry | not yet Butler-owned | imported platform adapters should plug in here later |

---

## 10. Immediate Butler-Native Change Queue

### Phase A: docs and naming cleanup

1. Rewrite this assimilation map to Butler-docs-first shape ✅
2. Update `backend/integrations/hermes/README.md` to distinguish:
   - active MVP assets
   - deferred capability inventory
   - isolated compatibility surfaces
3. Normalize the integration layer around **Butler-owned wrappers**, not “Hermes runtime but wrapped” language

### Phase B: highest-value code changes

1. Rebrand prompt identity in `agent/prompt_builder.py`
2. Consolidate renamed duplicate files into canonical Butler filenames
3. Clarify `core/constants.py` as Butler compatibility constants instead of copying Hermes semantics blindly
4. Rename or wrap public integration types so Butler-facing code stops exposing Hermes names casually

### Phase C: staged boundary hardening

1. Mark `gateway/platforms/*`, `acp_adapter/*`, CLI surfaces, and most skills/plugins as **deferred or isolated** in code-facing docs
2. Keep imported tool registry and execution helpers available for the MVP Tools slice
3. Keep imported memory/session helpers available for the MVP Memory slice
4. Continue cleaning deferred support modules in place so preserved capability behaves like a local Butler integration package even before activation

Deferred tool-support cleanup completed:

- `tools/managed_tool_gateway.py`, `tools/browser_camofox.py`, and `tools/tirith_security.py` now use local Butler integration imports instead of raw Hermes package-layout imports
- optional runtime/config dependencies in this cluster now degrade more safely while staying outside the active Butler MVP path

---

## 11. Definition of Assimilation Done

Assimilation is not complete when files are merely copied.

Assimilation is complete when:

- Butler docs clearly explain how imported Hermes capability fits Butler’s architecture
- Butler-facing code reads like Butler, not a renamed Hermes shell
- active MVP path is clean: Gateway → Auth → Orchestrator → Memory → Tools
- imported tools and runtime helpers are useful without redefining Butler’s identity
- platform adapters, CLI surfaces, ACP surfaces, optional skills, and plugin backends are preserved but clearly deferred/isolated
- duplicate transitional files are consolidated
- public wrappers stop leaking Hermes names where Butler should own the concept

---

## 12. Current Status

| Area | Status |
|---|---|
| Deep Butler-docs-first audit | complete |
| Imported package inventory | complete |
| Rebranding hotspot discovery | complete |
| Assimilation strategy rewrite | complete |
| Oracle architecture review | complete |
| Active-path wrapper/runtime cleanup | complete for current slice |
| Code/doc follow-up edits | in progress |

### Verified active slice

The following Butler-facing seams have been reworked and verified as part of the active assimilation path:

- `backend/domain/orchestrator/runtime_adapter.py`
- `backend/domain/memory/session_store.py`
- `backend/domain/tools/registry.py`
- `backend/domain/automation/scheduler.py`
- `backend/domain/workflows/skills_catalog.py`
- `backend/integrations/hermes/agent/runtime.py`
- `backend/integrations/hermes/agent/prompt_builder.py`
- `backend/integrations/hermes/agent/anthropic_adapter.py`
- `backend/integrations/hermes/agent/context_compressor.py`
- `backend/integrations/hermes/agent/prompt_caching.py`
- `backend/integrations/hermes/core/constants.py`
- `backend/integrations/hermes/state.py`
- `backend/integrations/hermes/tools/file_tools.py`
- `backend/integrations/hermes/tools/files.py`
- `backend/integrations/hermes/tools/__init__.py`
- `backend/integrations/hermes/tools/registry.py`
- `backend/integrations/hermes/cron/__init__.py`
- `backend/integrations/hermes/cron/jobs.py`
- `backend/integrations/hermes/hermes_time.py`

Verification completed on this slice:

- `lsp_diagnostics` clean on touched active-path Python files
- `python3 -m py_compile` clean on touched active-path Python files
- focused backend tests passing:
  - `test_orchestrator_runtime_adapter.py`
  - `test_automation_scheduler.py`
  - `test_hermes_session_store.py`
  - `test_skills_catalog.py`
  - `test_hermes_core_imports.py`
  - `test_hermes_tool_registry.py`

Additional verified provider-path cleanup:

- `agent/anthropic_adapter.py` now preserves Butler identity during prompt sanitization instead of rewriting product identity to `Claude Code`
- stale top-level integration imports in the provider path were normalized to local Butler integration imports

Additional verified active-tool cleanup:

- `tools/files.py` now uses canonical local integration imports instead of raw Hermes package-style imports
- `tools/file_tools.py` is now a compatibility shim re-exporting the canonical `files.py` module
- `tools/__init__.py` now points file-tool requirements at the canonical `terminal.py` module

This document should be updated as code changes land so it remains the single living map for Butler’s Hermes assimilation work.
