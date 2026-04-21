# Butler Native Tools, Skills & Plugins Guide

> **Purpose:** Create native Butler capabilities (not via Hermes)  
> **Created:** 2026-04-20

---

## Butler Capability Systems

Butler has **3 parallel systems** for capabilities:

| System | Purpose | How to Add |
|--------|----------|-----------|
| **Native Tools** | Direct execution (web search, code, etc.) | Register in ButlerToolRegistry |
| **Skills** | Composable capabilities (calendar, research) | Create skill package |
| **Plugins** | External integrations (MCP, trader's) | Create plugin package |

---

## System 1: Native Tools

Butler has its **own native tool registry** separate from Hermes.

### Tool Registry Architecture

```
┌─────────────────────────────────────────────────────────────┐
│            ButlerToolRegistry (domain/tools/)              │
│  - Maps tool name → CapabilityFlag                        │
│  - Discovers from Hermes via HermesRegistryAdapter          │
│  - Policy: domain/policy/ enforces capabilities           │
└─────────────────────────────────────────────────────────────┘
```

### CapabilityFlag Map

```python
# domain/tools/butler_tool_registry.py
_TOOLSET_CAPABILITY_MAP = {
    "web":                "WEB_SEARCH",
    "files":              "FILE_OPS",
    "terminal":           "TERMINAL",
    "browser":            "BROWSER_AUTOMATION",
    "code_execution":     "CODE_EXECUTION",
    "delegate":          "DELEGATE",
    "mcp":               "MCP_ACCESS",
    "vision":            "VISION",
    "voice":             "VOICE",
    "tts":               "VOICE",
    "image_gen":         "IMAGE_GENERATION",
    "memory":           "MEMORY_WRITE",
    "session_search":    "MEMORY_READ",
    "skills":            "SKILLS",
    "homeassistant":     "IOT_CONTROL",
    "cronjob":           "CRON_SCHEDULE",
    # Add your capability here
}
```

### How to Add a Native Tool

#### Step 1: Create the Tool Function

```python
# services/tools/native/my_tool.py
"""Native Butler tool - my capability."""

import httpx
import structlog
from typing import Any

logger = structlog.get_logger(__name__)

async def my_tool(params: dict, env: dict) -> dict:
    """Execute my capability.
    
    Args:
        params: Tool parameters
        env: Environment (API keys, services, etc.)
    
    Returns:
        Result dict with content
    """
    query = params.get("query")
    
    # Your implementation
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.example.com/search",
            params={"q": query},
            headers={"Authorization": f"Bearer {env.get('MY_API_KEY')}"}
        )
    
    return {
        "content": [{"type": "text", "text": response.text}]
    }

# Tool metadata
TOOL_DEFINITION = {
    "name": "my_capability",
    "description": "Does something useful",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"}
        },
        "required": ["query"]
    }
}
```

#### Step 2: Register in Tool Registry

```python
# services/tools/native/__init__.py or add to startup

# Option A: Add to HermesRegistryAdapter (if using Hermes)
# Option B: Create native-only registry

from domain.tools.butler_tool_registry import BUTLER_NATIVE_TOOLS

BUTLER_NATIVE_TOOLS = {
    "my_capability": {
        "handler": "services.tools.native.my_tool.my_tool",
        "definition": "TOOL_DEFINITION",
        "capability_flag": "MY_CAPABILITY",  # Must match policy
        "risk_tier": "T2_medium",
        "requires_approval": False,
        "timeout_s": 30,
    }
}
```

#### Step 3: Add Capability Flag (if new)

```python
# domain/policy/capability_flags.py

class CapabilityFlag(str, enum.Enum):
    """Butler capability gates."""
    # ... existing ...
    MY_CAPABILITY = "my_capability"
```

---

## System 2: Skills

Skills are **composable capabilities** that combine tools, prompts, and logic.

### Skill Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              Skill Marketplace (services/tools/)            │
│  - Skill registry with versions                            │
│  - Capability discovery                                  │
│  - Policy-gated execution                                │
│  - MCP compatibility                                      │
└─────────────────────────────────────────────────────────────┘
```

### Skill Models

```python
# domain/skills/models.py

class SkillType(str, Enum):
    NATIVE = "native"      # Butler native Python skill
    MCP = "mcp"          # Model Context Protocol server
    EXTERNAL = "external" # External HTTP skill
    COMPOSITE = "composite" # Composite of multiple skills

class CapabilityType(str, Enum):
    TOOL = "tool"
    PROMPT = "prompt"
    AGENT = "agent"
    COMPOSITE = "composite"
```

### How to Create a Skill

#### Step 1: Create Skill Package

```python
# services/skills/my_skill/__init__.py
"""My Butler Skill."""

from typing import Any, Dict
from pydantic import BaseModel, Field

class MySkillInput(BaseModel):
    query: str = Field(description="Input query")

class MySkillOutput(BaseModel):
    result: str
    confidence: float

class MySkill:
    """My capability skill."""
    
    skill_type = "native"  # MCP, external, composite
    version = "1.0.0"
    
    async def execute(self, input: MySkillInput, context: Dict[str, Any]) -> MySkillOutput:
        """Execute the skill.
        
        Args:
            input: Validated input
            context: Execution context (env, services, etc.)
        """
        # Your implementation
        result = await self._do_something(input.query, context)
        
        return MySkillOutput(
            result=result,
            confidence=0.95
        )
    
    async def _do_something(self, query: str, context: Dict) -> str:
        # Implementation
        pass
    
    @classmethod
    def get_manifest(cls) -> dict:
        """Return skill manifest for registry."""
        return {
            "name": "my_skill",
            "version": cls.version,
            "type": cls.skill_type,
            "description": "Does something useful",
            "input_schema": MySkillInput.model_json_schema(),
            "capabilities": ["MY_CAPABILITY"]
        }
```

#### Step 2: Create Skill Manifest

```json
// services/skills/my_skill/skill.json
{
  "name": "my_skill",
  "version": "1.0.0",
  "description": "Does something useful for users",
  "type": "native",
  "category": "productivity",
  "tags": ["search", "api", "utility"],
  "permissions": ["network:outbound"],
  "input_schema": {},
  "capabilities": ["MY_CAPABILITY"],
  "risk_tier": 2,
  "requires_approval": false,
  "environment": {
    "required": ["MY_API_KEY"],
    "optional": []
  }
}
```

#### Step 3: Register Skill

```python
# services/tools/skill_marketplace.py

from services.skills.my_skill import MySkill

# Register at startup
skill_registry.register(
    manifest=MySkill.get_manifest(),
    handler=MySkill
)
```

---

## System 3: Plugins

Plugins are **external integrations** with lifecycle management.

### Plugin Models

```python
# domain/skills/models.py

class PluginPackage(Base):
    """External plugin/skill package."""
    id: UUID
    package_id: str  # e.g. "clawhub:anthropic-provider"
    name: str
    publisher: str
    current_version: str
    state: PackageState  # STAGED, ACTIVE, PREVIOUS, FAILED, RETIRED
    risk_tier: RiskTier  # TIER_0 through TIER_3
    
class PluginVersion(Base):
    """Versioned plugin."""
    version: str
    manifest: dict  # Serialized plugin.json
    archive_hash: str  # SHA256
    signature: str  # ED25519

class SecurityAuditLog(Base):
    """Immutable audit trail."""
    action: str  # "install", "promote", "rollback"
    gate_results: dict  # Gate A/B/C/D results
    status: str  # "success", "failed"
```

### How to Add a Plugin

#### Step 1: Create Plugin Package

```python
# services/plugins/my_plugin/__init__.py
"""My Butler Plugin."""

from typing import Any, Dict, List
from pydantic import BaseModel

class MyPluginConfig(BaseModel):
    api_key: str
    mode: str = "production"

class MyPlugin:
    """My external service plugin."""
    
    PLUGIN_ID = "myorg:my-plugin"
    VERSION = "1.0.0"
    
    def __init__(self, config: MyPluginConfig):
        self.config = config
    
    async def initialize(self) -> None:
        """Initialize plugin."""
        pass
    
    async def call(self, method: str, params: dict) -> dict:
        """Call plugin method."""
        pass
    
    async def health_check(self) -> bool:
        """Check plugin health."""
        return True
    
    @classmethod
    def get_manifest(cls) -> dict:
        return {
            "id": cls.PLUGIN_ID,
            "name": "My Plugin",
            "version": cls.VERSION,
            "description": "Integration with my service",
            "methods": ["call", "health_check"],
            "permissions": ["network:outbound"],
            "risk_tier": 2
        }
```

#### Step 2: Create plugin.json

```json
// services/plugins/my_plugin/plugin.json
{
  "id": "myorg:my-plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "description": "Integration with My Service",
  "publisher": "myorg",
  "methods": [
    {"name": "call", "description": "Call my API"},
    {"name": "health_check", "description": "Check service health"}
  ],
  "permissions": ["network:outbound"],
  "risk_tier": "TIER_2",
  "capabilities": ["MY_API_INTEGRATION"],
  "config_schema": {
    "api_key": {"type": "string", "required": true},
    "mode": {"type": "string", "default": "production"}
  }
}
```

#### Step 3: Install via Plugin Ops

```python
# services/plugin_ops/

from services.plugin_ops.registry_service import PluginRegistry

registry = PluginRegistry()
await registry.install(
    package_id="myorg:my-plugin",
    version="1.0.0",
    source_url="https://plugins.myorg.com/my-plugin.tar.gz"
)
```

---

## Comparison: When to Use What

| Use Case | System | Example |
|---------|--------|----------|
| Simple function call | **Native Tool** | "Search web", "Run code" |
| Multi-step with prompts | **Skill** | "Research topic", "Write document" |
| External service | **Plugin** | "Slack", "GitHub", "Database" |
| MCP server integration | **Plugin** | "filesystem", "browser" |

---

## Quick Reference: Add Capability

### Add a Simple Tool (5 min)

```python
# 1. Create tool
# services/tools/native/my_tool.py

async def my_tool(params, env):
    return {"content": [{"type": "text", "text": "result"}]}

# 2. Register
# domain/tools/butler_tool_registry.py
_TOOLSET_CAPABILITY_MAP["my_tool"] = "MY_CAPABILITY"

# 3. Done - auto-discovered!
```

### Add a Skill (30 min)

```python
# 1. Create skill package
# services/skills/my_skill/__init__.py
# services/skills/my_skill/skill.json

# 2. Register in marketplace
# services/tools/skill_marketplace.py
registry.register_skill(MySkill)

# 3. Available via skill marketplace
```

### Add a Plugin (1 hour)

```python
# 1. Create plugin package
# services/plugins/my_plugin/__init__.py
# services/plugins/my_plugin/plugin.json

# 2. Install
# services/plugin_ops/registry_service.py
await registry.install_from_url(url)

# 3. Lifecycle managed with audit
```

---

## Files to Modify

| What | File |
|------|------|
| Add capability flag | `domain/policy/capability_flags.py` |
| Add tool | `services/tools/native/my_tool.py` |
| Register tool | `domain/tools/butler_tool_registry.py` |
| Add skill | `services/skills/my_skill/` |
| Register skill | `services/tools/skill_marketplace.py` |
| Add plugin | `services/plugins/my_plugin/` |
| Install plugin | `services/plugin_ops/registry_service.py` |

---

*Generated: 2026-04-20*