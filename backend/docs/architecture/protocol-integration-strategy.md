# Protocol Integration Strategy

This document defines the strategy for integrating MCP, A2A, and ACP protocols with Butler's RuntimeContext, ensuring proper context propagation, policy enforcement, and traceability.

## Overview

**Goal:** Ensure all protocol integrations use RuntimeContext with proper tenant/account/session scoping
**Scope:** MCP, A2A, ACP protocol integrations
**Status:** Contract-only - implementation pending

## Protocol Contracts

### MCP (Model Context Protocol)
- **Context Injection:** RuntimeContext injected into MCP requests
- **ToolPolicy Interceptor:** Policy enforcement before tool execution
- **Safe Structured Content:** Content safety validation
- **Tenant-Aware Logging:** Logging with tenant/account/session context

### A2A (Agent-to-Agent)
- **agent-card.json:** Agent metadata and capabilities
- **Context Mapping:** RuntimeContext mapped to A2A context
- **Trace Preservation:** Trace ID preservation across agent calls

### ACP (Agent Control Protocol)
- **Context Mapping:** RuntimeContext mapped to ACP context
- **Filesystem Policy:** Filesystem access policy enforcement
- **SandboxManager:** Sandbox isolation for ACP operations
- **Streaming Traceability:** Trace preservation for streaming operations

## RuntimeContext Integration

### Context Injection
```python
@dataclass(frozen=True)
class RuntimeContext:
    tenant_id: UUID
    account_id: UUID
    session_id: str | None = None
    user_id: UUID | None = None
    permissions: frozenset[str] = field(default_factory=frozenset)
    trace_id: str | None = None
```

### Context Propagation
- RuntimeContext injected at protocol entry point
- Context propagated through protocol layers
- Context validated at each layer
- Context logged at each layer

## MCP Integration

### Context Injection
- MCP requests include RuntimeContext in metadata
- MCP responses include RuntimeContext in metadata
- Context validated before processing
- Context logged for audit

### ToolPolicy Interceptor
- ToolPolicy evaluated before tool execution
- Policy decision enforced
- Approval required if policy requires
- Sandbox required if policy requires

### Safe Structured Content
- Content validated for safety
- PII redacted from content
- Secrets redacted from content
- Malicious content blocked

### Tenant-Aware Logging
- MCP operations logged with tenant context
- MCP errors logged with tenant context
- MCP metrics emitted with tenant context
- MCP audit trail maintained

## A2A Integration

### agent-card.json
- Agent metadata defined
- Agent capabilities defined
- Agent policies defined
- Agent endpoints defined

### Context Mapping
- RuntimeContext mapped to A2A context
- Tenant ID mapped to A2A tenant
- Account ID mapped to A2A account
- Session ID mapped to A2A session
- Trace ID mapped to A2A trace

### Trace Preservation
- Trace ID preserved across agent calls
- Trace context propagated
- Trace logging enabled
- Trace metrics emitted

## ACP Integration

### Context Mapping
- RuntimeContext mapped to ACP context
- Tenant ID mapped to ACP tenant
- Account ID mapped to ACP account
- Session ID mapped to ACP session
- Trace ID mapped to ACP trace

### Filesystem Policy
- Workspace-root policy enforced
- Denylist enforced
- Allowlist enforced
- Audit trail maintained

### SandboxManager
- ACP operations sandboxed
- Sandbox isolation enforced
- Sandbox cleanup enforced
- Sandbox metrics emitted

### Streaming Traceability
- Trace ID preserved for streaming
- Trace context propagated
- Trace logging enabled
- Trace metrics emitted

## Implementation Status

### Completed
- Protocol context contracts exist (domain/protocol/context_propagation.py)

### Pending
- MCP context injection
- MCP ToolPolicy interceptor
- MCP safe structured content
- MCP tenant-aware logging
- MCP policy/approval/sandbox
- A2A agent-card.json
- A2A context mapping
- A2A trace preservation
- ACP context mapping
- ACP filesystem policy
- ACP SandboxManager
- ACP streaming traceability
- Protocol integration tests

## Migration Strategy

### Phase 1: Add Context Injection
- Add RuntimeContext to MCP requests
- Add RuntimeContext to A2A requests
- Add RuntimeContext to ACP requests
- Add context validation

### Phase 2: Add Policy Enforcement
- Add ToolPolicy interceptor for MCP
- Add policy enforcement for A2A
- Add policy enforcement for ACP
- Add approval workflow

### Phase 3: Add Content Safety
- Add content validation for MCP
- Add content redaction for MCP
- Add content blocking for MCP
- Add content logging for MCP

### Phase 4: Add Tenant-Aware Logging
- Add tenant-aware logging for MCP
- Add tenant-aware logging for A2A
- Add tenant-aware logging for ACP
- Add tenant-aware metrics

### Phase 5: Add Traceability
- Add trace preservation for A2A
- Add trace preservation for ACP
- Add trace logging
- Add trace metrics

### Phase 6: Add Tests
- Add MCP integration tests
- Add A2A integration tests
- Add ACP integration tests
- Add end-to-end protocol tests

## Testing Strategy

### Unit Tests
- Test context injection
- Test context propagation
- Test policy enforcement
- Test content safety
- Test tenant-aware logging
- Test traceability

### Integration Tests
- Test MCP integration
- Test A2A integration
- Test ACP integration
- Test end-to-end protocol flows

### Protocol Integration Tests
- Test context propagation across protocols
- Test policy enforcement across protocols
- Test trace preservation across protocols
- Test tenant isolation across protocols

## Monitoring

### Metrics
- Protocol request count
- Protocol success rate
- Protocol failure rate
- Protocol latency (p50, p95, p99)
- Context injection count
- Policy enforcement count
- Content safety count

### Logging
- All protocol requests logged
- All protocol responses logged
- All context injections logged
- All policy decisions logged
- All content safety decisions logged
- All trace events logged

### Alerts
- High protocol failure rate
- Context injection failure
- Policy violation
- Content safety violation
- Trace loss

## Failure Modes

### Context Injection Failure
- Return error to caller
- Log as error
- Alert operations team
- Do not retry automatically

### Policy Enforcement Failure
- Return error to caller
- Log as error
- Include policy decision in error
- Do not retry automatically

### Content Safety Failure
- Block the content
- Log as security event
- Alert operations team
- Include in audit trail

### Trace Loss
- Log as warning
- Attempt to recover trace
- Alert operations team
- Include in audit trail

## Compliance

### Multi-Tenancy
- Protocol operations scoped to tenant
- Protocol operations scoped to account
- No cross-tenant access
- No cross-account access

### Security
- Policy enforcement at protocol boundary
- Content safety validation
- Sandbox isolation for ACP
- Audit trail maintained

### Observability
- All protocol operations logged
- All context injections logged
- All policy decisions logged
- All content safety decisions logged
- Trace preservation enabled
