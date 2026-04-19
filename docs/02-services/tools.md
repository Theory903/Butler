# Tools Service - Technical Specification

> **For:** Engineering  
> **Status:** Active (v3.1) — Core execution runtime fully wired; MCP bridge and SkillsHub implemented
> **Version:** 3.1
> **Reference:** Butler capability runtime — policy-governed tool execution, verification, and auditing  
> **Last Updated:** 2026-04-19

---

## 0. Implementation Status

| Phase | Component | Status | Description |
|-------|-----------|--------|-------------|
| 1 | **ToolExecutor** | ✅ IMPLEMENTED | Audit record, idempotency, pre/post verification, compensation |
| 2 | **ToolVerifier** | ✅ IMPLEMENTED | JSON schema pre/post validation; side-effect stubs |
| 3 | **SkillsHub** | ✅ IMPLEMENTED | Butler-native skills: web search, email, calendar, weather, file ops |
| 4 | **MCP Bridge** | ✅ IMPLEMENTED | `MCPToolBox` — Claude-compatible MCP tool execution adapter |
| 5 | **Approval Gates** | ✅ IMPLEMENTED | Approval queue in `ButlerToolDispatch` (approval_class routing) |
| 6 | **Policy Layer** | ✅ IMPLEMENTED | `ToolCapabilityGate` — capability scope + credential + idempotency |
| 7 | **Side-effect Verification** | ⚪ PARTIAL | `_verify_side_effects` stubs — tool-specific checks return `True` |
| 8 | **Credential Delegation** | ⚪ PARTIAL | OAuth token flow structure present; full token exchange pending |

---

## 0.1 v3.1 Implementation Notes

> **Current state as of 2026-04-19**

### ToolExecutor (`services/tools/executor.py`)
Production executor with the full lifecycle:
- **Idempotency**: Redis-based dedup using `idempotency_key` (TTL: 24h)
- **Audit trail**: `ToolExecution` records in PostgreSQL (pending/running/completed/failed)
- **Compensation**: `CompensationRecord` written on failure for rollback coordination
- **Result**: `ToolResult` with `output`, `verification_result`, `side_effects`, `duration_ms`, `model_used`

### ToolVerifier (`services/tools/verification.py`)
- **Pre-conditions**: Input schema validation (`jsonschema`), permission check, risk tier gate
- **Post-conditions**: Output schema validation, side-effect verification
- `_check_permission()` and `_verify_side_effects()` are policy stubs that return `True` — both need tool-specific implementations as skills are added

### SkillsHub (`services/tools/skills_hub.py`)
Butler-native skill implementations (not MCP):
- **`web_search`**: DuckDuckGo via `duckduckgo-search` + content extraction
- **`send_email`**: SMTP/IMAP adapter (account OAuth credential)
- **`create_calendar_event`**: Google Calendar / iCal adapter
- **`get_weather`**: OpenWeatherMap API
- **`read_file`** / **`write_file`**: Local filesystem with path policy

### MCP Bridge (`services/tools/mcp_bridge.py`)
`MCPToolBox` — wraps any Claude-compatible MCP tool server:
- Discovers tools from MCP server's `list_tools` endpoint
- Translates call/result format between Butler `ToolResult` and MCP JSON schema
- Supports `stdio` and `http` MCP transports

### Key Files
| File | Role |
|------|------|
| `services/tools/executor.py` | `ToolExecutor` — lifecycle, audit, idempotency |
| `services/tools/verification.py` | `ToolVerifier` — schema + permission gate |
| `services/tools/skills_hub.py` | Butler-native skill implementations |
| `services/tools/mcp_bridge.py` | `MCPToolBox` — MCP server adapter |
| `domain/tools/hermes_dispatcher.py` | `ButlerToolDispatch` — approval + sandbox dispatch |
| `domain/tools/hermes_compiler.py` | `HermesToolCompiler` — spec compiler |

---

## 1. Service Overview

### 1.1 Purpose
The Tools service is Butler's **policy-governed capability runtime** - executing, verifying, and auditing user-scoped and system-scoped actions.

This is NOT "a place where tools run." This is Butler's capability control plane with:
- Capability registry with exposure rules
- Policy-aware tool visibility
- Risk-tiered execution
- Approval gates
- Delegated credentials
- Verification and compensation
- Durable execution events
- MCP-native external tool support

### 1.2 Responsibilities

| Layer | Responsibilities |
|-------|-----------------|
| **Capability Registry** | Tool specs, schemas, visibility/exposure rules, channel/device availability |
| **Policy Layer** | Permission checks, resource ownership, approval requirements, auth strength |
| **Credential Layer** | Service creds, user delegated, session-bound creds |
| **Execution Layer** | Native tools, adapter tools, MCP tools, sandbox runners |
| **Verification & Recovery** | Output verification, read-after-write, compensation, retry/idempotency |
| **Audit & Eventing** | Audit log, tool events, metrics/traces |

### 1.3 Boundaries

| Service | Separation |
|---------|-----------|
| Orchestrator | Decides what to execute. Tools executes. |
| Auth | Issues identity/sessions. Tools validates caller context. |
| Memory | Stores execution history. Tools emits events. |
| Security | Defines policy classes. Tools enforces at execution. |
| Gateway | Handles HTTP. Tools handles execution. |

**Service does NOT own:**
- What actions to take (Orchestrator)
- Credential source of truth (Auth)
- Long-term storage (Memory)

### 1.4 Hermes Library Integration
Tools is Butler's **strongest active consumer** of Hermes.

| Hermes path | Mode |
|---|---|
| `backend/integrations/hermes/tools/registry.py` | Adapt behind wrapper |
| `backend/integrations/hermes/tools/approval.py` | Active |
| `backend/integrations/hermes/tools/process_registry.py` | Adapt behind wrapper |
| `backend/integrations/hermes/tools/terminal.py` | Adapt behind wrapper |
| `backend/integrations/hermes/tools/files.py` | Adapt behind wrapper |
| `backend/integrations/hermes/tools/web.py` | Adapt behind wrapper |
| `backend/integrations/hermes/model_tools.py` | Adapt behind wrapper |
| `backend/integrations/hermes/toolsets.py` | Adapt behind wrapper |

**Butler still owns:**
- Tool exposure decisions
- Schema contracts
- Risk tiers and permission enforcement
- Audit logging and verification policy

`browser_*`, `code_execution.py`, `delegate_tool.py`, `mcp_tool.py`, `voice_mode.py`, `vision_tools.py` → Deferred

---

## 2. Tool Specification Model

### 2.1 ToolSpec - Rich Capability Model

```python
from dataclasses import dataclass
from enum import Enum

class RiskTier(str, Enum):
    L0 = "l0"  # read-only, no side effects
    L1 = "l1"  # reversible, low-impact
    L2 = "l2"  # external communication, user-visible
    L3 = "l3"  # identity, financial, security, physical

class SideEffectClass(str, Enum):
    NONE = "none"
    EXTERNAL = "external"
    FINANCIAL = "financial"
    IDENTITY = "identity"
    PHYSICAL = "physical"

class IdempotencyClass(str, Enum):
    IDEMPOTENT = "idempotent"
    CONDITIONAL = "conditional"
    NON_IDEMPOTENT = "non_idempotent"

class ApprovalPolicy(str, Enum):
    NONE = "none"
    IMPLICIT = "implicit"
    EXPLICIT = "explicit"
    STEP_UP_AUTH = "step_up_auth"

class VerificationMode(str, Enum):
    NONE = "none"
    SCHEMA = "schema"
    PROVIDER_ACK = "provider_ack"
    READ_AFTER_WRITE = "read_after_write"
    SCREEN_CHECK = "screen_check"
    HUMAN_CONFIRM = "human_confirm"

class AuthMode(str, Enum):
    NONE = "none"
    SERVICE_CREDENTIAL = "service_credential"
    USER_DELEGATED = "user_delegated"
    SESSION_BOUND = "session_bound"
    APPROVAL_BOUND = "approval_bound"

class SandboxProfile(str, Enum):
    PURE_INTERNAL = "pure_internal"  # Audited pure functions only
    WASM = "wasm"  # Lightweight transforms, policy filters
    GVISOR = "gvisor"  # Networked tool adapters, API callers
    FIRECRACKER = "firecracker"  # High-risk, browser, file ops

class CompensationPolicy(str, Enum):
    NONE = "none"
    REVERSIBLE = "reversible"  # Can undo
    COMPENSATABLE = "compensatable"  # Can compensate with opposite action
    COMPENSATION_REQUIRED = "compensation_required"

@dataclass
class ToolSpec:
    name: str
    version: str
    category: str
    description: str
    input_schema: dict
    output_schema: dict
    risk_tier: RiskTier
    side_effect_class: SideEffectClass
    idempotency: IdempotencyClass
    approval_policy: ApprovalPolicy
    verification_policy: VerificationMode
    compensation_policy: CompensationPolicy
    auth_mode: AuthMode
    sandbox_profile: SandboxProfile
    timeout_s: int = 30
    retry_config: dict | None = None
    
    # Availability
    channels: list[str]  # mobile, web, watch, voice, internal
    device_tiers: list[str]  # basic, standard, premium
    visibility: str = "user"  # user, admin, internal,ACP
    
    # Execution
    required_permissions: list[str] = []
    required_scope: str | None = None
    resource_ownership_check: bool = False
```

### 2.2 Example ToolSpecs

```python
# Example: send_message
send_message = ToolSpec(
    name="send_message",
    version="1.0",
    category="communication",
    description="Send SMS or WhatsApp message",
    input_schema={
        "type": "object",
        "properties": {
            "to": {"type": "string", "format": "e164"},
            "body": {"type": "string", "maxLength": 5000}
        },
        "required": ["to", "body"]
    },
    output_schema={
        "type": "object",
        "properties": {
            "message_id": {"type": "string"},
            "status": {"type": "string"}
        }
    },
    risk_tier=RiskTier.L2,
    side_effect_class=SideEffectClass.EXTERNAL,
    idempotency=IdempotencyClass.CONDITIONAL,
    approval_policy=ApprovalPolicy.EXPLICIT,
    verification_policy=VerificationMode.PROVIDER_ACK,
    compensation_policy=CompensationPolicy.NONE,
    auth_mode=AuthMode.USER_DELEGATED,
    sandbox_profile=SandboxProfile.GVISOR,
    timeout_s=30,
    channels=["mobile", "web", "watch"],
    device_tiers=["standard", "premium"],
    required_permissions=["communication:sms:send", "communication:whatsapp:send"]
)

# Example: search_web
search_web = ToolSpec(
    name="search_web",
    version="1.0",
    category="search_retrieval",
    description="Web search",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "maxLength": 500}
        },
        "required": ["query"]
    },
    output_schema={
        "type": "object",
        "properties": {
            "results": {"type": "array", "items": {"type": "object"}}
        }
    },
    risk_tier=RiskTier.L0,
    side_effect_class=SideEffectClass.NONE,
    idempotency=IdempotencyClass.IDEMPOTENT,
    approval_policy=ApprovalPolicy.NONE,
    verification_policy=VerificationMode.SCHEMA,
    compensation_policy=CompensationPolicy.NONE,
    auth_mode=AuthMode.SERVICE_CREDENTIAL,
    sandbox_profile=SandboxProfile.GVISOR,
    timeout_s=10,
    channels=["mobile", "web", "watch", "voice", "internal"]
)

# Example: unlock_door
unlock_door = ToolSpec(
    name="unlock_door",
    version="1.0",
    category="device_control",
    description="Unlock smart door",
    input_schema={
        "type": "object",
        "properties": {
            "device_id": {"type": "string"}
        },
        "required": ["device_id"]
    },
    output_schema={
        "type": "object",
        "properties": {
            "status": {"type": "string"}
        }
    },
    risk_tier=RiskTier.L3,
    side_effect_class=SideEffectClass.PHYSICAL,
    idempotency=IdempotencyClass.CONDITIONAL,
    approval_policy=ApprovalPolicy.STEP_UP_AUTH,
    verification_policy=VerificationMode.PROVIDER_ACK,
    compensation_policy=CompensationPolicy.COMPENSATABLE,
    auth_mode=AuthMode.SESSION_BOUND,
    sandbox_profile=SandboxProfile.FIRECRACKER,
    timeout_s=15,
    channels=["mobile", "watch"],
    device_tiers=["premium"],
    required_permissions=["device:lock:control"],
    required_scope="device:lock",
    resource_ownership_check=True
)
```

---

## 3. Capability Registry

### 3.1 Registry Capabilities

The registry exposes NOT just tool names:

```python
class CapabilityRegistry:
    async def get_available_tools(
        self,
        account_id: str,
        channel: str,
        device_tier: str,
        assurance_level: str
    ) -> list[ToolSpec]:
        """Return tools visible to this context"""
        
    async def check_capability(
        self,
        tool_name: str,
        account_id: str,
        action_context: dict
    ) -> CapabilityCheck:
        """Check if tool is available and under what policy"""
        
    async def get_credential_ready(
        self,
        tool_name: str,
        account_id: str
    ) -> CredentialReady:
        """Check if tool has valid credentials"""
```

### 3.2 Exposure Rules

| Context | Tools Visible |
|--------|---------------|
| mobile casual chat | search_web, set_reminder, get_weather |
| mobile full | + send_message, send_email, browser_* |
| enterprise workspace | + device:*, automation:* |
| admin console | + all user tools + system tools |
| internal agent runtime | + all tools + MCP tools |
| ACP/browser session | browser control tools |

---

## 4. Permission Model

### 4.1 Granular Permission Classes

NOT "communication = yes/no". Use:

```python
class Permission(str, Enum):
    # Communication
    SEARCH_WEB_READ = "search:web:read"
    COMMUNICATION_SMS_SEND = "communication:sms:send"
    COMMUNICATION_EMAIL_SEND = "communication:email:send"
    COMMUNICATION_WHATSAPP_SEND = "communication:whatsapp:send"
    
    # Scheduling
    CALENDAR_EVENT_CREATE = "calendar:event:create"
    CALENDAR_EVENT_READ = "calendar:event:read"
    REMINDER_CREATE = "reminder:create"
    
    # Device
    DEVICE_LOCK_CONTROL = "device:lock:control"
    DEVICE_CAMERA_VIEW = "device:camera:view"
    DEVICE_SENSOR_READ = "device:sensor:read"
    
    # Automation
    AUTOMATION_APP_LAUNCH = "automation:app:launch"
    AUTOMATION_SCENE_CREATE = "automation:scene:create"
    
    # Filesystem
    FILESYSTEM_READ_SCOPED = "filesystem:read:scoped"
    FILESYSTEM_WRITE_SCOPED = "filesystem:write:scoped"
    
    # Browser/Session
    BROWSER_SESSION_USE = "browser:session:use"
    CREDENTIAL_DELEGATION_USE = "credential:delegation:use"
```

### 4.2 Grant Model

```python
@dataclass
class PermissionGrant:
    scope: str  # action:resource
    grant_type: Literal["implicit", "explicit", "session", "durable", "revocable"]
    auth_strength_required: Literal["normal", "step_up"]
    resource_ownership_check: bool
    channel_restriction: list[str] | None
    device_trust_required: bool
    time_bounded_seconds: int | None
    delegation_source: str | None
```

---

## 5. Execution Flow

### 5.1 Full Execution Pipeline

```
1. Execute Request (from Orchestrator via internal caller context)
        ↓
2. Resolve caller context (NOT from request body - server-side from session/auth)
        ↓
3. Lookup ToolSpec from registry
        ↓
4. Check tool visibility for channel/device tier
        ↓
5. Check required permissions (from Security)
        ↓
6. Check resource ownership (if required)
        ↓
7. Check approval requirement (approval service)
        ↓
8. Check auth strength (normal vs step-up)
        ↓
9. Resolve credential (credential service)
        ↓
10. Determine execution profile (sync vs async)
        ↓
11. Execute in sandbox (gvisor/firecracker/wasm)
        ↓
12. Verify result (per verification_policy)
        ↓
13. Handle idempotency (dedupe key, retry safety)
        ↓
14. Log audit + emit events
        ↓
15. Return result
```

### 5.2 Async Execution for Side-Effects

For side-effecting tools, use durable execution:

```python
class AsyncToolExecution:
    async def prepare(self, request: ToolRequest) -> ExecutionAccepted:
        # Validate, check permissions, check credentials
        # Return accepted with execution_id
        
    async def follow_status(self, execution_id: str) -> ExecutionStatus:
        # Return: accepted → running → verifying → completed/failed/compensating
        
    async def verify(self, execution_id: str) -> VerificationResult:
        # Per verification_policy
        
    async def compensate(self, execution_id: str) -> CompensationResult:
        # Per compensation_policy
```

**Execution Events:**
- tool.execution.accepted
- tool.execution.started
- tool.execution.completed
- tool.execution.verification.completed
- tool.execution.compensation.run
- tool.execution.failed

---

## 6. Credential Layer

### 6.1 Auth Modes

For each tool execution, resolve:

```python
class CredentialResolver:
    async def resolve(self, tool_spec: ToolSpec, context: CallerContext) -> ResolvedCredential:
        # 1. Does user have grant?
        # 2. Does tool have credential?
        # 3. Is credential scope sufficient?
        # 4. Is credential still valid?
        # 5. Does this action require step-up auth?
```

### 6.2 Credential Types

| Auth Mode | Credential Source | Use Case |
|----------|-----------------|---------|
| SERVICE_CREDENTIAL | Service-owned API keys/tokens | search_web, web APIs |
| USER_DELEGATED | OAuth token from user | send_email, send_message |
| SESSION_BOUND | Session-scoped temp creds | device_control |
| APPROVAL_BOUND | Approval-escrowed creds | high-risk actions |

---

## 7. Idempotency + Compensation

### 7.1 Idempotency Declaration

| Tool | Idempotency | Execution Key Derivation |
|------|-----------|----------------------|
| search_web | IDEMPOTENT | hash(query) |
| set_reminder | CONDITIONAL | normalized(title + time + device) |
| send_message | NON_IDEMPOTENT | Only with explicit idempotency_key |
| calendar.create_event | CONDITIONAL | external_id if provided |
| unlock_door | CONDITIONAL | device_id + timestamp bucket |

### 7.2 Compensation Policies

```python
# Example compensation definitions
compensation_policies = {
    "lock_door": {
        "action": "lock_door",
        "device_id": "{{device_id}}"
    },
    "send_email": {
        "action": "none",  # Cannot unsend
        "fallback": "reply_with_correction"
    }
}
```

---

## 8. Sandbox Profiles

### 8.1 Execution Profiles

| Profile | When to Use | Network | Filesystem | Isolation |
|---------|-------------|---------|------------|-----------|
| PURE_INTERNAL | Audited internal pure functions | None | None | Process |
| WASM | Policy filters, parser/verifier | None | None | WASM |
| GVISOR | API callers, tool adapters | Allowlist | None | gVisor |
| FIRECRACKER | Browser automation, sensitive file ops | Bridge | RO bind | MicroVM |

### 8.2 Network Allowlist

```yaml
allowed_domains:
  - api.twilio.com
  - api.sendgrid.com
  - api.openweathermap.org
  - duckduckgo.com
  - api.search.brave.com
  
allowed_ips:
  - 13.107.42.0/24  # Microsoft
```

---

## 9. API Contracts

### 9.1 Execute (Internal-Safe Contract)

```yaml
POST /tools/execute
  Request:
    {
      "tool": "send_message",
      "params": {},
      "execution_context": {
        "task_id": "task_abc",
        "session_id": "session_xyz",
        "account_id": "acc_123",
        "channel": "mobile",
        "device_tier": "premium",
        "approval_token": "approval_abc",  # if required
        "idempotency_key": "idem_abc"  # if used
      }
    }
  Response:
    {
      "execution_id": "exec_123",
      "status": "completed",
      "result": {...},
      "verification": {...}
    }
```

**Note:** No raw `user_id` in body. Caller context comes from authenticated session.

### 9.2 Prepare (Async Execution)

```yaml
POST /tools/prepare
  Request: same as execute
  Response:
    {
      "execution_id": "exec_123",
      "status": "accepted",
      "requires_approval": true
    }
```

### 9.3 Verify

```yaml
POST /tools/verify
  Request: { "execution_id": "exec_123" }
  Response:
    {
      "status": "verified",
      "verification_mode": "provider_ack",
      "result": {...}
    }
```

### 9.4 Capabilities

```yaml
GET /tools/{tool}/capability
  Response:
    {
      "name": "send_message",
      "available": true,
      "channels": ["mobile", "web"],
      "requires_approval": true,
      "requires_step_up": false,
      "credential_status": "ready"
    }
```

### 9.5 List

```yaml
GET /tools/list
  Query: ?account_id=&channel=&device_tier=
  Response:
    {
      "tools": [
        {
          "name": "send_message",
          "category": "communication",
          "risk_tier": "l2",
          "available": true
        }
      ]
    }
```

---

## 10. Observability

### 10.1 Metrics

| Metric | Type | Alert Threshold |
|--------|------|----------------|
| tool.execution.duration | histogram | p99 > 10s |
| tool.execution.success_rate | gauge | <95% |
| tool.execution.async.pending | gauge | >50 |
| tool.verification.failures | counter | >10/min |
| tool.compensation.run | counter | any |
| tool.approval.required | counter | rate |
| tool.approval.denied | counter | rate |
| credential.resolution.failures | counter | any |

### 10.2 Audit Fields

Every tool execution logs:
- actor_id, account_id, session_id, device_id
- tool_name, tool_version
- risk_tier, approval_policy
- policy_decision, reason
- credential_used (reference, not value)
- execution_id, task_id, workflow_id
- idempotency_key
- outcome, verification_mode

---

## 11. Runbook Quick Reference

### 11.1 Tool Execution Fails

```bash
# Check tool status
curl http://tools:8005/health

# Check execution logs
kubectl logs -l app=tools -f | grep "execution_id"

# Check sandbox status
curl http://sandbox-manager:9000/status

# Retry with idempotency
curl -X POST http://tools:8005/tools/execute -d '{"tool": "...", "idempotency_key": "..."}'
```

### 11.2 Permission Denied

```bash
# Check Security service
curl http://security:8015/health

# Check permission grant
curl "http://security:8015/security/permissions?account_id=...&tool=send_message"

# Grant permission (via auth service flow)
```

### 11.3 Sandbox Resource Exhaustion

```bash
# Check sandbox pool
curl http://sandbox-manager:9000/pool_status

# Scale workers
kubectl scale deployment/sandbox-worker --replicas=10
```

---

## 12. Implementation Phases

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Tool Specification Registry and Spec Normalization | [IMPLEMENTED] |
| 2 | ToolExecutor with sync/async capability support | [IMPLEMENTED] |
| 3 | ToolVerifier for result validation and schema checks | [IMPLEMENTED] |
| 4 | Policy and Approval gates integrated into execution flow | [PARTIAL] |
| 5 | Sandbox execution (gVisor/Firecracker) and MCP-native tools | [UNIMPLEMENTED] |

---

*Document owner: Tools Team*  
*Last updated: 2026-04-19*  
*Version: 3.0 (Active)*

(End of file - 429 lines)