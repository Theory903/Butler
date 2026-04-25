# Butler × Hermes Unified Multi-Tenant Runtime Security Plan
## Production-Grade SaaS Security Architecture for Tenant Isolation, Tool Execution, Model Routing, Memory, Billing, and Sandboxed Agent Operations

**Status:** Authoritative security blueprint
**Target:** Butler SaaS, Lasmoid AI
**Principle:** Butler may use Hermes implementations directly, but Butler owns identity, memory, policy, execution, billing, and trust boundaries.

---

## 1. Core Security Doctrine

Butler must treat every request, tool call, model call, memory lookup, file operation, browser session, plugin, MCP tool, and sandbox execution as tenant-scoped.

No service may infer tenant identity from loose headers, URL params, local state, model messages, tool args, or client-controlled payloads.

Tenant identity must be resolved once at the edge, verified cryptographically, converted into a canonical runtime context, then propagated through every internal call.

---

## 2. Non-Negotiable Rules

1. No raw `tenant_id` strings floating around as casual function arguments.
2. No DB query touching tenant-owned data without tenant scoping.
3. No Redis key may be manually formatted.
4. No file path may be built from raw user input.
5. No tool may execute outside `ToolExecutor`.
6. No model provider may be called outside `MLRuntime`.
7. No Hermes tool may call its own memory, credential, CLI config, or session store.
8. No sandbox may mount host directories except a tenant-scoped ephemeral workspace.
9. No browser automation may share profiles across tenants.
10. No provider credential may be returned as plaintext to app code except inside a short-lived execution scope.
11. No approval-required tool may execute without a durable approval record.
12. No billing usage may be mutable-only. Usage events must be append-only.
13. No logs may contain secrets, raw credentials, full prompts with PII, or unredacted tool params.
14. No enterprise tenant may share worker isolation with consumer tenants unless explicitly configured.
15. No fallback path may bypass governance. Fallbacks are where security bugs go to retire.

---

## 3. Canonical Tenant Context

Every request creates this object.

```python
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

class IsolationLevel(StrEnum):
    SHARED = "shared"
    DEDICATED_WORKER = "dedicated_worker"
    DEDICATED_VPC = "dedicated_vpc"

@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: str  # UUID as string
    tenant_slug: str | None = None  # display only
    org_id: str | None
    account_id: str  # UUID as string
    user_id: str  # UUID as string
    plan: str
    region: str
    isolation_level: IsolationLevel
    request_id: str
    session_id: str
    actor_type: str
    scopes: frozenset[str]
    metadata: Mapping[str, str]
```

**Rules:**

- TenantContext is immutable.
- Created only by TenantResolver.
- Passed to providers, tools, memory, search, storage, and billing.
- Never reconstructed inside downstream services.
- Never accepted directly from client payload.

---

## 4. Secure Request Flow

```
Client
  → Gateway
  → JWT/JWKS validation
  → TenantResolver
  → TenantContext
  → EntitlementPolicy
  → RateLimit + Quota
  → ButlerEnvelope
  → Orchestrator Graph
  → ToolExecutor / MLRuntime / MemoryService
  → Audit + Metering
  → Response
```

**Gateway responsibilities:**

- Verify token signature.
- Resolve user, account, tenant, org, plan, region.
- Validate scopes.
- Attach TenantContext.
- Reject unresolved tenancy.
- Reject mismatched tenant/account/session combinations.
- Normalize request into ButlerEnvelope.

---

## 5. ButlerEnvelope Security Shape

```python
from pydantic import BaseModel, Field

class TenantIdentity(BaseModel):
    tenant_id: str  # UUID as string
    tenant_slug: str | None = None  # display only
    org_id: str | None = None  # UUID as string
    account_id: str  # UUID as string
    user_id: str  # UUID as string
    plan: str
    region: str
    isolation_level: str

class ActorIdentity(BaseModel):
    actor_type: str = "user"
    scopes: list[str] = Field(default_factory=list)
    assurance_level: str = "aal1"

class ButlerEnvelope(BaseModel):
    request_id: str
    tenant: TenantIdentity
    actor: ActorIdentity
    session_id: str
    channel: str
    message: str
    attachments: list[dict] = Field(default_factory=list)
    idempotency_key: str | None = None
    model: str | None = None
    mode: str = "auto"
    model_config = {"extra": "forbid"}
```

**Rules:**

- tenant is gateway-set only.
- Client cannot override tenant.
- Downstream services consume envelope, not raw HTTP.
- Orchestrator converts envelope into TenantContext.

---

## 6. Tenant Platform Services

Use a single tenant security platform.

```
services/tenant/
  context.py          # TenantContext
  resolver.py         # JWT/session → TenantContext
  namespace.py        # Redis/storage/file keys
  entitlements.py     # plan + capability checks
  credentials.py      # encrypted credential broker
  quota.py            # limits, counters, concurrency
  metering.py         # append-only usage events
  audit.py            # security and execution audit
  isolation.py        # sandbox policy
  crypto.py           # encryption/decryption helpers
```

No provider-specific tenant manager explosion. One shared security substrate.

---

## 7. Database Isolation

Every tenant-owned table must contain:

```sql
tenant_id UUID NOT NULL
```

**Required tables:**

```sql
tenant_credentials
tenant_entitlements
tenant_usage_events
tenant_audit_events
tenant_quota_windows
tenant_sessions
tenant_workspaces
memory_entries
conversation_turns
knowledge_entities
knowledge_edges
tool_executions
approval_requests
```

**Recommended indexes:**

```sql
CREATE INDEX idx_memory_entries_tenant_account_created
ON memory_entries (tenant_id, account_id, created_at DESC);

CREATE INDEX idx_conversation_turns_tenant_session_turn
ON conversation_turns (tenant_id, session_id, turn_index);

CREATE INDEX idx_tool_executions_tenant_created
ON tool_executions (tenant_id, created_at DESC);

CREATE INDEX idx_usage_events_tenant_recorded
ON tenant_usage_events (tenant_id, recorded_at DESC);
```

**Enable Row Level Security where practical:**

```sql
ALTER TABLE memory_entries ENABLE ROW LEVEL SECURITY;

CREATE POLICY memory_entries_tenant_isolation
ON memory_entries
USING (tenant_id = current_setting('app.tenant_id')::uuid);
```

**DB session setup:**

```sql
SET LOCAL app.tenant_id = '<tenant_id>';
```

**Rules:**

- No tenant-owned query without tenant filter.
- No admin query without explicit elevated service context.
- No cross-tenant analytics from hot application connection.
- Use separate analytics replica or warehouse for aggregate reporting.

---

## 8. Redis Namespace Safety

Never hand-write Redis keys.

```python
from __future__ import annotations
import re
from dataclasses import dataclass

_SAFE_PART = re.compile(r"[^a-zA-Z0-9._-]")

@dataclass(frozen=True, slots=True)
class TenantNamespace:
    prefix: str = "butler"

    def _clean(self, value: object) -> str:
        return _SAFE_PART.sub("_", str(value))[:256]

    def key(self, ctx: TenantContext, *parts: object) -> str:
        cleaned = ":".join(self._clean(p) for p in parts)
        return f"{self.prefix}:tenant:{self._clean(ctx.tenant_id)}:{cleaned}"

    def lock(self, ctx: TenantContext, resource: str, id_: str) -> str:
        return self.key(ctx, "lock", resource, id_)

    def cache(self, ctx: TenantContext, namespace: str, key: str) -> str:
        return self.key(ctx, "cache", namespace, key)

    def rate_limit(self, ctx: TenantContext, resource: str, window: str) -> str:
        return self.key(ctx, "ratelimit", resource, window)

    def stream(self, ctx: TenantContext, session_id: str) -> str:
        return self.key(ctx, "events", session_id)
```

**Rules:**

- Redis keys always include tenant.
- Locks always include tenant.
- Cache entries always include tenant.
- Rate limits always include tenant.
- No shared cache for model responses unless data is proven public and prompt-independent.

---

## 9. Credential Broker

Provider credentials are accessed through one secure broker.

```python
class CredentialBroker:
    async def get_provider_credential(
        self,
        ctx: TenantContext,
        provider: str,
        purpose: str,
    ) -> ProviderCredential:
        """
        Returns a short-lived credential handle.
        Never logs plaintext.
        Enforces tenant, scopes, provider entitlement, and rotation status.
        """
```

**Rules:**

- Credentials encrypted at rest.
- Encryption keys managed by KMS or Vault.
- Optional per-tenant data encryption key.
- Secrets never logged.
- Secrets never passed to model prompts.
- Secrets never returned to frontend.
- Credentials may be cached only as encrypted handles or short-lived process memory.
- Rotation status checked before use.
- Provider access checked against entitlements.

**Credential table:**

```sql
CREATE TABLE tenant_credentials (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    tenant_slug TEXT UNIQUE,  -- display only
    provider TEXT NOT NULL,
    credential_encrypted TEXT NOT NULL,
    credential_metadata JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    rotated_at TIMESTAMPTZ,
    UNIQUE (tenant_id, provider)
);
```

---

## 10. Entitlements and Plans

Plans define capability, not just limits.

```python
class EntitlementPolicy:
    async def require(
        self,
        ctx: TenantContext,
        capability: str,
        resource: str | None = None,
    ) -> None:
        """
        Raises if tenant plan or actor scope cannot use capability.
        """
```

**Capabilities:**

- llm.basic
- llm.deep_reasoning
- llm.premium_models
- memory.long_term
- memory.graph
- tools.web_search
- tools.file_read
- tools.file_write
- tools.code_execution
- tools.browser_automation
- tools.device_control
- tools.finance_action
- tools.health_data
- storage.cloud_drive
- plugins.install
- mcp.connect
- enterprise.byok
- enterprise.audit_export

**Rules:**

- Free users cannot access high-cost models by default.
- Device control requires explicit enabled capability.
- Financial actions require separate policy.
- Health data access requires explicit consent.
- Enterprise BYOK requires isolated credential policy.

---

## 11. Quota, Rate Limit, and Concurrency

Use three separate controls:

1. Rate limit: request frequency.
2. Quota: monthly/periodic consumption.
3. Concurrency: simultaneous work.

```python
class TenantQuotaService:
    async def check_rate(self, ctx: TenantContext, resource: str) -> None: ...
    async def check_quota(self, ctx: TenantContext, resource: str, amount: int) -> None: ...
    async def acquire_concurrency(self, ctx: TenantContext, resource: str): ...
```

**Do not create thread pools per tenant.** Use shared worker pools with tenant-level semaphores and quotas.

**Correct model:**

```
Shared worker pool
  → tenant concurrency limiter
  → per-resource semaphore
  → quota check
  → execution
```

**Why:** Per-tenant thread pools create memory overhead, operational mess, and denial-of-service risk when tenants scale.

**Concurrency examples:**

- free: 1 active workflow, 0 code sandboxes
- pro: 3 active workflows, 1 code sandbox
- operator: 10 active workflows, 3 code sandboxes
- enterprise: configurable

---

## 12. Append-Only Metering

Billing and usage must be event-based.

```sql
CREATE TABLE tenant_usage_events (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    account_id UUID,
    user_id UUID,
    request_id UUID,
    session_id TEXT,
    provider TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    quantity NUMERIC NOT NULL,
    unit TEXT NOT NULL,
    cost_usd NUMERIC(12, 6),
    metadata JSONB NOT NULL DEFAULT '{}',
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Usage types:**

- llm.input_tokens
- llm.output_tokens
- llm.cache_read_tokens
- embedding.tokens
- search.requests
- browser.minutes
- sandbox.cpu_seconds
- sandbox.memory_mb_seconds
- storage.gb_month
- transcription.minutes
- tts.characters
- image.generations

**Rules:**

- Never mutate usage history.
- Aggregate invoices from events.
- Retry-safe idempotency required.
- Usage event must include tenant, request, provider, and resource.

---

## 13. Tool Execution Security

All tools go through ToolExecutor.

```
LangChain Tool
  → ButlerToolAdapter
  → ToolExecutor
  → Entitlement check
  → Risk classifier
  → Approval check
  → Idempotency lock
  → Sandbox policy
  → Hermes implementation
  → Audit
  → Metering
```

No Hermes tool calls directly from LangGraph. Wrap them. Govern them. Then let them work.

**Tool risk tiers:**

```python
class RiskTier(IntEnum):
    TIER_0_BUILTIN = 0
    TIER_1_READ = 1
    TIER_2_WRITE = 2
    TIER_3_DEVICE = 3
    TIER_4_RESTRICTED = 4
```

**Rules:**

- TIER_0: deterministic safe utilities.
- TIER_1: read-only tools.
- TIER_2: reversible writes.
- TIER_3: device, browser, external side effects.
- TIER_4: finance, destructive deletes, locks, cameras, health-sensitive actions.

TIER_3 and TIER_4 require approval unless user explicitly configured a narrow automation rule.

---

## 14. Approval Security

Approval records are durable and tenant-scoped.

```sql
CREATE TABLE approval_requests (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    account_id UUID NOT NULL,
    session_id TEXT NOT NULL,
    request_id UUID NOT NULL,
    tool_name TEXT NOT NULL,
    risk_tier INTEGER NOT NULL,
    args_redacted JSONB NOT NULL,
    args_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    resolved_by UUID
);
```

**Rules:**

- Approval IDs must be unguessable.
- Approval must bind to tenant, account, session, request, tool, and args hash.
- Approval expires.
- Approval cannot be reused for different args.
- Denied approval must stop execution.
- Approval result is resumed through LangGraph checkpoint state.

---

## 15. Sandbox Security

Default for SaaS:

- file read/write: tenant workspace only
- code execution: container sandbox only
- terminal: container sandbox only (disabled on free, sandboxed on paid)
- browser: isolated browser profile (ephemeral by default)
- device tools: approval-gated
- host execution: disabled in SaaS (dev mode only)

**Production rule:**

- SaaS code/terminal execution = container sandbox only
- Local shell execution = dev mode only
- Enterprise dedicated worker = allowed with explicit isolation policy

**Workspace path:**

```
/var/butler/tenants/{tenant_id}/executions/{execution_id}/
```

But do not build paths directly. Use WorkspaceManager.

```python
class WorkspaceManager:
    async def create_ephemeral_workspace(
        self,
        ctx: TenantContext,
        execution_id: str,
    ) -> Path:
        """
        Creates tenant-scoped workspace.
        Applies permissions.
        Rejects path traversal.
        """
```

**Rules:**

- No .. path traversal.
- No symlink escapes.
- No host root mounts.
- No Docker socket mount.
- No shared browser profile.
- No network access unless policy allows it.
- No metadata service access.
- No internal network access unless allowlisted.
- Enforce CPU, memory, disk, process, and timeout limits.
- Cleanup required after execution.
- Failed cleanup creates security alert.

---

## 16. Docker Sandbox Policy

Container requirements:

- read_only filesystem where possible
- no privileged mode
- no host network
- no Docker socket
- drop Linux capabilities
- seccomp profile enabled
- AppArmor/gVisor preferred
- memory limit
- CPU limit
- pids limit
- network egress policy
- tenant labels
- execution labels
- timeout

**Container labels:**

- butler.tenant_id
- butler.execution_id
- butler.request_id
- butler.risk_tier

**Network:**

- Per-execution network for risky tools.
- Per-tenant network only for longer-lived enterprise workspaces.
- Egress allowlist by tool.
- Block private IP ranges by default.

---

## 17. SSRF and Network Egress

All outbound HTTP from tools must use safe_request.

**Rules:**

- Allow only http and https.
- Block private/reserved/link-local/multicast IPs.
- Resolve DNS and verify final IP.
- Re-check after redirects.
- Block metadata endpoints.
- Limit redirects.
- Enforce timeout.
- Enforce max response size.
- Log domain, not full sensitive URL.

**Blocked ranges include:**

- 127.0.0.0/8
- 10.0.0.0/8
- 172.16.0.0/12
- 192.168.0.0/16
- 169.254.0.0/16
- 100.64.0.0/10
- ::1/128
- fc00::/7
- fe80::/10

Yes, IPv6 too. Because attackers also read documentation, unfortunately.

---

## 18. Memory Security

Memory is tenant-owned and consent-governed.

**Rules:**

- Every memory row has tenant_id.
- Every memory query filters tenant.
- Sensitive memory types require explicit consent.
- Health, finance, credentials, and identity documents get stronger classification.
- Model prompts receive minimized context, not full memory dumps.
- Memories have provenance.
- Deletion must support tenant/account/user-level erasure.
- Embeddings must be deleted when source memory is deleted.
- Graph entities must be tenant-scoped.

**Memory write policy:**

- L0 transient: no long-term storage
- L1 session: session only
- L2 preference: explicit/strong repeated preference
- L3 sensitive: consent required
- L4 restricted: never store unless explicit secure vault flow

---

## 19. Hermes Integration Rule

Hermes is not a separate runtime.

Hermes implementation code may be imported directly, but only behind Butler-owned wrappers.

Hermes may not own runtime state, memory state, credential resolution, tool authority, logging policy, or execution isolation.

**Allowed:**

- Hermes file tools → Butler file tool wrapper
- Hermes web tools → Butler search/web wrapper
- Hermes environment backends → Butler sandbox backend
- Hermes provider utilities → Butler ML provider helper
- Hermes gateway adapters → Butler communication adapters

**Forbidden:**

- Hermes SessionDB as production memory
- Hermes CLI config as production config
- Hermes direct tool registry as authority
- Hermes direct provider credentials
- Hermes direct agent loop as top-level runtime
- Hermes raw environment execution without Butler sandbox policy

**Correct architecture:**

```
Butler LangGraph node
  → Butler LangChain adapter
  → Butler ToolExecutor
  → Butler security kernel
  → Hermes function/class implementation
```

**Not:**

```
Butler → Hermes AIAgent → Hermes tools → Hermes memory
```

That would be architecture soup. Hot, messy, and somehow worse the longer it sits.

---

## 20. ML Provider Security

Model calls go through MLRuntime.

```
Orchestrator
  → MLRuntime
  → ProviderRouter
  → CredentialBroker
  → Quota/Metering
  → ProviderAdapter
```

**Rules:**

- No service calls model SDK directly.
- Provider credentials tenant-scoped.
- Prompt logging disabled by default.
- PII redaction before logging.
- Cost tracked per request.
- Model fallback preserves tenant policy.
- Premium model access checked by entitlement.
- BYOK tenants use their own credentials.
- Free users use cheap/default models unless upgraded.

---

## 21. Logging and Redaction

Never log:

- API keys
- OAuth tokens
- cookies
- authorization headers
- raw credentials
- full prompts with PII
- full tool args for risky tools
- health records
- financial details
- browser session cookies

**Use structured logs:**

```python
{
  "event": "tool_execution",
  "tenant_id": "ten_123",
  "request_id": "req_123",
  "tool_name": "web_search",
  "risk_tier": 1,
  "status": "success",
  "duration_ms": 312
}
```

Redaction required before logs leave process.

---

## 22. Audit Events

Audit everything security-relevant.

**Audit event types:**

- tenant_resolved
- auth_failed
- credential_accessed
- provider_called
- tool_requested
- tool_approved
- tool_denied
- tool_executed
- sandbox_started
- sandbox_stopped
- memory_written
- memory_deleted
- quota_exceeded
- rate_limited
- billing_event_recorded
- policy_blocked
- admin_action

**Audit table:**

```sql
CREATE TABLE tenant_audit_events (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    actor_user_id UUID,
    request_id UUID,
    session_id TEXT,
    event_type TEXT NOT NULL,
    risk_tier INTEGER,
    resource TEXT,
    action TEXT,
    status TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## 23. Object Storage Security

Storage path format:

```
tenant/{tenant_id}/account/{account_id}/objects/{object_id}
tenant/{tenant_id}/executions/{execution_id}/artifacts/{artifact_id}
```

**Rules:**

- Never expose raw storage paths.
- Use signed URLs with short TTL.
- Malware scan uploads where practical.
- Enforce file type and size limits.
- Encrypt objects at rest.
- Store metadata in DB with tenant_id.
- Delete objects on erasure request.

---

## 24. Browser Automation Security

Browser sessions require:

- tenant-scoped profile
- cookie isolation
- download directory isolation
- network egress policy
- secret redaction
- session timeout
- approval for login/session actions
- no cross-tenant shared browser state

**Default: Ephemeral browser profile per execution.**

Browser profile path:

```
/var/butler/tenants/{tenant_id}/browser_sessions/{execution_id}/profile/
```

**Persistent browser profiles require:**

- explicit user consent
- encrypted cookie store
- session expiry
- device/session binding
- audit logging
- manual disconnect option

**Why:** Shared cookies are basically "oops, I logged tenant B into tenant A's bank account," but with extra sadness.

**High-risk browser actions:**

- checkout
- payment
- banking
- account settings
- credential changes
- delete operations
- message sending
- posting publicly

These require approval.

---

## 25. Device Control Security

Device actions are at least TIER_3.

**TIER_4 if:**

- locks
- cameras
- alarms
- cars
- garage doors
- medical devices
- security systems
- payments

**Rules:**

- Device pairing requires explicit consent.
- Device actions have audit trail.
- Reversible low-risk scenes may be automated.
- Security-critical devices require fresh approval.
- Emergency flows require separate policy.

---

## 26. Enterprise Isolation

Enterprise options:

- Shared SaaS tenant
- Dedicated worker pool
- Dedicated database schema
- Dedicated database
- Dedicated VPC
- BYOK
- Private model endpoint
- Audit export
- Data retention controls

Enterprise must support:

- SSO/OIDC/SAML later.
- SCIM later.
- Admin audit.
- Workspace roles.
- Data retention policies.
- Regional residency config.

---

## 27. Final Secure Implementation Order

### Phase 0: Cleanup and Authority Freeze

- Delete duplicated legacy sections from this document.
- Freeze this document as the only tenant-security authority.
- Mark Hermes as implementation library, not runtime authority.
- Mark Butler security kernel as mandatory for all tools, memory, models, storage, and billing.

### Phase 1: Tenant Security Kernel

**Build:**

- `services/tenant/context.py`
- `services/tenant/resolver.py`
- `services/tenant/namespace.py`
- `services/tenant/entitlements.py`
- `services/tenant/credentials.py`
- `services/tenant/quota.py`
- `services/tenant/metering.py`
- `services/tenant/audit.py`
- `services/tenant/isolation.py`
- `services/tenant/crypto.py`

**Modify:**

- `backend/core/envelope.py`
- `backend/core/deps.py`
- `backend/core/middleware.py`
- `backend/infrastructure/database.py`
- `backend/infrastructure/cache.py`

**Acceptance:**

- Every request has immutable `TenantContext`.
- Client cannot override tenant.
- Missing tenant context rejects request.
- Tenant context propagates to orchestrator, tools, memory, ML, and storage.

### Phase 2: Database and Cache Isolation

**Add:**

- `tenant_id UUID NOT NULL` to every tenant-owned table.
- RLS policies where practical.
- Tenant-scoped indexes.
- Append-only usage table.
- Audit event table.
- Approval request table.
- Credential table.

**Enforce:**

- DB session sets `app.tenant_id`.
- Redis keys are created only through `TenantNamespace`.
- No raw Redis key formatting allowed.

**Acceptance:**

- Tenant A cannot read Tenant B memory, sessions, tools, usage, credentials, or audit events.
- Redis key tests prove tenant scoping.

### Phase 3: Runtime Enforcement

Wire `TenantContext` into:

- `ToolExecutor`
- `MLRuntime`
- `MemoryService`
- `SearchService`
- `WorkspaceManager`
- `ObjectStorageService`
- `ApprovalService`
- `MeteringService`
- `AuditService`

**Acceptance:**

- Tool calls fail without `TenantContext`.
- Model calls fail without `TenantContext`.
- Memory queries fail without `TenantContext`.
- Storage calls fail without `TenantContext`.

### Phase 4: Governed Hermes Assimilation

**Refactor Hermes usage:**

- Hermes file tools behind Butler file wrappers.
- Hermes web tools behind Butler search/web wrappers.
- Hermes environment backends behind Butler sandbox wrappers.
- Hermes provider helpers behind Butler ML providers.
- Hermes gateway adapters behind Butler communication adapters.

**Forbidden:**

- Hermes `SessionDB` in production.
- Hermes CLI config in production.
- Hermes direct registry as authority.
- Hermes direct provider credentials.
- Hermes top-level agent loop as production runtime.

**Acceptance:**

- No production path calls Hermes tools directly.
- All Hermes tools execute through `ToolExecutor`.
- All Hermes network calls use Butler SSRF-safe client.
- All Hermes filesystem calls use Butler workspace manager.

### Phase 5: Sandbox, Browser, and Network Isolation

**Build:**

- `DockerSandbox`
- `WorkspaceManager`
- `BrowserSandbox`
- `EgressPolicy`
- `safe_request`
- `CleanupWorker`

**Rules:**

- SaaS terminal/code execution uses container sandbox only.
- No Docker socket mount.
- No privileged containers.
- No host networking.
- No shared browser profiles by default.
- Metadata IPs and private IPs blocked.
- Symlink/path traversal blocked.

**Acceptance:**

- Sandbox cannot access host root.
- Sandbox cannot access Docker socket.
- Sandbox cannot hit metadata IP.
- Browser profiles are isolated.
- Failed cleanup creates audit/security alert.

### Phase 6: Provider and Billing Integration

Add providers through MLRuntime only:

- Anthropic
- Gemini
- Bedrock
- OpenAI-compatible providers
- Local/edge providers later

Each call must:

- Use tenant credential broker.
- Check entitlement.
- Check quota.
- Record usage event.
- Audit provider call.
- Preserve fallback policy.

**Acceptance:**

- Free tenant cannot access premium model unless entitled.
- BYOK tenant uses own key.
- Usage events are append-only.
- Model fallback cannot bypass tenant policy.

### Phase 7: Security Test Wall

Before feature tests, add:

- tenant isolation tests
- credential isolation tests
- Redis namespace tests
- memory isolation tests
- approval binding tests
- sandbox escape tests
- SSRF tests
- logging redaction tests
- usage immutability tests
- quota/rate limit tests

**Acceptance:**

- No feature work proceeds unless security tests pass.

---

## 28. Required Security Tests

- test_request_without_tenant_rejected
- test_client_cannot_override_tenant
- test_tenant_a_cannot_read_tenant_b_memory
- test_tenant_a_cannot_get_tenant_b_session
- test_redis_keys_are_tenant_scoped
- test_tool_executor_requires_tenant_context
- test_ml_runtime_requires_tenant_context
- test_provider_credential_is_tenant_scoped
- test_usage_event_is_append_only
- test_approval_bound_to_args_hash
- test_risky_tool_requires_approval
- test_workspace_blocks_path_traversal
- test_symlink_escape_blocked
- test_sandbox_has_no_docker_socket
- test_sandbox_blocks_metadata_ip
- test_browser_profile_is_not_shared
- test_logs_redact_secrets
- test_deleted_memory_deletes_embedding
- test_quota_is_per_tenant
- test_rate_limit_is_per_tenant
- test_enterprise_byok_uses_tenant_key

---

## 29. Final Architecture Summary

```
Butler SaaS Security Kernel
  ├─ TenantContext
  ├─ Entitlements
  ├─ Credentials
  ├─ Namespace
  ├─ Quotas
  ├─ Metering
  ├─ Audit
  ├─ Isolation
  └─ Policy
Butler Runtime
  ├─ LangGraph orchestration
  ├─ LangChain adapters
  ├─ Hermes implementation library
  ├─ Butler memory
  ├─ Butler tools
  ├─ Butler ML runtime
  └─ Butler sandbox
```

**Rule:**
Hermes provides implementation muscle.
Butler provides the nervous system, immune system, memory, identity, and wallet.

This is the secure version: fewer duplicate managers, stronger tenant boundaries, DB-level isolation, sandbox-first execution, governed Hermes integration, append-only billing, and testable security guarantees.

---

## 30. Provider Adapters Integration (After Security Foundation)

Once security foundation is complete, integrate provider adapters with proper governance:

### 30.1 Anthropic Adapter (Claude API)

**Integration through MLRuntime:**

```
Orchestrator
  → MLRuntime
  → ProviderRouter
  → CredentialBroker (tenant-scoped)
  → AnthropicTenantProvider
  → Quota/Metering
```

**Files to Create:**
- `services/ml/providers/anthropic_tenant.py` (after security foundation)

### 30.2 Bedrock Adapter (AWS Bedrock)

**Integration through MLRuntime:**

```
Orchestrator
  → MLRuntime
  → ProviderRouter
  → CredentialBroker (tenant-scoped)
  → BedrockTenantProvider
  → Quota/Metering
```

**Files to Create:**
- `services/ml/providers/bedrock_tenant.py` (after security foundation)

### 30.3 Gemini Native Adapter (Google Gemini)

**Integration through MLRuntime:**

```
Orchestrator
  → MLRuntime
  → ProviderRouter
  → CredentialBroker (tenant-scoped)
  → GeminiTenantProvider
  → Quota/Metering
```

**Files to Create:**
- `services/ml/providers/gemini_tenant.py` (after security foundation)

### 30.4 Auxiliary Client (Web Search)

**Integration through ToolExecutor:**

```
LangGraph Node
  → ButlerToolAdapter
  → ToolExecutor
  → Entitlement check
  → AuxiliarySearchTenant
  → Audit
  → Metering
```

**Files to Create:**
- `butler_runtime/hermes/providers/auxiliary_tenant.py` (after security foundation)

---

## 31. Environment Backends Integration (After Security Foundation)

### 31.1 Local Environment Backend

**Integration through WorkspaceManager:**

```
ToolExecutor
  → WorkspaceManager (tenant-scoped)
  → LocalEnvironmentTenant
  → Sandbox policy
  → Audit
  → Metering
```

**Files to Create:**
- `butler_runtime/hermes/environments/local_tenant.py` (after security foundation)

### 31.2 Docker Environment Backend

**Integration through WorkspaceManager:**

```
ToolExecutor
  → WorkspaceManager (tenant-scoped)
  → DockerSandbox
  → DockerEnvironmentTenant
  → Sandbox policy
  → Audit
  → Metering
```

**Files to Create:**
- `butler_runtime/hermes/environments/docker_tenant.py` (after security foundation)

---

## 32. Tool Implementations Integration (After Security Foundation)

### 32.1 Code Execution Tool

**Integration through ToolExecutor:**

```
LangGraph Node
  → ButlerToolAdapter
  → ToolExecutor
  → Entitlement check
  → Risk classifier (TIER_3)
  → Approval check
  → WorkspaceManager
  → CodeExecutionToolTenant
  → Sandbox policy
  → Audit
  → Metering
```

**Files to Create:**
- `butler_runtime/hermes/tools/code_tenant.py` (after security foundation)

### 32.2 Browser Tool

**Integration through ToolExecutor:**

```
LangGraph Node
  → ButlerToolAdapter
  → ToolExecutor
  → Entitlement check
  → Risk classifier (TIER_3)
  → Approval check
  → BrowserProfileManager (tenant-scoped)
  → BrowserToolTenant
  → Audit
  → Metering
```

**Files to Create:**
- `services/tenant/browser_profile_manager.py` (after security foundation)
- `butler_runtime/hermes/tools/browser_tenant.py` (after security foundation)

### 32.3 Terminal Tool

**Integration through ToolExecutor:**

```
LangGraph Node
  → ButlerToolAdapter
  → ToolExecutor
  → Entitlement check
  → Risk classifier (TIER_3)
  → Approval check
  → TerminalSessionManager (tenant-scoped)
  → TerminalToolTenant
  → Audit
  → Metering
```

**Files to Create:**
- `services/tenant/terminal_session_manager.py` (after security foundation)
- `butler_runtime/hermes/tools/terminal_tenant.py` (after security foundation)

---

## 33. Next Steps

1. Review this security blueprint
2. Approve architecture and security decisions
3. Begin Phase 1: Security Foundation implementation
4. Validate at each phase before proceeding
5. Complete security tests before feature tests

**Best next file to inspect:** `backend/core/envelope.py`, then `backend/core/deps.py`, because tenant context must enter the system once and propagate everywhere cleanly.
