# Hermes Service Specification v2.0

> **Status:** Oracle-Grade v2.0
> **Updated:** 2026-04-19
> **Owner:** Integration Layer
> **References:** Platform Constitution §7, Gateway Service v3.1, Communication Service v2.0

---

## Purpose

Hermes is Butler's **permanent integration layer**. It is not a transitional component, not a temporary bridge, and not a compatibility shim.

Hermes exists to isolate Butler's core execution plane from the chaotic, ever-changing external world of platforms, channels, devices, and protocols. It provides stable, uniform interfaces to the rest of the system while handling all the messy reality of integration.

All external integrations go through Hermes. No other service speaks directly to external platforms.

---

## Boundaries

### ✅ What Hermes OWNS
- All channel and platform adapter implementations
- Transport layer semantics and reliability
- Session transport glue and connection state
- Operator messaging and control surfaces
- Protocol translation between external formats and Butler canonical types
- Delivery retry logic and backoff policies
- External rate limiting and throttling
- Webhook ingress and egress
- Device connection lifecycle management

### ❌ What Hermes DOES NOT OWN
- **Authentication** - Auth service is source of truth
- **Memory** - Memory service owns all state
- **Tenancy** - Tenant policy and quotas live in Security service
- **Orchestration** - Never makes execution decisions
- **Business logic** - Never interprets message content
- **Policy decisions** - Only enforces policy, never defines it
- **User identity** - Passes through tokens without modification

Butler core owns all contracts. Hermes adapts the world to Butler, not the other way around.

---

## Owned Capabilities

### 1. Channel / Platform Adapters
- Standardized adapter interface for all external platforms
- Slack, Discord, Email, SMS, WhatsApp, Telegram, Teams
- IoT device protocols: MQTT, CoAP, Matter
- API webhooks and callback endpoints
- Each adapter implements exactly one external protocol

### 2. Communication Delivery Semantics
- At-most-once, at-least-once, exactly-once delivery guarantees
- Message ordering guarantees per session
- Dead letter queue handling
- Delivery status tracking and reporting
- Idempotency key management for external systems

### 3. Session Transport Glue
- Maintains long-lived connections to external platforms
- Handles connection state, reconnects, and backoffs
- Translates external session identifiers to Butler session IDs
- Preserves message context across transport boundaries
- Manages presence and online/offline state

### 4. Operator Messaging & Control Surfaces
- Administrative notification channels
- System alert delivery
- Operator command ingress
- Emergency stop surfaces
- Audit log forwarding for external systems

---

## Non-Goals

Hermes explicitly will **never**:
- Be an auth source of truth
- Store user memory or conversation history
- Enforce tenant quotas or rate limits (only applies them)
- Make routing decisions for messages
- Modify message content beyond protocol translation
- Implement business logic of any kind
- Maintain user state beyond transport connection lifecycle

---

## Gateway Interactions

| Responsibility | Owner |
|----------------|-------|
| HTTP termination, TLS, request parsing | Gateway |
| Authentication validation | Gateway |
| Rate limiting enforcement | Gateway |
| Channel adapter execution | Hermes |
| Webhook signature validation | Hermes |
| Protocol translation | Hermes |
| Request routing to core services | Gateway |

Gateway handles all HTTP ingress. Hermes provides channel-specific handlers that Gateway invokes after validation.

---

## Communication Service Interactions

Hermes implements the transport layer for the Communication service:

- Communication service defines delivery requirements
- Hermes executes delivery with requested semantics
- Hermes reports delivery status back to Communication service
- Communication service owns idempotency keys for Butler internal operations
- Hermes manages idempotency for external system interactions
- All cross-service messages pass through Hermes transport layer

---

## Security

Hermes operates as a policy enforcement point:
- Security service owns all policy definitions
- Hermes receives policy decisions and enforces them
- Approval flows are initiated by Security service, executed by Hermes
- Hermes never makes allow/deny decisions
- All external communications pass through Security service policy checks before transmission

---

## Health Model

Follows Butler four-state health standard:

| State | Description |
|-------|-------------|
| **STARTING** | Adapters are initializing, connections being established |
| **HEALTHY** | All configured adapters online, delivery within SLO |
| **DEGRADED** | One or more adapters offline, delivery backlog growing |
| **UNHEALTHY** | Core transport failure, no messages being delivered |

---

## Platform Constitution Compliance

This specification complies with:
- §3.2 Service Boundary Principle
- §5.1 Layered Architecture
- §7.4 Integration Layer Requirements
- §9.2 Security Policy Enforcement Points

---

## Verification Checks

Required validation points:
```bash
grep -n "permanent integration layer" docs/02-services/hermes.md
grep -n "NOT OWN" docs/02-services/hermes.md
grep -n "Boundaries" docs/02-services/hermes.md
```
