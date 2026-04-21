# Butler Operator Plane

> **Version:** 1.0  
> **Updated:** 2026-04-19  
> **Owner:** Butler Gateway + Security Team  
> **Sources:** OpenClaw doctor/status/control-plane patterns, Twitter Server admin endpoint patterns

---

## Overview

Butler's operator plane provides the control surfaces for managing, monitoring, and protecting the Butler system. It is organized into three distinct operator roles with clear RBAC scopes, audit trails, and break-glass controls.

---

## OperatorScope

OperatorScope defines the set of capabilities and permissions available to each operator role.

## Operator Roles

### 1. Personal Operator

The user themselves, acting as the operator of their own Butler instance.

**Scope:**
- All user-facing capabilities
- Tool approval workflows (ACP confirmations)
- Memory inspection and deletion
- Capability installation from marketplace
- Device management (pair/unpair, permissions)
- Account settings, retention, consent configuration

**Auth requirement:** AAL2 (strong MFA)

### 2. Tenant Admin

An administrator managing a team, organization, or multi-user Butler deployment.

**Note:** "Tenant admin" refers specifically to this role within a tenant scope, distinct from platform-level administrators.

**Scope (in addition to Personal Operator):**
- User management within tenant (invite, deactivate, role assignment)
- Capability allowlist/blocklist for tenant
- Quota and billing configuration
- Audit log access for tenant users
- Kill-switch for specific users or capabilities
- SLA and health dashboard for tenant nodes

**Auth requirement:** AAL3 (phishing-resistant MFA)

### 3. Platform Admin (Butler Operations Team)

Butler engineering and operations staff managing the global platform.

**Scope (in addition to Tenant Admin, cross-tenant):**
- Global circuit breaker control
- Node drain and graceful shutdown
- Cluster health dashboard (`GET /admin/cluster/status`)
- Emergency kill switches (global capability disable)
- Cross-tenant audit log access
- Doctor diagnostic runs
- Deployment and canary management

**Auth requirement:** AAL3 + hardware key + just-in-time access tokens

---

## Doctor

The **Doctor** is Butler's self-diagnostic and self-healing subsystem. Inspired by OpenClaw's doctor UX.

**Doctor checks:**
- Auth service reachability and JWKS freshness
- Redis connectivity and health
- Postgres connectivity and migration state
- Vault connectivity and secret accessibility
- Neo4j/Qdrant reachability
- TLS certificate expiry
- Security configuration audit (no hardcoded secrets, secure defaults)
- Dependency version audit
- Self-healing: can auto-remediate certain issues (`--fix` flag)

**Endpoints:**
- `GET /api/v1/health/ready` — readiness probe (Kubernetes)
- `GET /api/v1/health/live` — liveness probe
- `GET /api/v1/health/startup` — startup probe
- `POST /api/v1/admin/doctor/diagnose` — trigger full doctor run (Platform Admin only)

---

## Control UI

Butler's operator control UI surfaces:

| Surface | Access Level | Description |
|---|---|---|
| **User Dashboard** | Personal Operator | Memory browser, session history, active tasks, device manager |
| **Approval Inbox** | Personal Operator | ACP pending approvals, action audit trail |
| **Tenant Admin Panel** | Tenant Admin | User management, capability allowlists, quota dashboards |
| **Platform Admin Console** | Platform Admin | Cluster health, circuit breakers, drain controls, audit logs |
| **Doctor UI** | Tenant Admin + Platform Admin | Diagnostic results, self-healing actions |

All control UI interactions are:
- Authenticated (AAL matching role requirement)
- Audit-logged (who, what, when, from where)
- Rate-limited (no bulk operations without explicit approval)

---

## Emergency Controls

### Break-Glass

For security incidents or critical failures, Platform Admins have break-glass access:
- Bypass normal approval flow with just-in-time token
- Break-glass access is time-limited (1 hour max) and requires two-person authorization
- Every break-glass activation creates an immediate audit alert

### Drain

`POST /api/v1/admin/drain` — stops accepting new requests while in-flight requests complete.

- Used for graceful maintenance, deployments, or emergency response
- Configurable timeout (default: 30s)
- Cancellable: `DELETE /api/v1/admin/drain`

### Kill Switches

`POST /api/v1/admin/kill-switch/{service}` — disable a specific service or capability.

- Per-service kill switches (gateway, ml, tools, memory...)
- Per-capability kill switches (disable a specific tool globally)
- Kill switch state persisted in Redis (survives restarts)
- Auto-reactivation timer (optional): kill switch expires after N hours

### Circuit Breakers

- `GET /api/v1/admin/circuit-breakers` — view all breaker states
- `POST /api/v1/admin/circuit-breakers/reset` — manually reset all breakers to CLOSED
- Circuit breaker states exported to Prometheus (`butler_circuit_breaker_state` gauge)

---

## Audit Trails

Every operator action is logged with:

```json
{
  "event": "admin.drain.initiated",
  "actor_id": "user_abc123",
  "actor_role": "platform_admin",
  "ip": "192.168.1.1",
  "aal": "aal3",
  "payload": {"timeout_s": 30, "reason": "emergency deployment"},
  "ts": 1745123456,
  "trace_id": "abc123def456..."
}
```

Audit logs are:
- Append-only (immutable in production)
- Retained for 7 years (compliance default)
- Encrypted at rest
- Accessible only to authorized roles

---

## Tenant-Aware Dashboards

The Tenant Admin panel shows:

| Metric | Description |
|---|---|
| Active users (last 24h) | Distinct users with sessions |
| Tool invocations (by tier) | L0/L1/L2/L3 breakdown |
| ACP approval rate | % of L3 actions approved vs rejected |
| Memory write volume | Writes by tier (episodic, graph, etc.) |
| Error rate | 1xx/2xx/4xx/5xx breakdown |
| Quota consumption | % of tenant quota used this billing period |
| Active circuit breakers | Any open breakers affecting tenant |

---

## Reference

- `backend/api/routes/admin.py` — Admin endpoint implementations
- `backend/core/health_agent.py` — Node health monitoring
- `backend/core/circuit_breaker.py` — Circuit breaker registry
- `docs/02-services/gateway.md` — Gateway service boundaries
- `docs/02-services/observability.md` — Observability stack


## Harvested Capabilities: Operator Plane
**Source: twitter-server**
- **Admin HTTP Diagnostics Interface:** Standardized `/admin/metrics`, `/admin/histograms`, and `/health/startup` lifecycle endpoints injected automatically into every running subsystem.
- **Dynamic Log/Metric Filtering:** Per-tenant, per-agent log verbosity toggles directly via the Admin panel.

**Source: OpenClaw**
- **Doctor Command (/status, /doctor):** Comprehensive environment validation checks to verify local daemon permissions, port bindings, and key health before launching.

