# Butler AI - Documentation System

> **Version:** 4.0 (Production-Grade)
> **Status:** Authoritative
> **Quick Nav:** [index.md](./index.md) - AI-optimized navigation

---

## Butler is a durable, memory-driven, policy-governed personal AI runtime

### Product Thesis

> **"Tell Butler what matters. Butler handles the rest, safely, consistently, across your real digital world."**

---

## Quick Navigation

| Category | Description | Link |
|----------|-------------|------|
| **AI Index** | Optimized for AI agents | [index.md](./index.md) |
| **Governance** | Constitution, rules, models | [00-governance](./00-governance/) |
| **Core Docs** | BRD → PRD → TRD → HLD → LLD | [01-core](./01-core/) |
| **18 Services** | All service specifications | [02-services](./02-services/) |
| **Reference** | API, workflows, plugins | [03-reference](./03-reference/) |
| **Operations** | Runbooks, security, deployment | [04-operations](./04-operations/) |
| **Development** | Setup, build order | [05-development](./05-development/) |

---

## v4.0 Production-Grade Patterns

| Pattern | Description |
|---------|-------------|
| **Four-state health** | STARTING → HEALTHY → DEGRADED → UNHEALTHY |
| **RFC 9457 errors** | Problem Details format |
| **18 services** | Gateway through Plugins |
| **Macro/Routine/Workflow** | Three execution layers |
| **Service boundaries** | Gateway NEVER calls Memory |

---

## Doc Precedence

When docs conflict, resolve in this order:

1. **00-governance/platform-constitution.md** (Highest)
2. **00-governance/system-design-rules.md**
3. **01-core/BRD.md** → **PRD.md** → **TRD.md** → **HLD.md** → **LLD.md**
4. **02-services/*.md**
5. **03-reference/*.md**
6. **04-operations/*.md**
7. **Code**

---

## Architecture Principles

1. **KISS** - Keep It Simple, Stupid
2. **SOLID** - Clean boundaries
3. **Modular monolith** - Extraction-ready
4. **Event-driven** - Async over sync
5. **Security-first** - Trust by default

---

## Performance Targets

| Metric | Target |
|--------|--------|
| Users | 1M |
| RPS (peak) | 10K |
| Latency P95 | <1.5s |
| Availability | 99.9% |

---

## Getting Started

For **AI agents**, start with:

1. [index.md](./index.md) - Navigation
2. [00-governance/platform-constitution.md](./00-governance/platform-constitution.md) - Thesis
3. [01-core/HLD.md](./01-core/HLD.md) - Architecture

For **engineers**, start with:

1. [05-development/SETUP.md](./05-development/SETUP.md) - Local setup
2. [01-core/HLD.md](./01-core/HLD.md) - Architecture
3. [05-development/build-order.md](./05-development/build-order.md) - Build sequence

---

## Support

| Channel | Contact |
|---------|---------|
| Engineering | #butler-engineering |
| Security | security@butler.lasmoid.ai |
| Documentation | docs@butler.lasmoid.ai |

---

*Document owner: Architecture Team*
*Version: 4.0 (Production-Grade)*
*Last Updated: 2026-04-18*