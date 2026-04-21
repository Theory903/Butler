# Subagent Runtime Specification
> **Version:** 2.0 (Oracle-Grade)
> **Status:** Final
> **Updated:** 2026-04-19
> **Workstream:** 3 - Agent Runtime
> **Related:** `docs/03-reference/agent/agent-loop.md`, `docs/02-services/orchestrator.md`

---

## Overview

The Subagent Runtime is Butler AI OS's multi-agent execution layer that enables hierarchical, parallel, and isolated execution of AI workloads. It is the foundational mechanism that allows Butler to decompose complex tasks into specialized, bounded execution units while maintaining system integrity, security, and observability.

### Core Purpose
- Enables safe parallel execution of independent subtasks
- Provides isolation boundaries for untrusted code and third-party skills
- Implements failure containment through hierarchical supervision
- Maintains audit and trace continuity across all execution paths
- Enforces budget, quota, and policy constraints at every level

### Relationship to Orchestrator
The Subagent Runtime is a component of the Orchestrator service. It does not exist as an independent service. All subagent lifecycle operations go through the Orchestrator's public API. The Orchestrator maintains the supervision tree, handles failure recovery, and propagates policy decisions to all running subagents.

---

## Runtime Classes

Butler defines five standardized runtime classes for subagent execution, each with different isolation guarantees and performance characteristics:

| Class | Description | Isolation Level | Primary Use Case |
|-------|-------------|-----------------|------------------|
| `IN_PROCESS` | Same OS process, shared memory space, same event loop | None | Fast execution of trusted, verified internal capabilities. Zero overhead. |
| `ISOLATED_CONTAINER` | Dedicated container instance with resource limits, seccomp profiles, and network policies | Full process + kernel + network isolation | Untrusted third-party skills, MCP plugins, user-provided code. |
| `WORKER_POOL` | Dedicated OS process from a pre-warmed pool, no shared memory | Process boundary | CPU-intensive ML inference, vector operations, heavy compute workloads. |
| `DEVICE_ATTACHED` | Remote execution on user-owned edge device | Network boundary | Mobile offline execution, IoT device operations, hardware-accelerated workloads. |
| `DURABLE_WORKFLOW` | PostgreSQL-backed state machine with at-least-once delivery guarantees | Transactional isolation | Long-running workflows, multi-step operations, tasks requiring durability across restarts. |

---

## SubAgentProfile

Every subagent executes within a `SubAgentProfile` that defines its execution context and inherited capabilities. All properties are inherited from the parent agent and **can only be restricted, never elevated**.

### Inheritance Rules

| Property | Inheritance Behavior |
|----------|----------------------|
| **Identity** | Subagents receive a derived identity with a unique trace ID. User identity and permissions are inherited unchanged. |
| **Sandbox** | Sandbox capabilities are intersected with parent. Subagents cannot gain capabilities the parent does not have. |
| **Tool Access** | Tool permissions are a strict subset of parent's tool set. Individual tools may be revoked but not added. |
| **Memory Scope** | Subagents receive a bounded view of parent session memory. Write access is explicit and transactional. |
| **Budget/Quotas** | All resource budgets (tokens, compute time, API calls) are allocated from parent's remaining budget. |
| **Trace Propagation** | OpenTelemetry context is fully propagated. All subagent operations appear as child spans in the parent trace. |
| **Audit Context** | Full audit trail is maintained including parent/child relationships, invocation parameters, and exit codes. |

---

## Execution Model

### Spawning
Subagents are spawned through the Orchestrator API with:
```python
class SubAgentSpec(BaseModel):
    name: str                        # human-readable name
    runtime_class: RuntimeClass      # one of the 5 classes above
    tools: list[str]                 # allowed tool names from parent's profile
    memory_scope: str                # "session" | "user" | "isolated"
    budget: AgentBudget              # token + cost + time limits
    sandbox_profile: str             # "none" | "docker" | "gvisor"
    trace_parent_id: str             # parent span/trace ID
    identity: SubAgentIdentity       # inherited or scoped credentials
```

### Failure Isolation
- Subagent failures never impact the parent agent execution
- Parent receives a failure notification with exit code and stack trace
- Failed subagents are automatically cleaned up within 30 seconds
- Resource budgets are reclaimed immediately on termination

### Interrupt Handling
- All subagents support graceful interruption signals
- Interrupts propagate down the supervision tree
- Subagents have 5 seconds to clean up before forced termination
- Partial results are preserved and returned to parent on interrupt

### Idempotency
- All subagent spawn operations are idempotent
- Duplicate spawn requests with the same idempotency key return the existing subagent
- At-most-once execution guarantee for all runtime classes

---

## Security Model

### Trust Level Inheritance
> **Iron Law:** Subagents **never** receive a higher trust level than their parent.

Trust levels are strictly ordered:
```
SYSTEM > INTERNAL > VERIFIED_SKILL > USER_PROVIDED > UNTRUSTED
```

A subagent spawned at `VERIFIED_SKILL` level can only spawn children at `VERIFIED_SKILL` or lower.

### Policy Check Propagation
- All OPA policy decisions are inherited
- Additional policy constraints may be added
- Policy checks are performed at every subagent boundary
- Policy evaluation results are included in audit logs

### Audit Trail
Every subagent execution records:
- Parent agent identity and trace ID
- Exact capability set requested and granted
- Resource budget allocation and consumption
- All tool invocations and their parameters
- Exit code, termination reason, and runtime duration

---

## Memory Model

### Session-Scoped Memory
Subagents operate on a **sliced view** of the parent session memory:
```
Parent Session Memory
├── Shared Read-Only Region (inherited)
├── Subagent Private Region (isolated)
└── Explicit Write Back Region (transactional)
```

### Memory Scope Inheritance
1. **Read Access**: Subagents inherit read access to all parent memory by default
2. **Write Access**: Must be explicitly granted for specific memory regions
3. **Isolation**: Subagent private memory is never visible to parent or siblings
4. **Commit**: Writes are only visible to parent after explicit commit operation
5. **Rollback**: All uncommitted writes are discarded on subagent termination

### Data Classification
Data classification labels are strictly enforced across subagent boundaries. Subagents cannot access data classified above their trust level.

---

## Compliance
This specification conforms to:
- Butler Platform Constitution v2.0
- Security Baseline v2.0
- RFC 9457 Problem Details
- OpenTelemetry Semantic Conventions
