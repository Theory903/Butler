# Butler Skill and Plugin Marketplace

> **Version:** 1.0  
> **Updated:** 2026-04-19  
> **Owner:** Butler Tools + Platform Team  
> **Sources:** OpenClaw SKILL.md patterns, OpenClaw manifest-first plugins, Supermemory MCP server portability

---

## Overview

Butler's capability marketplace is the governed, tenant-scoped registry for skills, plugins, and tools. It allows:

- First-party Butler capabilities (built-in tools and skills)
- Developer-published plugins (MCP-compatible, sandboxed)
- User-installed third-party integrations (governed by policy)
- Operator-approved enterprise capabilities

All capabilities are subject to Butler's tool risk tier model (L0–L3) and tenant quota/billing governance.

---

## Capability Format

### SKILL.md — Skill Manifest

Every skill in the marketplace declares itself via a `SKILL.md` file following the Butler skill manifest format:

```yaml
---
name: web-search
version: 1.0.0
description: Search the web and return cited results
author: butler-platform
risk_tier: L1          # L0 (safe) → L3 (high-risk)
sandbox: none          # none | docker | gvisor
mcp_compatible: true
tools:
  - web.search
  - web.fetch_page
permissions:
  - network.outbound
quotas:
  requests_per_hour: 100
  max_cost_usd_per_request: 0.01
---

## Description

...long-form skill documentation...
```

### Butler Plugin Manifest

Richer plugins (multi-tool, with UI) declare a `butler-plugin.json`:

```json
{
  "name": "google-workspace",
  "version": "2.1.0",
  "description": "Gmail, Calendar, Drive integration",
  "risk_tier": "L2",
  "tools": ["gmail.read", "gmail.send", "calendar.create", "drive.upload"],
  "sandbox": "docker",
  "mcp_compatible": true,
  "oauth_required": ["google"],
  "ui_components": ["inbox-widget", "calendar-widget"],
  "tenant_scoped": true,
  "billing": {
    "model": "per_request",
    "rate_usd": 0.001
  }
}
```

---

## MCP Compatibility

Butler's plugin system is built on the MCP (Model Context Protocol) standard:

- Every Butler tool is exposed as an MCP tool
- External MCP servers can register as Butler plugins
- MCP clients (coding agents, external AI systems) can call Butler tools via the MCP bridge
- MCP tool calls are subject to the same L0–L3 risk tiers and ACP approval flow

**MCP Bridge endpoint:** `POST /api/v1/mcp/call`  
**Format:** Standard MCP JSON-RPC

---

## Capability Registry

The marketplace registry tracks:

| Field | Description |
|---|---|
| `capability_id` | Unique slug: `{author}.{name}@{version}` |
| `risk_tier` | L0–L3 |
| `sandbox` | Required execution environment |
| `permissions` | Network, filesystem, device access declared |
| `tenant_scoped` | Whether installation is per-tenant or global |
| `mcp_compatible` | Whether MCP clients can invoke it |
| `install_count` | Number of tenant installations |
| `avg_latency_p95` | Observed P95 latency from telemetry |
| `error_rate` | 7-day rolling error rate |
| `billing_model` | flat | per_request | usage-based |

Registry is stored in Postgres (`capabilities` table) with Redis cache for hot-path tool resolution.

---

## Marketplace Governance

### Publication Review

1. Developer submits plugin manifest
2. Automated security scan: dependency audit, permission scope review, sandbox policy check
3. Risk tier classification: automated for L0/L1, manual review for L2/L3
4. Approval gate: L2+ requires Butler platform team sign-off
5. Published to registry with changelog

### Tenant-Scoped Installation

- Users/tenants install capabilities from the marketplace
- Installation is per-tenant — a capability is never globally activated for all users
- Tenant admins control which capabilities users can install
- Enterprise tenants can restrict to an approved-only allowlist

### Plugin Isolation

| Risk Tier | Isolation | Network Access |
|---|---|---|
| L0 | in-process | None |
| L1 | in-process with timeout | Allowlisted outbound only |
| L2 | docker container | Allowlisted outbound + rate-limited |
| L3 | gVisor sandbox | Strict allowlist; ACP required per call |

### Billing and Quota Governance

- Each capability invocation is logged in the billing ledger
- Per-tenant quota enforced by `RateLimiter` + Redis counters
- Billing events published to Kafka (or Redis Streams) for downstream processing
- Free tier caps: configurable per capability, enforced at plugin level
- Overage: blocked by default (configurable: block | notify | charge)

---

## First-Party Butler Capabilities (Built-in)

| Capability | Risk Tier | Category |
|---|---|---|
| `butler.web_search` | L1 | Research |
| `butler.web_fetch` | L1 | Research |
| `butler.code_execute` | L3 | Developer |
| `butler.code_edit` | L2 | Developer |
| `butler.memory.recall` | L0 | Memory |
| `butler.memory.add` | L0 | Memory |
| `butler.email.read` | L1 | Communication |
| `butler.email.send` | L2 | Communication |
| `butler.calendar.read` | L1 | Productivity |
| `butler.calendar.create` | L2 | Productivity |
| `butler.device.capture_screen` | L2 | Device |
| `butler.device.capture_audio` | L2 | Device |
| `butler.file.read` | L1 | Files |
| `butler.file.write` | L2 | Files |

---

## Reference

- `docs/03-reference/plugins/plugin-system.md` — Full plugin system specification
- `docs/03-reference/plugins/plugin-to-tool.md` — How plugins map to Butler tools
- `docs/02-services/tools.md` — Tool service and L0–L3 risk tier model
- `docs/03-reference/agent/subagent-runtime.md` — Plugin execution in sub-agents


## Harvested Capabilities: Skill Marketplace
**Source: OpenClaw Ecosystem**
- **SKILL.md Declarative Definitions:** Highly portable, markdown-driven capability manifests. Allows natural language agent instructions alongside structured metadata.
- **ClawHub/MCP Registry Alignment:** Universal integration surface using Model Context Protocol as the core protocol, avoiding tightly-coupled in-process code.
- **Manifest-First Publishing:** All capabilities, tools, and constraints are strictly validated via JSON schema before any runtime invocation or installation.

