# Butler AI Documentation Hub

> **For:** Product, Leadership, Engineering
> **Status:** Implementation-ready
> **Version:** 3.1
> **Reference:** Corrected specification with boundary fixes, durable runtime direction, and RFC 9457 error model
> **Quick Nav:** [index.md](./index.md) - AI-optimized navigation

---

## System Design Rules

Reference: [docs/rules/SYSTEM_RULES.md](./rules/SYSTEM_RULES.md) - Version 2.0

The Oracle-grade rules define authoritative standards for:
- RFC 9457 Problem Details (not custom success envelopes)
- Four-state health probes: /health/live, /health/ready, /health/startup
- JWT: RS256/ES256 with JWKS, NO HS256, validate issuer/audience
- Password hashing: Argon2id (OWASP minimum)
- OpenTelemetry semantic conventions for tracing

---

## What Butler Is

Butler is a personal AI system designed to observe, understand, decide, act, and learn across digital and physical environments.

It is not a chatbot wrapper.

It is a modular AI execution system that combines:
- personal assistance
- workflow automation
- memory-driven context
- multimodal input
- tool execution
- device and environment control

The system is designed around KISS and SOLID principles, with a production target of:
- **1M users**
- **10K RPS**
- **P95 latency under 1.5s**
- **security-first defaults**
- **clear service ownership**
- **implementation through modular services**

---

## What This Documentation Is For

This documentation is the control layer for the Butler project.

It exists to make sure:
- product intent is clear
- technical design is consistent
- service boundaries do not overlap
- security requirements are non-optional
- implementation follows one source of truth
- operations and scaling are already accounted for before code grows messy

This docs set should be treated as the system contract.

If code and docs disagree, either:
1. the code is wrong, or  
2. the doc must be updated before the code is considered correct

---

## How To Use This Documentation

Do not read this repository randomly.

Use it by role and by task.

### For product decisions
Start with:
- `BRD.md`
- `PRD.md`

These define:
- why Butler exists
- who it serves
- what problems it solves
- what features are in scope

### For system understanding
Then read:
- `TRD.md`
- `HLD.md`
- `LLD.md`

These define:
- architecture
- service responsibilities
- internal data flow
- technical constraints
- performance and reliability expectations

### For service implementation
Use:
- `docs/services/*.md`

Each service document should define:
- purpose
- responsibilities
- boundaries
- dependencies
- API contracts
- failure modes
- performance constraints
- scaling notes

### For runtime behavior
Use:
- `docs/agent/*`
- `docs/workflows/*`
- `docs/system/*`

These define:
- agent loop
- decision logic
- workflow execution
- first working end-to-end flow
- runtime behavior expectations

### For security and trust
Use:
- `docs/security/*`

These define:
- baseline security rules
- crypto standards
- key management
- data classification
- AI-specific security controls

### For implementation sequencing
Use:
- `docs/dev/build-order.md`
- `docs/dev/run-first-system.md`
- `docs/product/mvp-services.md` (defines minimum service path)

These define:
- what to build first
- what not to build yet
- how to get the first working system running

### For operations
Use:
- `docs/runbooks/*`
- `docs/deployment/*`
- `docs/testing/*`
- `docs/analytics/*`
- `docs/infra/*`

These define:
- how to deploy
- how to test
- how to monitor
- how to respond when things break

---

## Documentation Hierarchy

When documents conflict, use this priority order:

1. `BRD.md`  
2. `PRD.md`  
3. `TRD.md`  
4. `HLD.md`  
5. `LLD.md`  
6. service-level specifications  
7. runbooks and implementation plans

This prevents local service docs from inventing behavior that breaks product or system intent.

---

## Source of Truth Rules

Every major system behavior must be documented in exactly one authoritative place.

Examples:
- product scope belongs in `PRD.md`
- architecture belongs in `HLD.md`
- service ownership belongs in service docs
- security policy belongs in `docs/security/*`
- runtime failure handling belongs in agent/workflow/service docs
- operational recovery belongs in runbooks

Do not duplicate logic across files unless one document is explicitly a summary that points back to the source.

---

## Current Documentation Coverage

The Butler docs currently cover:

- business requirements
- product requirements
- technical requirements
- high-level architecture
- low-level architecture
- team structure
- service specifications
- runtime agent behavior
- workflow behavior
- plugin and tool model
- security baseline
- cryptography and key management
- AI-specific security
- implementation sequencing
- deployment and testing
- analytics and runbooks

This means the project is no longer at ideation stage.

It is in execution-planning stage.

---

## What “Implementation-Ready” Means Here

Implementation-ready does **not** mean the whole system is already safe to build in parallel without thought, because humans do love taking “documented” as permission to create seven conflicting services by lunchtime.

It means:

- the architecture is defined
- the service boundaries are mostly clear
- the security baseline exists
- `docs/product/mvp-services.md` (defines minimum service path)
- the first runnable system path is identifiable
- docs are strong enough to begin controlled implementation

It does **not** mean:
- all edge cases are solved
- every service is equally mature
- all docs are equally deep
- implementation can happen without validation

---

## Current Recommended Build Path

The minimum working Butler path should begin with:

- Gateway
- Auth
- Orchestrator
- Memory
- Tools

These services are enough to create the first real loop:

**user input → auth → orchestrator → memory lookup → tool execution → response → memory update**

Only after this works should additional layers be expanded:
- realtime
- ml enrichment
- communication
- search
- audio
- vision
- device/iot
- observability hardening

---

## Core System Principles

Butler must remain:

### KISS
Prefer fewer moving parts, fewer network hops, and fewer interpretations of system behavior.

### SOLID
Each service should have one reason to change and a clear interface boundary.

### Security-first
No service is complete unless it defines:
- authentication expectations
- authorization model
- transport security
- data handling rules
- failure behavior
- auditability

For Butler specifically, this now includes:
- asymmetric token signing and validation
- device-aware sessions
- phishing-resistant auth direction (passkeys)
- step-up auth for sensitive actions

### Action over demo
A feature is only real if it can be executed, validated, observed, and recovered from on failure.

### Memory with discipline
Memory is a system capability, not an excuse to store everything forever.

### Human trust
Butler must be powerful without becoming reckless.
High-risk actions require explicit control.

### Durable execution
Tasks must survive restarts, approval pauses, and delayed dependencies.
Execution should resume from a committed boundary, not restart from vibes.

---

## Security Baseline

All services are expected to align with the security docs.

Minimum expectations:
- TLS 1.3 for all transport
- mTLS for internal service communication
- AES-256-GCM for sensitive data at rest
- Argon2id for password hashing
- envelope encryption for key hierarchy
- data classification enforcement
- AI-specific protection against prompt injection, unsafe tool use, and memory poisoning

Security is not optional polish.
It is part of the runtime contract.

---

## Documentation Quality Rules

A document is not considered complete unless it answers:

- what this component does
- what it does not do
- what it depends on
- what depends on it
- what happens when it fails
- how it is secured
- how it is measured
- how it scales
- how it is tested

Good docs reduce interpretation.
Bad docs create architecture by accident.

---

## Definition of Done for a Service Spec

A service spec is done only when it includes:

- overview
- responsibilities
- boundaries
- dependencies
- API contracts
- data flow
- core logic
- failure handling
- security notes
- scaling notes
- observability expectations

If any of these are missing, the service is still draft-level, no matter how pretty the markdown looks.

---

## Definition of Done for the Project

The project moves from documentation-guided to implementation-valid only when:

1. the minimum service path runs end-to-end  
2. one real user request can execute through the full loop  
3. auth, logging, and memory writes are functioning  
4. one tool executes safely and deterministically  
5. failure behavior is visible and recoverable  
6. documentation matches actual runtime behavior  

Until then, the system is planned, not proven.

---

## Current Risks

The main risks are no longer “lack of ideas.”

They are:
- overbuilding too many services too early
- drifting from documented boundaries
- weak runtime glue between services
- vague failure handling
- treating docs as completed work instead of execution guidance

This is where projects usually become expensive mythology.

Avoid that.

---

## Recommended Entry Points

Use these reading paths depending on what you are doing:

### Building the first working system
Read:
- `docs/product/mvp-services.md` (defines minimum service path)
- `docs/dev/build-order.md`
- `docs/dev/run-first-system.md`
- `docs/system/first-flow.md`

### Implementing a service
Read:
- corresponding `docs/services/{service}.md`
- `TRD.md`
- `HLD.md`
- relevant security docs

### Validating boundaries
Read:
- service spec
- adjacent service specs
- `LLD.md`
- `docs/rules/*`

### Preparing for scale
Read:
- `docs/infra/*`
- `docs/deployment/*`
- `docs/analytics/*`
- `docs/runbooks/*`

---

## Current Project Maturity

Butler is no longer just a concept.

It now has:
- system definition
- documented architecture
- service boundaries
- implementation sequencing
- security baseline
- runtime design direction

That means the next meaningful milestone is not “more documentation.”

It is:
**a working vertical slice**

---

## Immediate Next Objective

The next objective for the Butler project is:

**Build and validate the first end-to-end execution loop using the minimum service path.**

That loop should prove:
- request intake
- auth validation
- orchestration
- context retrieval
- tool execution
- response generation
- memory update
- observability basics

Once that exists, the project moves from documentation-complete to system-real.

---

## Final Note

This repository should behave like an engineering operating manual, not a knowledge dump.

Every new document must either:
- clarify a system decision
- unblock implementation
- reduce ambiguity
- improve security
- improve operability

If it does none of those, it is probably just another markdown file humans wrote to comfort themselves while avoiding the harder problem of making the machine actually work.

---

## Performance Targets

| Metric | Target | Reference |
|--------|--------|-----------|
| Concurrent users | 50K-100K | Scale target |
| RPS (peak) | 10K | RFC 9110/9113 |
| Latency P50 | <100ms | Simple requests |
| Latency P95 | <500ms | Medium requests |
| Latency P99 | <1.5s | Complex requests |
| Availability | 99.9% | SLA target |
| Task completion rate | >85% | Success metric |

---

## Protocol Standards

| Protocol | Standard | Implementation |
|----------|----------|----------------|
| HTTP/1.1 | RFC 9110 | Gateway REST API |
| HTTP/2 | RFC 9113 | Mobile/high-perf clients |
| HTTP/3 | RFC 9114 | Edge ingress only |
| WebSocket | RFC 6455 | Realtime streaming |
| SSE | HTML Standard | One-way streaming |
| gRPC | gRPC | Internal services |
| MCP | MCP 2025 target compatibility | Tool context protocol |
| A2A/ACP | Butler internal control envelope | Agent control plane |

---

## Error Response Standards (RFC 9457)

All services MUST use RFC 9457 Problem Details for error responses:

```json
{
  "type": "https://docs.butler.lasmoid.ai/problems/{error-type}",
  "title": "Error Title",
  "status": {http_code},
  "detail": "Human-readable description",
  "instance": "/api/v1/endpoint#req_xxx"
}
```

Standard error types:
- `invalid-request` (400)
- `authentication-failed` (401)
- `authorization-failed` (403)
- `not-found` (404)
- `rate-limit-exceeded` (429)
- `internal-error` (500)
- `bad-gateway` (502)
- `service-unavailable` (503)
- `gateway-timeout` (504)

---

## Backwards Compatibility

**Changes requiring migration from v1.0:**

- Error format migrated to RFC 9457 Problem Details
- Service boundaries clarified (Gateway NEVER calls Memory directly)
- Protocol alignment to RFC 9110/9113 standards

**Migration path:**
1. Update error handling to RFC 9457 format
2. Use standard MCP client for tool calls
3. Adopt A2A/ACP for agent communication

---

## Document Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-15 | Initial draft |
| 2.0 | 2026-04-16 | Implementation-ready |
| 3.0 | 2026-04-17 | Production-ready status |
| 3.1 | 2026-04-18 | Durable runtime and boundary clarifications |

---

*Document owner: Architecture Team*  
*Last updated: 2026-04-18*  
*Version: 3.1 (Implementation-ready)*
