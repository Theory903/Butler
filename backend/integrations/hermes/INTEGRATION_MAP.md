# Hermes-to-Butler Integration Reference

**Source:** `.ref/butler-agent/`  
**Target:** `backend/integrations/hermes/`  
**Primary strategy doc:** `docs/system/hermes-assimilation-map.md`

> This file is now a lightweight historical/reference map.
> The active Butler-owned assimilation strategy lives in
> `docs/system/hermes-assimilation-map.md` and Butler docs under `docs/`.

---

## Integration Status

| Hermes Module | Butler Adapter | Status |
|---------------|----------------|--------|
| Runtime/core utilities | `backend/integrations/hermes/` | ✅ Imported |
| Agent package | `backend/integrations/hermes/agent/` | ✅ Imported |
| Tools package | `backend/integrations/hermes/tools/` | ✅ Imported |
| Gateway + platforms | `backend/integrations/hermes/gateway/` | ✅ Imported |
| ACP adapter | `backend/integrations/hermes/acp_adapter/` | ✅ Imported |
| Plugins + memory plugins | `backend/integrations/hermes/plugins/` | ✅ Imported |
| Skills + optional-skills | `backend/integrations/hermes/skills/` and `optional-skills/` | ✅ Imported |
| Scheduler | `backend/integrations/hermes/cron/` | ✅ Imported |

Imported does **not** mean active in Butler’s MVP path.
Active/deferred/isolated decisions are tracked in the main assimilation map.

---

## Hermes Core Files → Butler Adapters

### 1. Core Utilities

| Hermes File | Butler Adapter | Purpose |
|------------|----------------|---------|
| `hermes_constants.py` | `core/constants.py` | `HERMES_HOME`, paths, constants |
| `hermes_time.py` | `core/time_module.py` | Timezone-aware utilities |
| `utils.py` | `core/utils.py` | Common helpers |
| `hermes_logging.py` | `core/logging.py` | Structured logging |

**Current note:** these utilities are imported, but still require Butler-native
renaming and boundary cleanup where they leak Hermes identity or profile semantics.

### 2. Session State (hermes_state.py)

| Hermes | Butler |
|--------|--------|
| `SessionDB` (SQLite + FTS5) | `HermesSessionDB` → `integrations/hermes/state.py` |
| Session keys | Butler owns session format |

**Butler wrapper:** `backend/domain/memory/session_store.py` wraps HermesSessionDB

### 3. Tool System (model_tools.py + tools/)

| Hermes | Butler |
|--------|--------|
| `get_tool_definitions()` | `ButlerToolRegistry.get_schemas()` |
| `handle_function_call()` | `ButlerToolRegistry.execute()` |
| `tools/registry.py` | `integrations/hermes/tools/registry.py` |
| Individual tools (`tools/*.py`) | TBD - one file per tool |

**Butler wrapper:** `backend/domain/tools/registry.py` wraps Hermes tool registry

---

## Butler Package → Butler Adapters

The `agent/` package in Hermes contains the core AI agent logic:

| Hermes File | Butler Adapter | Purpose |
|-------------|----------------|---------|
| `prompt_builder.py` (1043 lines) | `agent/prompt_builder.py` | System prompt assembly |
| `context_compressor.py` (1091 lines) | `agent/compressor.py` | Context window compression |
| `prompt_caching.py` (72 lines) | `agent/caching.py` | Anthropic prompt caching |
| `memory_manager.py` (361 lines) | `agent/memory_manager.py` | Memory provider orchestration |
| `display.py` (1037 lines) | N/A | CLI presentation (not needed) |
| `skill_commands.py` (370 lines) | N/A | Slash commands (not needed) |
| `trajectory.py` (56 lines) | N/A | Trajectory saving (not needed) |

### Key Butler-owned wrappers

**prompt_builder.py:**
```python
# Imported implementation stays here
from backend.integrations.hermes.agent.prompt_builder import build_skills_system_prompt

# Butler-facing runtime/domain code should consume it through Butler-owned wrappers
```

**context_compressor.py:**
```python
from backend.integrations.hermes.agent.compressor import ButlerContextCompressor
```

**memory_manager.py:**
```python
from backend.integrations.hermes.agent.memory_manager import ButlerMemoryManager
```

---

## Hermes Gateway → Butler Adapters

The gateway provides multi-platform messaging:

| Hermes | Butler |
|--------|--------|
| `gateway/run.py` (GatewayRunner) | `gateway/gateway.py` |
| `gateway/session.py` (SessionStore) | `gateway/session.py` |
| `gateway/delivery.py` (DeliveryRouter) | `gateway/delivery.py` |
| `gateway/platforms/` (19 adapters) | TBD per platform |

**Platform adapters (preserved, but not active in MVP):**
- Telegram, Discord, WhatsApp, Slack, Signal
- Mattermost, Matrix, Email, SMS
- DingTalk, Feishu, WeCom, WeChat, QQ
- Home Assistant, BlueBubbles (iMessage)
- Webhook, API Server

**Butler approach:** Gateway is HTTP-first in the MVP path. Platform adapters are preserved as deferred/isolated channel integrations.

---

## Hermes Tools → Butler Adapters

Each Hermes tool becomes a Butler domain tool:

| Hermes Tool | Butler Tool | Status |
|-------------|-------------|--------|
| `terminal_tool.py` | `tools/terminal.py` | Imported |
| `file_tools.py` | `tools/files.py` | Imported |
| `web_tools.py` | `tools/web.py` | Imported |
| `browser_tool.py` | `tools/browser_tool.py` | Imported |
| `code_execution_tool.py` | `tools/code_execution.py` | Imported |
| `delegate_tool.py` | `tools/delegate_tool.py` | Imported |
| `mcp_tool.py` | `tools/mcp_tool.py` | Imported |

**Tool registration pattern:**
```python
# Hermes
from tools.registry import registry
registry.register(name="tool_name", schema={...}, handler=fn)

# Butler
from backend.integrations.hermes.tools.registry import hermes_registry
hermes_registry.register(name="tool_name", schema={...}, handler=fn)
```

---

## Hermes CLI → Preserved but Isolated

Hermes CLI features are preserved in the import layer but should not define Butler product behavior:
- Interactive REPL with Rich/prompt_toolkit
- Banner/panel presentation
- KawaiiSpinner animations
- Slash command autocomplete
- Skin/theme system
- Profile management (multi-instance)

**Rationale:** Butler is an assistant runtime with an API-first MVP slice. CLI/operator assets are compatibility surfaces, not core product behavior.

---

## Hermes Skills → Butler Skills

| Hermes | Butler |
|--------|--------|
| `skills/` directory | `integrations/hermes/skills/` |
| Skill scan/load | `HermesSkillsCatalog` |
| Skill invocation | Via orchestrator |

**Imported examples now present:**
- `productivity/powerpoint` - Office automation
- `productivity/google-workspace` - GWS integration
- `research/arxiv` - Academic search
- `media/youtube-content` - YouTube transcripts

---

## Hermes Cron → Butler Scheduler

| Hermes | Butler |
|--------|--------|
| `cron/scheduler.py` | `cron/scheduler.py` |
| `cron/jobs.py` | `cron/jobs.py` |

**Butler wrapper:** `backend/domain/automation/scheduler.py` wraps HermesCronJobs

---

## Integration Layer Rules

1. **All Hermes-derived code stays in `backend/integrations/hermes/`**
2. **Domain modules use Butler adapters, not raw Hermes**
3. **No CLI/TUI behavior ships as Butler product**
4. **Butler docs override Hermes when behavior differs**

---

## Usage Examples

```python
# ✅ CORRECT - use Butler adapter
from backend.integrations.hermes.agent.runtime import HermesAIAgentRuntime
from backend.domain.orchestrator.runtime_adapter import ButlerRuntimeAdapter

# ✅ CORRECT - use Butler wrapper
from backend.domain.memory.session_store import ButlerSessionStore
from backend.domain.tools.registry import ButlerToolRegistry
from backend.domain.automation.scheduler import ButlerScheduler

# ❌ WRONG - tight coupling
from hermes_agent.run_agent import AIAgent
```

---

## Current Next Steps

1. Rebrand Hermes-specific naming and runtime identity where Butler-facing code sees it
2. Consolidate duplicate/renamed import files into canonical Butler filenames
3. Strengthen Butler-owned wrappers around runtime, tools, and session persistence
4. Mark active vs deferred vs isolated areas clearly in code-facing docs
5. Wire only the documented MVP path first: Gateway → Auth → Orchestrator → Memory → Tools

---

## Note

This file is intentionally narrower than the main assimilation map. For decisions about
what is active now, what is deferred, and what must be isolated, use:

- `docs/system/hermes-assimilation-map.md`
- `docs/product/mvp-services.md`
- `docs/dev/backend-architecture.md`
