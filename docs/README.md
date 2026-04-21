# Butler AI - Documentation System

> **Version:** 4.1 (Production-Grade with Four Foundations)
> **Status:** Authoritative
> **Quick Nav:** [index.md](./index.md) - AI-optimized navigation

---

## Butler is a durable, memory-driven, policy-governed personal AI runtime

### Product Thesis

> **"Tell Butler what matters. Butler handles the rest, safely, consistently, across your real digital world."**

---

## Core Design Principle

Every feature must answer ONE of four questions:

| Question | Service | What it determines |
|----------|---------|------------------|
| **WHO?** | Identity | Voice face, user profile |
| **WHERE + WHEN + WHAT around?** | Context | Location, device proximity, time, environment |
| **WHAT WANT?** | Intent | Command, question, request, conversation |
| **HOW RESPOND?** | Response | Spoken, visual, notification, action |

### No Random Features

Butler ONLY responds when explicitly prompted or when monitoring critical context:
- ✅ Responding to explicit commands
- ✅ Answering direct questions
- ✅ Following user-set reminders
- ✅ Acting on detected emergencies
- ❌ Unsolicited news alerts
- ❌ Random fun facts
- ❌ Unprompted recommendations
- ❌ Tracking without consent

Reference: [perfect-design.md](./perfect-design.md) - Complete four foundations documentation

---

## Architecture Summary

### 18 Services

| Service | Purpose |
|---------|---------|
| Gateway | REST API, idempotency, streaming |
| Auth | JWT, passkeys, JWKS |
| Orchestrator | Durable execution, interrupts |
| Memory | Temporal model, entity resolution |
| ML | Retrieval → ranking cascade |
| Tools | Capability runtime, policy |
| Security | Policy engine, OPA |
| Realtime | Typed events, delivery classes |
| Device | Capability-based, health connectors |
| Data | Domain schema, outbox, RLS |
| Vision | Stacked perception, verification |
| Audio | Dual-STT, TTS stack |
| Communication | Policy layer, SLOs |
| Observability | Platform, workflow telemetry |
| Search | Full-text + semantic |
| Plugins | MCP-first tool extensions |
| (Reserved) | Future expansion |
| (Reserved) | Future expansion |

### Five Core Services (MVP)

Gateway → Auth → Orchestrator → Memory → Tools

---

## Client-Server Split

Butler optimally distributes work between client and server:

| Client (latency + privacy) | Server (intelligence + memory) |
|--------------------------|-------------------------------|
| Wake word detection | ASR (Automatic Speech Recognition) |
| VAD (Voice Activity Detection) | Intent classification |
| Sensor data collection | User profile management |
| Local embedding extraction | Cross-device context |
| Matter/IoT control | Response generation |
| Audio playback | Memory storage |

Reference: [client-server-split.md](./client-server-split.md) - Complete split mapping

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Vision AI | GroundingDINO, SAM 2, InsightFace |
| Audio AI | ECAPA-TDNN, Silero VAD, Whisper |
| Backend | FastAPI, PostgreSQL, Redis, Kafka |
| Infrastructure | Kubernetes, NGINX, Prometheus |
| Mobile | React Native (Expo) |

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

## Key Files for AI Agents

| Need | File |
|------|------|
| Navigation | [index.md](./index.md) - Start here |
| System overview | [perfect-design.md](./perfect-design.md) - Four foundations |
| Architecture | [client-server-split.md](./client-server-split.md) - Client vs server |
| Capabilities | [butler-capability-matrix.md](./butler-capability-matrix.md) - 177 features |
| Setup | [cross-platform-deployment-matrix.md](./cross-platform-deployment-matrix.md) - Deployment |
| Services | [infrastructure-architecture-spec.md](./infrastructure-architecture-spec.md) - Infrastructure |

---

## Performance Targets

| Metric | Target |
|--------|--------|
| Users | 1M |
| RPS (peak) | 10K |
| Latency P95 | <1.5s |
| Availability | 99.9% |

---

## Support

| Channel | Contact |
|---------|---------|
| Engineering | #butler-engineering |
| Security | security@butler.lasmoid.ai |
| Documentation | docs@butler.lasmoid.ai |

---

*Document owner: Architecture Team*
*Version: 4.1 (Production-Grade with Four Foundations)*
*Last Updated: 2026-04-20*