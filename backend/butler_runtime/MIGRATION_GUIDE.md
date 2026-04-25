# Butler × Hermes Unified Runtime - Migration Guide

This guide documents the migration from Hermes-as-plugin to Butler's unified runtime.

## Overview

Hermes has been fully integrated into Butler as an internal runtime layer. The old Hermes-as-plugin architecture is deprecated.

## What Changed

### New Unified Runtime Location
- **Old:** `backend/integrations/hermes/` (external plugin)
- **New:** `backend/butler_runtime/` (internal runtime)

### Key Components

**Agent Runtime:**
- `butler_runtime/agent/loop.py` - ButlerUnifiedAgentLoop
- `butler_runtime/agent/budget.py` - ExecutionBudget
- `butler_runtime/agent/tool_calling.py` - Tool calling orchestration
- `butler_runtime/agent/message_builder.py` - Message construction
- `butler_runtime/agent/callbacks.py` - Event streaming callbacks

**Tool Registry:**
- `butler_runtime/tools/registry.py` - UnifiedToolRegistry
- `butler_runtime/hermes/execution/tool_schema_converter.py` - Schema conversion
- `butler_runtime/hermes/execution/function_call_handler.py` - Function call handling

**Butler-Hermes Tools:**
- `butler_runtime/hermes/tools/file.py` - File operations
- `butler_runtime/hermes/tools/web.py` - Web operations
- `butler_runtime/hermes/tools/utility.py` - Utility tools
- `butler_runtime/hermes/tools/memory.py` - Memory tools (calls Butler MemoryService)

**LangGraph Integration:**
- `butler_runtime/graph/state.py` - ButlerGraphState
- `butler_runtime/graph/compiler.py` - ButlerGraphCompiler

**Skills Manager:**
- `butler_runtime/skills/registry.py` - ButlerSkillsRegistry
- `butler_runtime/skills/manager.py` - ButlerSkillsManager

**Channels Adapter:**
- `butler_runtime/channels/adapter.py` - ButlerHermesGatewayAdapter
- `butler_runtime/channels/platform_registry.py` - HermesPlatformRegistry

**LangChain Interface:**
- `butler_runtime/langchain/agent.py` - ButlerLangChainAgent
- `butler_runtime/langchain/tools.py` - ButlerLangChainTools

## Configuration Changes

### Removed Configuration
- `HERMES_HOME` - No longer needed (Hermes is internal)
- `HERMES_AGENT_ENABLED` - No longer needed
- `HERMES_TOOLS_ENABLED` - No longer needed
- `HERMES_BROWSER_ENABLED` - No longer needed
- `HERMES_SKILLS_ENABLED` - No longer needed
- `HERMES_PLATFORM_ADAPTERS_ENABLED` - No longer needed
- `HERMES_CRON_ENABLED` - No longer needed
- `HERMES_MEMORY_PLUGINS_ENABLED` - No longer needed
- `get_hermes_env()` function - No longer needed

### Butler Configuration
All configuration is now unified under Butler's `Settings` class in `backend/infrastructure/config.py`.

## Deprecated Files

The following files are deprecated and should be removed after migration:

### Hermes Agent Backend
- `backend/domain/orchestrator/hermes_agent_backend.py` - DEPRECATED (marked with deprecation notice)
- `backend/domain/orchestrator/hermes_api_client.py` - DEPRECATED

### Hermes CLI/TUI
- `backend/integrations/hermes/hermes_cli/` - DEPRECATED (CLI no longer needed in production)
- `backend/integrations/hermes/tui_gateway/` - DEPRECATED (TUI no longer needed in production)

### Hermes Gateway (Old)
- `backend/integrations/hermes/gateway/` - Use Butler channels instead
- `backend/integrations/hermes/tools/managed_tool_gateway.py` - Use Butler channels instead

### Hermes Tools (Old)
- `backend/integrations/hermes/tools/` - Use `butler_runtime/hermes/tools/` instead

### Hermes Tests (Old)
- `backend/integrations/hermes/tests/` - Use `butler_runtime/tests/` instead

## Migration Steps

### 1. Update Imports

**Old:**
```python
from domain.orchestrator.hermes_agent_backend import HermesAgentBackend
```

**New:**
```python
from butler_runtime.agent.loop import ButlerUnifiedAgentLoop
from butler_runtime.tools.registry import UnifiedToolRegistry
```

### 2. Update Configuration

Remove any references to `HERMES_HOME`, `HERMES_*_ENABLED`, or `get_hermes_env()`.

### 3. Update Tool Registration

**Old:**
```python
from langchain.hermes_registry import ButlerHermesRegistry
```

**New:**
```python
from butler_runtime.tools.registry import UnifiedToolRegistry
registry = UnifiedToolRegistry()
```

### 4. Update Memory Operations

**Old:**
```python
from integrations.herms.memory import HermesMemory
```

**New:**
```python
from butler_runtime.hermes.tools.memory import ButlerMemoryTools
# Or directly use Butler MemoryService
from services.memory.service import MemoryService
```

### 5. Update Agent Execution

**Old:**
```python
backend = HermesAgentBackend(...)
result = await backend.run(ctx)
```

**New:**
```python
from butler_runtime.agent.loop import ButlerUnifiedAgentLoop
from butler_runtime.graph.compiler import ButlerGraphCompiler

agent_loop = ButlerUnifiedAgentLoop(...)
result = await agent_loop.run(ctx)
```

## Cleanup Commands

After migration is complete, remove deprecated files:

```bash
# Remove deprecated Hermes agent backend
rm backend/domain/orchestrator/hermes_agent_backend.py
rm backend/domain/orchestrator/hermes_api_client.py

# Remove Hermes CLI/TUI (if not needed for development)
rm -rf backend/integrations/hermes/hermes_cli/
rm -rf backend/integrations/hermes/tui_gateway/

# Remove old Hermes gateway (use Butler channels instead)
rm -rf backend/integrations/hermes/gateway/

# Remove old Hermes tools (use butler_runtime instead)
rm -rf backend/integrations/hermes/tools/

# Remove old Hermes tests (use butler_runtime/tests instead)
rm -rf backend/integrations/hermes/tests/
```

**Note:** Keep `backend/integrations/hermes/skills/` if you need the skill manifests. The skills manager can load from this directory.

## Testing

Run the unified runtime tests:

```bash
cd backend
python -m pytest butler_runtime/tests/test_unified_runtime.py -v
```

## Rollback

If you need to rollback, restore the deprecated files from git:

```bash
git checkout HEAD -- backend/domain/orchestrator/hermes_agent_backend.py
git checkout HEAD -- backend/domain/orchestrator/hermes_api_client.py
git checkout HEAD -- backend/integrations/hermes/
```

## Support

For issues or questions about the migration, refer to:
- `backend/butler_runtime/HERMES_MERGE_MAP.md` - Detailed merge strategy
- `backend/butler_runtime/agent/loop.py` - Unified agent loop implementation
- `backend/butler_runtime/tools/registry.py` - Tool registry implementation
