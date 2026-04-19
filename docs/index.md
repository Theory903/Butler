# Butler Documentation Index

> **AI-optimized navigation**
> **Version:** 4.1 (v3.1 Production Features)
> **Updated:** 2026-04-19

---

## For AI Agents - Start Here

If you're an AI working on Butler, read these **in order**:

### 1. Entry Points (Pick One)

| Your Goal | Start Here |
|----------|------------|
| Understand Butler | [00-governance/platform-constitution.md](./00-governance/platform-constitution.md) |
| Build features | [01-core/HLD.md](./01-core/HLD.md) |
| Fix bugs/investigate | [04-operations/runbooks/index.md](./04-operations/runbooks/index.md) |
| Deploy/infrastructure | [04-operations/deployment/DEPLOYMENT.md](./04-operations/deployment/DEPLOYMENT.md) |
| Security issues | [04-operations/security/SECURITY.md](./04-operations/security/SECURITY.md) |

### 2. Quick Navigation by Category

```
docs/
├── 00-governance/            # Constitution, rules, models
│   ├── platform-constitution.md
│   ├── system-design-rules.md
│   ├── object-model.md
│   ├── event-contract.md
│   ├── request-envelope.md
│   ├── glossary.md
│   └── doc-precedence.md
│
├── 01-core/                  # BRD → PRD → TRD → HLD → LLD
│   ├── BRD.md
│   ├── PRD.md
│   ├── TRD.md
│   ├── HLD.md
│   ├── LLD.md
│   └── teams.md
│
├── 02-services/              # 18 service specifications
│   ├── gateway.md           # Port 8000
│   ├── auth.md              # Port 8001
│   ├── orchestrator.md      # Port 8002
│   ├── memory.md            # Port 8003
│   ├── ml.md                # Port 8006
│   ├── realtime.md          # Port 8004
│   ├── search.md            # Port 8012
│   ├── tools.md             # Port 8005
│   ├── communication.md     # Port 8013
│   ├── data.md              # Port 8014
│   ├── security.md          # Port 8015
│   ├── observability.md     # Port 8016
│   ├── device.md            # Port 8017
│   ├── vision.md            # Port 8018
│   ├── audio.md             # Port 8019
│   ├── automation.md        # Port 8020
│   ├── workflows.md         # Port 8021
│   └── plugins.md           # Port 8022
│
├── 03-reference/            # API, workflows, plugins
│   ├── api/
│   │   ├── public-api.md
│   │   └── problem-types.md
│   ├── workflows/
│   │   ├── macro-engine.md
│   │   ├── routine-engine.md
│   │   └── durable-workflow-engine.md
│   ├── plugins/
│   │   └── plugin-system.md
│   └── runtime/
│       ├── first-flow.md
│       └── health-model.md
│
├── 04-operations/            # Production ops
│   ├── deployment/
│   │   └── DEPLOYMENT.md
│   ├── security/
│   │   ├── SECURITY.md
│   │   ├── SECURITY_BASELINE.md
│   │   ├── AI_SECURITY.md
│   │   ├── CRYPTOGRAPHY.md
│   │   └── DATA_CLASSIFICATION.md
│   ├── runbooks/
│   │   ├── index.md
│   │   ├── service-down.md
│   │   ├── high-latency.md
│   │   └── database-failure.md
│   └── testing/
│       └── TESTING.md
│
└── 05-development/           # Dev setup
    ├── SETUP.md
    ├── build-order.md
    └── run-local.md
```

---

## Critical Patterns (v4.0)

All docs follow these production-grade patterns:

| Pattern | Description | Where |
|---------|-----------|-------|
| **Four-state health** | STARTING → HEALTHY → DEGRADED → UNHEALTHY | System Design Rules |
| **RFC 9457 errors** | Problem Details format | All services |
| **RFC 9068/JWKS** | RS256 JWT, no HS256 | Auth service |
| **Argon2id** | Password hashing | Security |
| **Redis Streams** | Durable async | System Design Rules |
| **OpenTelemetry** | Semantic conventions | Observability |
| **Service boundaries** | Gateway NEVER calls Memory | Platform Constitution |

---

## Source of Truth Rules

When docs conflict, resolve in this order:

1. **00-governance/platform-constitution.md**
2. **00-governance/system-design-rules.md**
3. **01-core/BRD.md** → **PRD.md** → **TRD.md** → **HLD.md** → **LLD.md**
4. **02-services/*.md**
5. **03-reference/*.md**
6. **04-operations/*.md**
7. Code

---

## Knowledge Graph

```
                    ┌─────────────────────┐
                    │ Platform Constitution│ ← Top authority
                    └──────────┬──────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ↓                    ↓                    ↓
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│System Design    │  │   Object Model  │  │  Event Contract │
│     Rules       │  │                 │  │                 │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                    │
         └────────┬───────────┼───────────┬────────┘
                  ↓           ↓           ↓
           ┌─────────────────────────────────────┐
           │         Core Docs (BRD→LLD)        │
           └──────────────┬──────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ↓                 ↓                 ↓
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Services   │  │  Reference   │  │  Operations  │
│   (18 docs)  │  │   (API/WF)   │  │(Runbooks)    │
└──────────────┘  └──────────────┘  └──────────────┘
```

---

## v3.1 Implementation Status (as of 2026-04-19)

| Service | Status | What Changed |
|---------|--------|--------------|
| **Search** | ✅ Active | `SearchService` wired to real providers; `DeepResearchEngine` implemented |
| **Security** | ✅ Active | `RedactionService` + `ContentGuard` fully implemented |
| **Orchestrator** | ✅ Active | Security guardrails + ambient context integrated into full pipeline |
| **Memory** | ✅ Active | `FaissColdStore` + `get_cold_store()` factory added |
| **ML** | ✅ Active | `get_smart_router()` dep fixed; `TRIATTENTION_ENABLED` key fixed |
| **Audio** | 🟡 Partial | `AudioModelProxy` three-tier fallback (GPU→OpenAI→mock); diarization pending |
| **Device** | 🟡 Partial | `EnvironmentService` implemented; Mobile Bridge pending |
| **Gateway** | ✅ Active | Hermes stream bridge, channel discovery operational |
| **Auth** | ✅ Active | RS256 JWT + JWKS, Argon2id, WebAuthn |
| **Tools** | ✅ Active | `ToolExecutor` + `ToolVerifier` wired |
| **Realtime** | ✅ Active | WebSocket/SSE transport |
| **Communication** | ⚪ Partial | Email/push notification structure present |
| **Observability** | ⚪ Partial | OTEL export configured; dashboards pending |
| **Vision** | 🔲 Stub | Screen capture pipeline not implemented |
| **Data** | ✅ Active | Postgres layer operational |

---

## 18 Services Quick Reference

| # | Service | Port | Status | Key Constraint |
|---|---------|------|--------|--------------|
| 1 | Gateway | 8000 | ✅ Active | NEVER calls Memory directly |
| 2 | Auth | 8001 | ✅ Active | Identity only |
| 3 | Security | 8015 | ✅ Active | Enforcement + PII + Safety |
| 4 | Orchestrator | 8002 | ✅ Active | Decision hub + guardrails |
| 5 | Memory | 8003 | ✅ Active | Store/retrieve + FAISS cold tier |
| 6 | ML | 8006 | ✅ Active | Embeddings + SmartRouter (T0-T3) |
| 7 | Realtime | 8004 | ✅ Active | WebSocket/SSE |
| 8 | Search | 8012 | ✅ Active | RAG + DeepResearch |
| 9 | Tools | 8005 | ✅ Active | Execution |
| 10 | Communication | 8013 | ⚪ Partial | Notifications |
| 11 | Data | 8014 | ✅ Active | Postgres |
| 12 | Observability | 8016 | ⚪ Partial | Logs/metrics |
| 13 | Device | 8017 | 🟡 Partial | IoT + EnvironmentService |
| 14 | Vision | 8018 | 🔲 Stub | Screen (Phase 3 roadmap) |
| 15 | Audio | 8019 | 🟡 Partial | STT/TTS + cloud fallback |
| 16 | Automation | 8020 | 🔲 Planned | Macros |
| 17 | Workflows | 8021 | 🔲 Planned | Durable |
| 18 | Plugins | 8022 | 🔲 Planned | Extensions |

---

## Common Tasks

| Task | Doc |
|------|-----|
| Set up local dev | [05-development/SETUP.md](./05-development/SETUP.md) |
| Build a service | [05-development/build-order.md](./05-development/build-order.md) |
| Run the system | [05-development/run-local.md](./05-development/run-local.md) |
| Add a plugin | [03-reference/plugins/plugin-system.md](./03-reference/plugins/plugin-system.md) |
| Handle service down | [04-operations/runbooks/service-down.md](./04-operations/runbooks/service-down.md) |
| Handle DB failure | [04-operations/runbooks/database-failure.md](./04-operations/runbooks/database-failure.md) |
| Handle latency | [04-operations/runbooks/high-latency.md](./04-operations/runbooks/high-latency.md) |

---

## Execution Layers

| Layer | Doc | Purpose |
|-------|-----|---------|
| Macro | [03-reference/workflows/macro-engine.md](./03-reference/workflows/macro-engine.md) | Fast repeated actions |
| Routine | [03-reference/workflows/routine-engine.md](./03-reference/workflows/routine-engine.md) | Contextual behavior |
| Durable Workflow | [03-reference/workflows/durable-workflow-engine.md](./03-reference/workflows/durable-workflow-engine.md) | Long-running tasks |

---

## Protocol Reference

| Protocol | Standard | Implementation |
|----------|----------|----------------|
| HTTP | RFC 9110 | REST API |
| JWT | RFC 9068 | RS256 + JWKS |
| Errors | RFC 9457 | Problem Details |
| TLS | 1.3 | All transport |
| Passwords | Argon2id | OWASP |

---

## Metadata Required

Every doc MUST have:

```yaml
## Metadata
- Version: 4.0
- Status: authoritative | draft
- Owner: <team>
- Last Updated: YYYY-MM-DD
- Depends On:
- Supersedes:
- Source of Truth Rank:
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 4.1 | 2026-04-19 | v3.1 feature docs: Search, Security, Memory, ML, Audio, Device, Orchestrator |
| 4.0 | 2026-04-18 | Production-grade rewrite, 18 services, governance docs |
| 3.1 | 2026-04-18 | Oracle-grade v2.0 |
| 3.0 | 2026-04-17 | Production-ready |
| 2.0 | 2026-04-16 | Implementation-ready |

---

*AI-optimized navigation - start with platform-constitution.md for full authority*
*Version: 4.1 (v3.1 Production Features — 2026-04-19)*