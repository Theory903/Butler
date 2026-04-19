# Plugin System Specification

> **For:** Engineering  
> **Status:** Production Required  
> **Version:** 2.0

---

## v2.0 Changes

- Complete rewrite per Oracle architectural review
- Split into 4 plugin runtime types
- MCP-first extension surface
- Policy-gated execution
- Manifest-driven (no SKILL.md)
- Supply-chain security requirements
- WASM sandbox for code plugins

---

## 1. Plugin Architecture Overview

### 1.1 Butler Extension Model

**NOT raw code upload.** Butler plugins are capability packages, not uploaded Python files.

```
┌─────────────────────────────────────────────────────────────┐
│              BUTLER EXTENSION SYSTEM                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  4 Runtime Types:                                           │
│  ├─ manifest-only: Metadata, schemas, config                 │
│  ├─ MCP adapter: External MCP server → Butler tool          │
│  ├─ remote service: Butler wrapper around external API    │
│  └─ WASM sandbox: Extism-based sandboxed execution       │
│                                                              │
│  Execution:                                               │
│  Request → Schema validation → Policy check → Execution   │
│                                                              │
│  Supply Chain:                                             │
│  Package install → Manifest verify → Policy eval →   │
│  Register → Capability exposure                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Plugin Package Structure

**NOT this:**
```
plugins/
├── SKILL.md
├── tool.py
├── service.py
└── static/
```

**THIS:**
```
butler-plugin/
├── plugin.yaml           # REQUIRED: machine-readable manifest
├── README.md
├── schemas/
│   ├── tools.json
│   ├── config.schema.json
│   └── outputs.schema.json
├── mcp/
│   └── server.json       # OPTIONAL: MCP bridge
├── wasm/
│   └── plugin.wasm      # OPTIONAL: WASM binary
├── web/
│   └── admin-card.json   # OPTIONAL: admin UI
├── provenance/
│   ├── checksums.txt
│   ├── signature.sig
│   └── provenance.json
└── assets/
```

---

## 2. Manifest Specification

### 2.1 plugin.yaml (REQUIRED)

```yaml
plugin_id: "butler-weather"
name: "weather"
version: "1.2.0"
publisher: "butler-team"
homepage: "https://github.com/butlerai/weather-plugin"
source_repo: "https://github.com/butlerai/weather-plugin"
license: "MIT"

# Runtime type
runtime_type: "mcp"  # manifest-only | mcp | remote | wasm

# Capabilities
capabilities:
  - type: "tool"
    name: "get_weather"
    description: "Get weather for location"
    input_schema: "./schemas/weather-input.json"
    output_schema: "./schemas/weather-output.json"
    risk_tier: "low"

# Required permissions
required_permissions:
  - "http:requests:external"
  - "network:outbound"

# Auth mode (how Butler obtains credentials)
auth_mode: "user-provided"  # user-provided | oauth | api-key | none

# Network policy
network_policy:
  allowlist:
    - "api.weather.com"
    - "*.weather.com"

# Data classes touched
data_classes:
  - "location"

# Approval policy
approval_policy:
  requires_approval: false

# Compatibility
compatibility:
  butler_version: ">=2.0.0"
  min_api_version: "2025-01"

# Signature/provenance refs
signature:
  algorithm: "RSA-SHA256"
  key_id: "butler-team-key-001"
```

---

## 3. Plugin Runtime Types

### 3.1 Manifest-Only Plugins

No code execution. Just capability declarations, schemas, config.

**Use for:**
- Native Butler capabilities
- UI cards
- Documentation
- Configuration

```yaml
runtime_type: "manifest-only"
capabilities:
  - type: "tool"
    name: "builtin_search"
    description: "Search Butler knowledge base"
  - type: "ui_card"
    name: "weather_dashboard"
    template: "./web/card.json"
```

### 3.2 MCP Adapter Plugins (DEFAULT)

MCP is the **default** extension surface for Butler.

**Why MCP:**
- Already schema-first
- Named, versioned tools
- Lifecycle management built-in
- Capability negotiation
- Transport-neutral

**Use for:**
- External tool integrations
- API wrappers
- Community plugins

```python
# MCP server that Butler wraps
class Weather MCPAdapter:
    """
    Wraps external MCP server as Butler capability.
    Butler owns the wrapper, not the tool implementation.
    """
    
    TOOL_SPEC = {
        "name": "weather-mcp",
        "description": "Weather via MCP",
        "mcp_server": "external-mcp://weather",
        "capabilities": ["tools", "resources"],
        "auth": {
            "mode": "api-key",
            "location": "header:X-API-Key"
        }
    }
    
    async def register(self, registry: PluginRegistry):
        """Register MCP tools as Butler tools"""
        
        # Negotiate capabilities
        tools = await self.mcp_client.list_tools()
        
        for tool in tools:
            # Wrap MCP tool as Butler tool
            await registry.register(
                Tool(
                    name=f"weather.{tool.name}",
                    input_schema=tool.inputSchema,
                    output_schema=tool.outputSchema,
                    execute=self.wrap_execution(tool),
                    policy=self.default_policy
                )
            )
```

### 3.3 Remote Service Plugins

Plugin is a Butler-owned manifest + auth wrapper around external service.

**Use for:**
- External APIs (not MCP-compatible)
- Third-party services
- Legacy integrations

```python
class RemoteServicePlugin:
    """
    Butler-owned wrapper around external service.
    External service is NOT code running in Butler.
    """
    
    REMOTE_SPEC = {
        "name": "slack",
        "base_url": "https://slack.com/api",
        "auth": {
            "type": "oauth",
            "scopes": ["chat:write", "channels:read"]
        },
        "endpoints": {
            "message": "/chat.postMessage",
            "channels": "/conversations.list"
        }
    }
    
    async def execute(self, endpoint: str, params: dict) -> dict:
        """Execute via Butler-owned HTTP wrapper"""
        
        # Credentials from Butler secret store
        credentials = await self.get_credentials()
        
        # Execute via Butler (not direct from plugin)
        response = await self.http.post(
            f"{self.base_url}{endpoint}",
            headers={"Authorization": f"Bearer {credentials.token}"},
            json=params
        )
        
        return response.json()
```

### 3.4 WASM Sandbox Plugins

**RARE.** Only when Butler truly needs custom execution logic.

**Use for:**
- Custom ML processing
- Specialized computation
- Performance-critical logic

**NOT for:**
- Basic API wrappers
- Standard tools

```python
class WASMPlugin:
    """
    Extism-based sandboxed execution.
    Third-party code runs in WASM, never in-process.
    """
    
    WASM_SPEC = {
        "name": "custom-sentiment",
        "runtime": "extism",
        "memory_limit": "64MB",
        "compile_timeout": "10s",
        "execution_timeout": "5s",
        "allowed_imports": ["http_request", "json_parse"]
    }
    
    async def initialize(self):
        """Load WASM into sandbox"""
        
        self.runtime = Extismruntime(
            wasm=self.plugin_wasm_path,
            memory_limit=self.WASM_SPEC["memory_limit"],
            timeout=self.WASM_SPEC["execute_timeout"]
        )
        
        # Verify allowed imports
        for import_fn in self.runtime.imports:
            if import_fn not in self.WASM_SPEC["allowed_imports"]:
                raise PluginSecurityError(
                    f"Unauthorized import: {import_fn}"
                )
```

---

## 4. Execution Pipeline

### 4.1 Tool Execution Flow

```
┌─────────────────────────────────────────────────────────────┐
│              TOOL EXECUTION PIPELINE                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. REQUEST                                                 │
│     ↓                                                       │
│  2. SCHEMA VALIDATION                                      │
│     ├─ Input schema check                                    │
│     ├─ Required fields check                                │
│     └─ Type validation                                     │
│     ↓                                                       │
│  3. POLICY CHECK (OPA)                                      │
│     ├─ Plugin identity                                    │
│     ├─ Trust tier                                         │
│     ├─ Requested permissions                               │
│     ├─ User permissions                                   │
│     ├─ Tenant policy                                      │
│     ├─ Channel/device limits                               │
│     └─ Approval state                                    │
│     ↓                                                       │
│  4. CREDENTIAL RESOLUTION                                   │
│     ├─ Fetch from vault                                    │
│     ├─ Validate expiry                                    │
│     └─ Inject into context                                │
│     ↓                                                       │
│  5. EXECUTION                                             │
│     ├─ manifest-only: Error                               │
│     ├─ mcp: MCP call → Butler result                       │
│     ├─ remote: HTTP call via Butler wrapper             │
│     └─ wasm: Extism sandbox execution                     │
│     ↓                                                       │
│  6. OUTPUT VALIDATION                                      │
│     ├─ Schema check                                       │
│     ├- Dangerous pattern scan                           │
│     └─ Sensitive data redaction                         │
│     ↓                                                       │
│  7. AUDIT + TELEMETRY                                      │
│     ├─ Log execution                                      │
│     ├- Emit metrics                                       │
│     └- Update SLO                                          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Policy Engine (OPA Integration)

Plugins go through policy decision point:

```python
class PluginPolicyEngine:
    """OPA-based policy evaluation"""
    
    async def evaluate(
        self,
        plugin: PluginManifest,
        tool_request: ToolRequest,
        context: ExecutionContext
    ) -> PolicyResult:
        """Evaluate plugin tool request"""
        
        input_data = {
            "plugin": {
                "id": plugin.plugin_id,
                "trust_tier": plugin.trust_tier,
                "runtime_type": plugin.runtime_type,
                "permissions": plugin.required_permissions
            },
            "tool": {
                "name": tool_request.name,
                "risk_tier": tool_request.risk_tier
            },
            "user": {
                "id": context.user_id,
                "tier": context.user_tier,
                "permissions": context.permissions
            },
            "request": {
                "channel": context.channel,
                "device": context.device_type,
                "time": context.timestamp
            },
            "approval": context.approval_state
        }
        
        result = await self.opa.evaluate(
            "plugin_execution",
            input_data
        )
        
        return PolicyResult(
            allow=result.allow,
            restrictions=result.restrictions,
            require_approval=result.require_approval
        )
```

### 4.3 Approval Policy

```python
APPROVAL_REQUIRED = {
    # Tool requires human approval
    "critical": ["all"],
    "high": ["payment", "device_control", "delete"],
    
    # Tool requires admin approval  
    "admin": ["user_management", "system_config"],
    
    # Tool logged for review
    "logged": ["send_message", "send_email"]
}
```

---

## 5. Lifecycle

### 5.1 Installation

```python
async def install_plugin(package_source: str):
    """
    Installation flow:
    1. Fetch package
    2. Verify signature/provenance
    3. Check compatibility
    4. Policy evaluation
    5. Register manifest only (NOT activate)
    """
    
    # 1. Fetch package (from registry, not arbitrary upload)
    package = await self.registry.fetch(package_source)
    
    # 2. Verify signature
    if not await self.verify_signature(package):
        raise PluginSecurityError("Signature invalid")
    
    # 3. Verify provenance
    if not await self.verify_provenance(package):
        raise PluginSecurityError("Provenance unverified")
    
    # 4. Check compatibility
    if not self.check_compatibility(package.compatibility):
        raise PluginCompatibilityError("Incompatible")
    
    # 5. Evaluate policy
    policy = await self.policy.evaluate_install(package)
    if not policy.allow:
        raise PluginPolicyError(f"Policy denied: {policy.reason}")
    
    # 6. Register manifest (NOT activate)
    await self.registry.register(package.manifest)
```

### 5.2 Activation

```python
async def activate_plugin(plugin_id: str):
    """Activation flow"""
    
    # 1. Load manifest
    manifest = await self.registry.get(plugin_id)
    
    # 2. Validate schema
    await self.validate_manifest(manifest)
    
    # 3. Load schemas
    await self.schemas.load(manifest.schemas)
    
    # 4. Initialize runtime
    if manifest.runtime_type == "mcp":
        await self.mcp_adapter.connect(manifest.mcp_server)
    elif manifest.runtime_type == "wasm":
        await self.wasm_runtime.load(manifest.wasm_path)
    
    # 5. Register capabilities
    await self.capability_registry.register(manifest.capabilities)
    
    # 6. Emit activation event
    await self.events.emit("plugin_activated", plugin_id=plugin_id)
```

### 5.3 Deactivation

```python
async def deactivate_plugin(plugin_id: str):
    """Deactivation flow"""
    
    # 1. Revoke capability exposure
    await self.capability_registry.revoke(plugin_id)
    
    # 2. Drain in-flight executions
    await self.execution_pool.drain(plugin_id)
    
    # 3. Unload runtime
    if plugin.runtime_type == "mcp":
        await self.mcp_adapter.disconnect(plugin_id)
    elif plugin.runtime_type == "wasm":
        await self.wasm_runtime.unload(plugin_id)
    
    # 4. Preserve audit trail
    await self.audit.log_deactivation(plugin_id)
```

---

## 6. Anti-Patterns

### NEVER Do

| Anti-Pattern | Why | Use Instead |
|-------------|-----|-------------|
| Raw code upload | Arbitrary code execution | MCP/remote/WASM |
| importlib load | In-process execution | Package install |
| SKILL.md as source | Markdown for humans | plugin.yaml |
| Hot module reload | Runtime code injection | Policy-gated lifecycle |
| Arbitrary routes | Plugin injection | Declared ingress only |
| Direct HTTP from plugin | Uncontrolled calls | Policy + credential wrapper |

---

## 7. API Contracts

### 7.1 Plugin Management

```yaml
# GET /plugins
Response: { "plugins": [{ "id": "weather", "version": "1.2.0", "status": "active", "runtime": "mcp" }] }

# GET /plugins/{plugin_id}
Response: { "id": "weather", "name": "Weather", "runtime": "mcp", "capabilities": [...], "permissions": [...] }

# POST /plugins/{plugin_id}/activate
Response: { "activated": true }

# POST /plugins/{plugin_id}/deactivate
Response: { "deactivated": true }

# DELETE /plugins/{plugin_id}
Response: { "uninstalled": true }
```

### 7.2 Plugin Discovery

```yaml
# GET /plugins/available
Response: { "plugins": [{ "id": "weather", "description": "...", "rating": 4.5, "publisher": "..." }] }

# POST /plugins/install
Request: { "source": "registry:weather@1.2.0" }
Response: { "installed": true, "plugin_id": "weather" }
```

---

## 8. Security Requirements

### 8.1 Supply Chain Security

| Requirement | Implementation |
|-------------|----------------|
| Signing | RSA-SHA256, require key registration |
| Provenance | SLSA Level 3 attestation |
| Registry | Signed package registry (not random uploads) |
| Verification | Every install verifies signature |

### 8.2 Execution Isolation

| Runtime Type | Isolation |
|--------------|------------|
| manifest-only | N/A (no execution) |
| mTCP | Butler-owned wrapper, no direct access |
| remote | Butler HTTP proxy, no user credential storage |
| WASM | Memory + network isolated Extism runtime |

---

*Document owner: Platform Team*  
*Version: 2.0 - Production Required*  
*Last updated: 2026-04-18*