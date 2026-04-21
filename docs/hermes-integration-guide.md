# Butler Hermes Tools Integration Guide

> **Purpose:** How Butler uses Hermes tools and how to add new ones  
> **Created:** 2026-04-20

---

## Overview

Butler uses Hermes tools through a **Butler-owned abstraction layer**:

```
┌─────────────────────────────────────────────────────────────┐
│                    BUTLER ORCHESTRATOR                     │
└─────────────────────┬─────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              ToolExecutor (services/tools/)                  │
│  - Audit trail (PostgreSQL)                                │
│  - Idempotency check (Redis)                              │
│  - Parameter validation (jsonschema)                        │
│  - Risk tier evaluation                                    │
└─────────────────────┬─────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│         ButlerToolDispatch (domain/tools/)                  │
│  - Policy gate (ToolCapabilityGate)                        │
│  - Approval workflow                                       │
│  - Execution routing                                       │
└─────────────────────┬─────────────────────────────────────┘
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
┌─────────────────────┐   ┌─────────────────────────────┐
│   HermesEnvBridge   │   │     MCP Bridge             │
│ (Native execution)  │   │ (External MCP servers)     │
└─────────────────────┘   └─────────────────────────────┘
          │                       │
          ▼                       ▼
┌─────────────────────────────────────────────────────────────┐
│         Hermes Tools (integrations/hermes/tools/)          │
│  web.py, browser_tool.py, delegate_tool.py, etc.           │
└─────────────────────────────────────────────────────────────┘
```

---

## Current Hermes Tools Available

### Ready to Use

| Tool | File | Purpose | Status |
|------|------|---------|--------|
| **Web Search** | `hermes/tools/web.py` | Search the web | ✅ Wired |
| **Browser** | `hermes/tools/browser_tool.py` | Computer use/automation | ✅ Wired |
| **Delegate** | `hermes/tools/delegate_tool.py` | Subagent delegation | ✅ Wired |
| **Session Search** | `hermes/tools/session_search_tool.py` | Memory retrieval | ✅ Wired |
| **MCP** | `hermes/tools/mcp_tool.py` | MCP tool calls | ✅ Wired |
| **Vision** | `hermes/tools/vision_tools.py` | Image understanding | ✅ Wired |
| **TTS** | `hermes/tools/tts_tool.py` | Text to speech | ✅ Wired |
| **Image Gen** | `hermes/tools/image_generation_tool.py` | Create images | ✅ Wired |
| **Send Message** | `hermes/tools/send_message_tool.py` | Send messages | ✅ Wired |

### Browser Providers

| Provider | File | Purpose |
|----------|------|---------|
| BrowserUse | `browser_providers/browser_use.py` | AI browser automation |
| Firecrawl | `browser_providers/firecrawl.py` | Web scraping |
| BrowserBase | `browser_providers/browserbase.py` | Browser infrastructure |
| Camofox | `browser_providers/camofox.py` | Stealth browsing |

---

## How Tools Are Registered

### 1. Tool Spec Compilation

Tools are compiled into `ButlerToolSpec` at startup:

```python
# services/tools/hermes_compiler.py
from domain.tools.hermes_compiler import HermesToolCompiler

compiler = HermesToolCompiler()
compiled_specs = compiler.compile_tools(
    tool_modules=[
        "hermes.tools.web",
        "hermes.tools.browser_tool", 
        "hermes.tools.delegate_tool",
        # Add new tools here
    ]
)
```

### 2. Tool Spec Structure

Each tool becomes a `ButlerToolSpec`:

```python
@dataclass
class ButlerToolSpec:
    name: str                           # "web_search"
    description: str                     # "Search the web for information"
    input_schema: dict                  # JSON Schema for params
    handler: Callable                  # The actual function
    risk_tier: RiskTier               # T1_low, T2_medium, T3_high
    requires_approval: bool           # Need human approval?
    timeout_s: int                    # Max execution time
    category: ToolCategory            # search, communication, etc.
```

### 3. Tool Dispatch

When a tool is called:

```python
# services/tools/executor.py
result = await executor.execute(
    tool_name="web_search",
    params={"query": "weather in Bangalore"},
    account_id="user_123"
)
```

---

## How to Add a New Hermes Tool

### Step 1: Create the Tool (in Hermes)

```python
# integrations/hermes/tools/my_new_tool.py
"""My new capability tool."""

import httpx
from typing import Any

async def my_new_tool(params: dict, env: dict) -> dict:
    """Do something useful.
    
    Args:
        params: Tool parameters from caller
        env: Environment variables
    
    Returns:
        Dict with 'content' key for result
    """
    query = params.get("query")
    
    # Your implementation
    result = await fetch_something(query)
    
    return {
        "content": [
            {"type": "text", "text": result}
        ]
    }

# Required metadata for Butler
TOOL_METADATA = {
    "name": "my_new_tool",
    "description": "Does something useful",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to search for"}
        },
        "required": ["query"]
    }
}
```

### Step 2: Register in Tool Compiler

```python
# services/tools/hermes_compiler.py - add to TOOL_REGISTRY

TOOL_REGISTRY = {
    # ... existing tools ...
    "my_new_tool": {
        "module": "hermes.tools.my_new_tool",
        "handler": "my_new_tool",
        "metadata": "TOOL_METADATA",
        "risk_tier": "T2_medium",
        "requires_approval": False,
        "timeout_s": 30,
        "category": "utility"
    }
}
```

### Step 3: Configure Environment Variables

Add any required API keys:

```python
# infrastructure/config.py
MY_NEW_SERVICE_API_KEY: Optional[str] = None
```

### Step 4: Restart Butler

The tool compiler runs at startup and compiles all registered tools.

---

## Alternative: Add via MCP

Instead of native integration, add tools via MCP server:

```python
# services/tools/mcp_bridge.py
await mcp_bridge.register_remote_server(
    MCPServerConfig(
        server_id="my-service",
        name="My Service",
        transport="http",
        url="https://my-service.com/mcp",
        default_risk_tier="T2_medium"
    )
)
```

---

## How Tools Execute

### Execution Flow

```
1. User request → Orchestrator
2. Orchestrator → ToolExecutor.execute(tool_name, params)
3. ToolExecutor:
   a. Lookup ButlerToolSpec
   b. Check idempotency (Redis)
   c. Validate params (jsonschema)
   d. Pre-execution verification
   e. Write audit record (PostgreSQL)
4. ToolExecutor → ButlerToolDispatch
5. ButlerToolDispatch:
   a. Check policy (ToolCapabilityGate)
   b. Check approval requirement
   c. Route to HermesEnvBridge or MCP
6. HermesEnvBridge → Call handler function
7. Return result → ToolExecutor
8. ToolExecutor:
   a. Post-execution verification
   b. Commit audit record
   c. Cache result
9. Return ToolResult to Orchestrator
```

---

## Key Files

| File | Purpose |
|------|---------|
| `services/tools/executor.py` | Main tool execution |
| `services/tools/hermes_compiler.py` | Compile Hermes tools to ButlerToolSpec |
| `services/tools/hermes_dispatcher.py` | ButlerToolDispatch |
| `domain/tools/hermes_compiler.py` | ButlerToolSpec dataclass |
| `domain/tools/contracts.py` | ToolResult, ValidationResult |
| `integrations/hermes/tools/` | Actual Hermes tool implementations |

---

## Available Environment in Tools

Tools receive an `env` dict with:

```python
env = {
    # Butler context
    "account_id": "user_123",
    "session_id": "sess_abc",
    "user_id": "u123",
    
    # Services
    "redis_url": "redis://...",
    "database_url": "postgresql://...",
    "neo4j_uri": "bolt://...",
    
    # Config
    "openai_api_key": "sk-...",
    "anthropic_api_key": "sk-ant-...",
    
    # Custom
    "HOME_ASSISTANT_URL": "http://homeassistant:8123",
    # ... any configured env vars
}
```

---

## Risk Tiers

| Tier | Description | Requires Approval |
|------|-------------|-----------------|
| T1_low | Safe, read-only | No |
| T2_medium | May have side effects | Sometimes |
| T3_high | Potentially dangerous | Yes |
| T4_critical | System modification | Always |

---

## Testing Tools

```python
# Test locally
from services.tools.executor import ToolExecutor
from services.tools.hermes_compiler import HermesToolCompiler

# Compile tools
compiler = HermesToolCompiler()
specs = compiler.compile_tools()

# Execute
executor = ToolExecutor(db=session, redis=redis, compiled_specs=specs)
result = await executor.execute(
    tool_name="web_search",
    params={"query": "test"},
    account_id="test"
)
print(result)
```

---

## Summary

**Butler already has Hermes tools integrated via:**
1. `ToolExecutor` → `ButlerToolDispatch` → `HermesEnvBridge`
2. Tool specs compiled at startup via `HermesToolCompiler`
3. MCP bridge for external tool servers

**To use a Hermes tool:**
```python
# Just call it by name
result = await executor.execute(
    tool_name="web_search",  # Uses hermes/tools/web.py
    params={"query": "..."},
    account_id="..."
)
```

**To add a new tool:**
1. Create tool in `integrations/hermes/tools/`
2. Register in `HermesToolCompiler.TOOL_REGISTRY`
3. Add config to `infrastructure/config.py`
4. Restart

*No manual wiring needed - the compilation system auto-registers.*

---

*Generated: 2026-04-20*