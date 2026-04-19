# Hermes Library Map for Butler Services

> **For:** Engineering  
> **Status:** Active (v1.1) [MAPPING AUTHORITY: Core, Agent, Tools | DEFERRED: Skills, Plugins]
> **Version:** 1.1  
> **Reference:** Multi-source capability mapping for Oracle-grade intelligence integration

---

## 0. Integration Status

| Module | Status | Butler Owner | Description |
|-------|--------|--------------|-------------|
| `agent/` | [ACTIVE] | Orchestrator, ML | Prompt, context, and runtime helpers |
| `tools/` | [ACTIVE] | Tools Service | Registry, file, and web execution |
| `gateway/`| [ACTIVE] | Gateway, Realtime | Session and delivery patterns |
| `skills/` | [DEFERRED] | Feature Services | Specialized domain capabilities |
| `plugins/`| [DEFERRED] | Memory Service | Pluggable backend extensions |

---

## 1. Purpose

This document maps the imported Hermes code under `backend/integrations/hermes/` to Butler service ownership.

It answers three questions:

1. **What does each Hermes area do?**
2. **Which Butler service or domain should consume it?**
3. **Should it be active now, adapted behind a wrapper, deferred, or isolated?**

This is a **service-facing library map**, not a product redefinition.

---

## 2. Non-Negotiables

- Butler services consume Hermes through **Butler-owned wrappers**, not raw route imports.
- Hermes code is a **capability source**, not Butler's product identity.
- Butler docs override imported Hermes assumptions whenever they conflict.
- The active MVP path remains: **Gateway → Auth → Orchestrator → Memory → Tools**.
- CLI, operator, and training surfaces stay **deferred or isolated** until Butler's documented runtime needs them.

---

## 3. Usage Modes

| Mode | Meaning |
|---|---|
| Active now | Safe to use in the current Butler service path behind Butler wrappers |
| Adapt behind wrapper | Useful, but Butler must own contracts, naming, and policy |
| Deferred | Valuable later, but not part of the current MVP runtime |
| Isolated | Preserve for compatibility or operator workflows, but do not let it shape Butler service behavior |

---

## 4. Service Consumption Rules

| Butler service/domain | Hermes inputs allowed |
|---|---|
| Gateway | `gateway/session.py`, `gateway/delivery.py`, selected `gateway/config.py` patterns |
| Auth | selective patterns from `agent/credential_pool.py`, `acp_adapter/auth.py`, `acp_adapter/permissions.py` |
| Orchestrator | `run_agent.py`, `agent/*`, `model_tools.py`, `toolsets.py` behind runtime adapters |
| Memory | `hermes_state.py`, `state.py`, `agent/memory_manager.py`, `agent/context_compressor.py`, memory plugins |
| Tools | `tools/*`, `model_tools.py`, `toolsets.py`, `toolset_distributions.py`, safety helpers |
| Communication | deferred channel adapters from `gateway/platforms/*`, plus `send_message` tool patterns |
| Realtime | `gateway/stream_consumer.py`, session/event compatibility patterns |
| Search | `tools/web.py`, `tools/browser_*`, `skills/research/*` as future search capability inputs |
| ML | `agent/model_metadata.py`, `agent/prompt_caching.py`, `agent/usage_pricing.py`, `agent/context_engine.py` |
| Security | `tools/approval.py`, `tools/path_security.py`, `tools/url_safety.py`, `tools/tirith_security.py`, `agent/redact.py` |
| Data | Hermes event/session schemas only as compatibility references, not ownership transfer |

---

## 5. Directory and Root File Map

| Hermes path | What it contains | Butler owner/wrapper | Mode | How Butler should use it |
|---|---|---|---|---|
| `acp_adapter/` | Agent control plane compatibility modules: auth, events, permissions, server, session, tools | Gateway + Orchestrator + Auth wrappers | Deferred / Isolated | Keep for future A2A/ACP compatibility. Do not let Butler routes import it directly. Use as reference material for internal agent control APIs only. |
| `agent/` | Prompt building, context compression, memory routing, retry logic, model metadata, redaction, runtime helpers | Orchestrator, Memory, ML, Security | Adapt behind wrapper | Best source of execution helpers. Butler should wrap prompt/context/runtime behavior so Butler state machine and policy remain authoritative. |
| `core/` | Rebranded constants, time, and utility helpers | Core shared backend utilities | Active now | Safe generic helpers. Use through Butler core modules where naming and path assumptions are already cleaned up. |
| `cron/` | Scheduler and jobs support | Automation / Tools / future Workflows | Deferred | Keep for later scheduled workflows and automation, but do not promote into the MVP path yet. |
| `gateway/` | Session, delivery, routing, stream consumption, platform integration patterns | Gateway + Communication + Realtime | Adapt behind wrapper | Reuse `session.py` and `delivery.py` patterns now. Keep `platforms/*` and operator behavior deferred until channel integrations become active. |
| `optional-skills/` | Domain-specific optional capability packs and helper scripts | Tools + Plugins + future specialized services | Deferred | Preserve as capability inventory. Only expose through explicit Butler plugin decisions, not automatic discovery. |
| `plugins/` | Plugin catalog plus memory/context plugins | Memory + Tools + Orchestrator | Deferred / Adapt | Good reference for plugin-backed memory providers. Butler should own plugin contracts and activation policy. |
| `skills/` | Preserved capability bundles for productivity, research, media, red teaming, mlops | Tools + Search + Communication + future feature services | Deferred / Adapt | Treat as a library of optional capabilities. Promote only through Butler-owned workflows or tool adapters. |
| `tools/` | Registry, approval, process tracking, file/web/terminal tools, browser/code/MCP/delegation surfaces | Tools service | Active now / Adapt | Strongest current import. Butler Tools service should wrap schemas, permission checks, audit policy, and execution safety around these primitives. |
| `batch_runner.py` | Parallel dataset runner for multi-prompt jobs | ML / offline evaluation / tooling | Deferred | Useful for offline eval and training workflows, not for request-serving services. |
| `cli.py` | Interactive Hermes terminal application | No Butler service owner; operator compatibility only | Isolated | Do not document as Butler product behavior. Keep as preserved operator surface only. |
| `hermes_constants.py` | Hermes home path and env worldview | Core compatibility layer only | Isolated / Adapt | Use carefully as a compatibility layer. Do not let `HERMES_HOME` or CLI profile assumptions leak into Butler service contracts. |
| `hermes_logging.py` | Structured logging helpers | Core / Observability | Active now | Reuse logging patterns where generic. Rebrand outputs and service naming as Butler-owned. |
| `hermes_state.py` | Session DB with SQLite + FTS5 for messages and sessions | Memory service | Adapt behind wrapper | Strong candidate for fast session/history persistence behind Butler memory contracts. |
| `hermes_time.py` | Time and timezone helpers | Core shared utils | Active now | Safe generic helper import for scheduling, session metadata, and user-facing time logic. |
| `mcp_serve.py` | Stdio MCP server exposing conversations and permissions | Gateway / Tools / ACP future surface | Isolated | Keep as compatibility asset. Do not treat it as Butler's public HTTP gateway implementation. |
| `mini_swe_runner.py` | Specialized coding-task runner | Orchestrator / Tools experiments | Deferred | Preserve for future autonomous coding or evaluation workflows, not current Butler services. |
| `model_tools.py` | Thin orchestration layer over the Hermes tool registry with async bridging and discovery | Tools service | Adapt behind wrapper | Use as Butler's imported execution substrate, but Butler Tools remains the authority for registration, permissions, verification, and auditability. Orchestrator should consume it only through Butler Tools interfaces or service calls. |
| `rl_cli.py` | Reinforcement-learning CLI | ML / offline training | Isolated | Preserve for operator/training workflows only. Not an active Butler service dependency. |
| `run_agent.py` | Main AI agent runner with tool-calling loop and provider support | Orchestrator | Adapt behind wrapper | High-value runtime substrate. Butler must wrap it so orchestrator policy, state transitions, approvals, and memory contracts stay Butler-owned. |
| `state.py` | Butler-labeled SQLite session/message store compatibility layer | Memory service | Active now / Adapt | Useful immediate store for session transcripts and search. Prefer this over direct raw `SessionDB` imports when Butler wants integration-owned state with Butler defaults. |
| `toolset_distributions.py` | Probability distributions for selecting toolsets during batch/eval runs | Tools + ML offline evaluation | Deferred | Keep for testing, benchmarking, and eval pipelines rather than request path logic. |
| `toolsets.py` | Toolset grouping and composition rules | Tools service | Adapt behind wrapper | Good source for capability bundles and allowlists. Butler should own which toolsets are exposed per service path and risk tier. |
| `trajectory_compressor.py` | Compression/support utility for trajectories and long transcripts | Memory + ML + offline evaluation | Deferred / Adapt | Useful for transcript compaction and analysis, but not critical to the current MVP runtime. |
| `utils.py` | Generic helper functions | Core shared utils | Active now | Safe shared helper surface once Butler naming and dependency boundaries are preserved. |

---

## 6. Subtree Notes for the Most Important Directories

### 6.1 `agent/`

| Sub-area | Butler use |
|---|---|
| `prompt_builder.py`, `context_engine.py` | Orchestrator prompt/context assembly behind Butler runtime adapters |
| `context_compressor.py`, `compressor.py` | Memory and Orchestrator token budget management |
| `memory_manager.py`, `memory_provider.py` | Memory provider orchestration and retrieval composition |
| `error_classifier.py`, `retry_utils.py`, `rate_limit_tracker.py` | Orchestrator resilience and upstream failure handling |
| `model_metadata.py`, `usage_pricing.py`, `prompt_caching.py` | ML/runtime support, provider metadata, cost accounting |
| `redact.py` | Security/privacy helper for logs and prompts |
| `display.py`, `skill_commands.py`, `trajectory.py` | Keep isolated from Butler product behavior |

### 6.2 `gateway/`

| Sub-area | Butler use |
|---|---|
| `session.py`, `session_context.py` | Gateway/Realtime session helper patterns |
| `delivery.py`, `channel_directory.py` | Communication routing and channel metadata |
| `stream_consumer.py` | Realtime/event-stream design input |
| `platforms/*` | Deferred channel adapters for Communication service |
| `run.py`, `display_config.py`, `restart.py`, `mirror.py` | Preserve, but keep out of active Butler service docs unless promoted later |

### 6.3 `tools/`

| Sub-area | Butler use |
|---|---|
| `registry.py`, `approval.py`, `process_registry.py` | Core Butler Tools service substrate |
| `terminal.py`, `files.py`, `web.py`, `send_message_tool.py` | Best current real-tool inputs for MVP vertical slices |
| `path_security.py`, `url_safety.py`, `tirith_security.py`, `tool_backend_helpers.py` | Safety controls and execution hardening |
| `browser_*`, `code_execution.py`, `delegate_tool.py`, `mcp_tool.py`, `vision_tools.py`, `voice_mode.py` | Deferred advanced capability surfaces |
| `skills_*`, `todo_tool.py`, `memory_tool.py` | Only expose through Butler-owned workflow decisions, not direct inheritance |

### 6.4 `plugins/` and `skills/`

These are best treated as **capability inventory**:

- `plugins/memory/*` informs future pluggable memory backends.
- `skills/research/*`, `skills/productivity/*`, `skills/media/*` inform Search, Communication, and Tools expansions.
- `optional-skills/*` is preserved for future domain modules, not the current product path.

---

## 7. How Services Should Use Hermes as a Library

### Correct pattern

```python
# Butler-owned wrapper
from backend.domain.orchestrator.runtime_adapter import ButlerRuntimeAdapter
from backend.domain.tools.registry import ButlerToolRegistry
from backend.domain.memory.session_store import ButlerSessionStore
```

### Wrong pattern

```python
# Raw imported entrypoint leaking into service contracts
from backend.integrations.hermes.run_agent import AIAgent
from backend.integrations.hermes.model_tools import handle_function_call
```

### Why

- Butler must own **contracts**.
- Hermes supplies **implementation leverage**.
- Service boundaries stay stable even if Hermes-backed internals change later.

---

## 8. Recommended Documentation Usage

Service specs should use this document in one of two ways:

1. Reference the relevant Hermes paths in their **Dependencies** and **Boundaries** sections.
2. Explain whether the Hermes surface is **active now**, **deferred**, or **isolated** for that service.

This keeps service docs concrete without duplicating the full library map in every file.

---

*Document owner: Architecture Team*  
*Last updated: 2026-04-18*
