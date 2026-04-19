# Butler Hermes Integration Layer

This directory is Butler's **imported capability boundary** for Hermes-derived code.

It exists so Butler can preserve useful Hermes runtime, tools, gateway adapters,
plugins, skills, and scheduler code **without** letting imported structure define
Butler's product identity or service architecture.

## Role in Butler

Per Butler docs, the active MVP path is:

`Gateway -> Auth -> Orchestrator -> Memory -> Tools`

So this integration layer should be read in three buckets:

1. **Active MVP support**
   - runtime helpers for orchestrator
   - imported tool registry + safe execution helpers
   - imported session/history helpers
2. **Deferred but preserved capability**
   - advanced tools, browser/code-execution/MCP surfaces
   - skills and optional-skills
   - plugin backends and memory plugins
   - scheduler/automation helpers
3. **Isolated compatibility surfaces**
   - CLI/TUI artifacts
   - ACP/editor integration
   - gateway platform adapters

The integration layer is therefore **not** Butler core. It is Butler-owned
compatibility inventory consumed through Butler-owned domain wrappers.

## Layout

```
backend/integrations/hermes/
├── __init__.py       # Root package
├── agent/             # Butler runtime modules
├── core/              # Hermes constants, utils, time
├── gateway/           # Hermes gateway patterns
├── tools/             # Hermes tool registry system
├── cron/              # Hermes scheduler patterns
├── plugins/           # Hermes plugin adapters
└── skills/            # Hermes skills/capabilities
```

## Non-Negotiables

1. **Hermes-derived code stays here** - imported code belongs under `backend/integrations/hermes/`
2. **Butler owns the boundaries** - `backend/domain/*` and `backend/api/*` must not couple directly to raw Hermes entrypoints
3. **No chatbot-shaped collapse** - imported runtime code must not redefine Butler as a generic CLI/chat loop
4. **No CLI/TUI product leakage** - Hermes CLI/TUI behavior is not exposed as Butler product behavior
5. **Docs override imports** - Butler docs win when Hermes assumptions conflict with Butler architecture or product direction

## Active Consumption Pattern

When Butler needs imported capability, it should go through Butler-owned wrappers:

```python
# WRONG - raw foreign entrypoint
from backend.integrations.hermes.run_agent import AIAgent

# BETTER - Butler domain wrapper owns the contract
from backend.domain.orchestrator.runtime_adapter import ButlerRuntimeAdapter
from backend.domain.tools.registry import ButlerToolRegistry
from backend.domain.memory.session_store import ButlerSessionStore
```

## Current Assimilation Status

### Active now

- imported runtime helpers behind Butler orchestrator wrapper
- imported tool registry and starter tool execution helpers
- imported session/history helpers behind Butler memory wrapper

### Deferred but kept

- skills and optional-skills
- memory plugins
- advanced browser / MCP / code-execution surfaces
- scheduler / automation helpers beyond the MVP loop

### Isolated

- `gateway/platforms/*`
- `acp_adapter/*`
- CLI/operator surfaces like `cli.py`, `agent/display.py`, `agent/skill_commands.py`

## Imported Sources

This layer was populated from sources including:
- `.ref/butler-agent/run_agent.py`
- `.ref/butler-agent/agent/`
- `.ref/butler-agent/model_tools.py`
- `.ref/butler-agent/hermes_state.py`
- `.ref/butler-agent/hermes_constants.py`
- `.ref/butler-agent/utils.py`
- `.ref/butler-agent/cron/`
- `.ref/butler-agent/tools/`
- `.ref/butler-agent/plugins/`
- `.ref/butler-agent/skills/`

## Important Companion Docs

- `docs/system/hermes-assimilation-map.md` - current Butler assimilation strategy
- `docs/dev/backend-architecture.md` - Butler modular monolith boundaries
- `docs/product/mvp-services.md` - Butler active MVP service path
- `docs/agent/agent-loop.md` - Butler runtime behavior and state machine
