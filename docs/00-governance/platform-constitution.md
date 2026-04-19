# Butler Platform Constitution

> **For:** All Engineering, Product, Design  
> **Status:** Authoritative  
> **Version:** 2.0  
> **Reference:** Cross-service governance - the one document that binds all Butler services

---

## v2.0 Changes

- Full-product modular monolith architecture
- 18 canonical services (not just MVP)
- Runtime planes model
- Package boundary rules
- Full build priority defined

---

## 1. Platform Definition

### 1.1 What Butler Is

**Butler is a durable, memory-driven, policy-governed personal AI runtime across devices, channels, and environments.**

Butler is NOT:
- A chatbot wrapper
- A tool execution engine
- A smart home app
- An ML microservice zoo
- A random agent experiment wearing enterprise clothes

### 1.2 Platform Mission

Butler exists to:
1. **Observe** and understand user context across devices, channels, and environments
2. **Remember** user relationships, preferences, routines, and history
3. **Decide** what actions serve the user's goals
4. **Act** across tools, devices, and integrations
5. **Learn** from outcomes to improve over time

---

## 2. Architecture Model

### 2.1 Full-Product Modular Monolith

Butler uses **one deployable backend** with real service boundaries inside the codebase.

```
backend/
├── app/
│   ├── main.py
│   ├── lifespan.py
│   ├── core/                    # Config, security, telemetry
│   ├── api/routers/            # 18 route modules
│   ├── services/                # 18 application services
│   ├── domain/                  # Business contracts per service
│   ├── infrastructure/           # Storage adapters
│   └── tests/
├── alembic/
├── docker-compose.yml
└── pyproject.toml
```

### 2.2 Dependency Rules

| Rule | Implementation |
|------|---------------|
| api → services → domain → infrastructure | Never skip layers |
| api → infrastructure | FORBIDDEN |
| service A → service B internals | FORBIDDEN (use contracts) |
| infrastructure → api | FORBIDDEN |

---

## 3. Service Catalog (18 Canonical Services)

### 3.1 Identity & Control

| Service | Owns | Key Capabilities |
|---------|------|-------------------|
| **Auth** | Identity, sessions, tokens | Passkeys, MFA, device trust, linked identities |
| **Security** | Policy, authorization, AI gating | Crypto, approval rules, redaction, threat detection |
| **Gateway** | Transport, normalization | TLS termination, rate limiting, idempotency, protocol adapters |

### 3.2 Intelligence Core

| Service | Owns | Key Capabilities |
|---------|------|-------------------|
| **Orchestrator** | Planning, coordination | Intent understanding, structured planning, durable execution |
| **Memory** | Context, history | Session history, preferences, episodic + semantic memory |
| **ML** | Embeddings, models | Intent classification, reranking, candidate retrieval |
| **Search** | Evidence, citations | Web search, crawler orchestration, citation bundles |

### 3.3 Action & Interaction

| Service | Owns | Key Capabilities |
|---------|------|-------------------|
| **Tools** | Tool registry, execution | Schema validation, policy-gated execution, verification |
| **Realtime** | Streaming, events | WebSocket/SSE, token streaming, notifications |
| **Communication** | Messages, delivery | SMS, WhatsApp, email, push, delivery tracking |
| **Workflows** | Durable workflows | State machines, resumable execution, checkpoints |

### 3.4 Environment & Extension

| Service | Owns | Key Capabilities |
|---------|------|-------------------|
| **Device** | Device identity, control | Mobile/desktop/IoT, sensors, cross-device state |
| **Vision** | Visual understanding | OCR, object detection, screen parsing, UI elements |
| **Audio** | Voice processing | STT, TTS, wake word, speaker ID, streaming |
| **Automation** | Trigger/action rules | Event-driven automation, scheduled routines |
| **Plugins** | Extension registry | MCP/WASM/remote adapters, signed manifests |

### 3.5 Platform Services

| Service | Owns | Key Capabilities |
|---------|------|-------------------|
| **Data** | PostgreSQL persistence | Users, sessions, workflow state, audit |
| **Observability** | Telemetry | Metrics, traces, logs, alerts |

---

## 4. Runtime Planes

```
┌─────────────────────────────────────────────────────────────┐
│                 EXPERIENCE PLANE                           │
│  API Routes | Realtime Streams | Mobile/Web/Desktop      │
├─────────────────────────────────────────────────────────────┤
│                  CONTROL PLANE                             │
│  Auth | Security | Policy | Approvals | Plugin Exposure  │
├─────────────────────────────────────────────────────────────┤
│                 INTELLIGENCE PLANE                         │
│  Orchestrator | ML | Memory | Search | Planning         │
├─────────────────────────────────────────────────────────────┤
│                    ACTION PLANE                            │
│  Tools | Communication | Device | Automation | Workflows │
├─────────────────────────────────────────────────────────────┤
│                     DATA PLANE                              │
│  PostgreSQL | Redis | Neo4j | Qdrant | S3                │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Build Priority

### Phase 1: Foundation (Week 1-2)
- Core: config, lifespan, security primitives, observability hooks

### Phase 2: Identity & Control (Week 2-3)
- Auth → Security → Data → Gateway

### Phase 3: Intelligence Core (Week 3-5)
- Memory → Tools → Orchestrator → ML

### Phase 4: Interaction (Week 5-7)
- Realtime → Communication → Search → Workflows

### Phase 5: Environment (Week 7-9)
- Device → Vision → Audio → Automation

### Phase 6: Extension (Week 9-10)
- Plugins → Hermes adapters → MCP loaders

---

## 6. Service Ownership Boundaries

### 6.1 Canonical Rules

| Rule | Service | Owns | Does NOT Own |
|------|---------|------|-------------|
| Identity | Auth | User credentials, sessions, device trust | Policy enforcement |
| Policy | Security | Policy definitions, risk signals | Credential management |
| Transport | Gateway | HTTP ingress, protocol edge | Business logic |
| Execution | Orchestrator | Planning, task coordination | Credential validation |
| Memory | Memory | Long-term memory, entity graph | ML model training |
| Intelligence | ML | Embeddings, rankers, predictors | Storage backend |
| Realtime | Realtime | Connection lifecycle, event delivery | Credential issuing |
| Devices | Device | Device control, state, health ingress | User identity |

### 6.2 Cross-Service Principles

1. **Gateway NEVER calls Memory directly.** Always via Orchestrator.
2. **Auth owns identity; Security owns enforcement.** Clear separation.
3. **Memory stores; ML generates embeddings.** Retrieval-first contract.
4. **Orchestrator decides; Tools execute.** No silent action-driving.
5. **Realtime delivers; Orchestrator publishes.** Clear pub/sub contract.

---

## 7. Core Definitions

### 7.1 Durable

**Definition:** Work must survive restarts, approval pauses, and delayed dependencies. Execution resumes from a committed boundary, not from vibes.

**Implications:**
- All task state in PostgreSQL (source of truth)
- Redis for hot cache only
- Event-sourced task trail for replay
- Compensation actions for rollback

### 7.2 Safe / Safety Class

**Definition:** Every action has a policy class determining approval requirements.

| Class | Approval Required | Examples |
|------|------------------|----------|
| `low` | No | search, get_memory, time |
| `medium` | No (logged) | send_message, create_event |
| `high` | Yes | payment, device_control |
| `critical` | Yes + dual | admin_action, lock_unlock |

### 7.3 Memory

**Definition:** Memory is a system's capability, NOT an excuse to store everything forever. Memory must evolve, not accumulate.

**Implications:**
- Temporal truth model (observed_at, valid_from)
- Episodic memory with temporal windows
- Preference + dislike graph
- Provenance on every write
- Freshness scoring
- Bounded raw retention

### 7.4 Approval

**Definition:** A gating mechanism that pauses execution pending human decision.

| Type | Trigger | Escalation |
|------|---------|-----------|
| none | low risk | None |
| implicit | medium risk | Log for review |
| explicit | high risk | User notification |
| critical | critical risk | Dual authorization |

### 7.5 Session

**Definition:** A bounded conversation context tied to identity + device + channel.

**Session Properties:**
- account_id (owner)
- device_id (interaction surface)
- channel (mobile, web, watch, voice)
- assurance_level (AAL1, AAL2, AAL3)
- active_workflow (if any)

---

## 8. Design Rules

### 8.1 Fundamental Principles

| # | Rule | Rationale |
|---|------|-----------|
| 1 | Retrieve first, reason second | Performance + cost control |
| 2 | Durable before clever | Production survival |
| 3 | Every side effect replay-safe or compensatable | Reliability |
| 4 | Every sensitive action has a policy class | Security enforcement |
| 5 | Memory evolves, not only accumulates | Cost + privacy |
| 6 | Realtime supports reconnect and replay | UX reliability |
| 7 | Every user-visible answer has provenance | Trust |
| 8 | Every service emits typed events | Debugging |
| 9 | Personal data defaults to least retention | Privacy |
| 10 | Low-end mode behavior is designed | Resilience |

### 8.2 Architecture Rules

1. **No HS256 in production.** Use RS256/ES256 with JWKS.
2. **No password hashing except Argon2id.**
3. **Redis Pub/Sub = at-most-once.** Use Streams for durable.
4. **No hardcoded embedding models.** Use contract + version.
5. **No silent action-driving from ML.** Predictions feed Orchestrator, not execute.
6. **No raw code upload.** MCP-first, manifest-driven, policy-gated.
7. **Health is not one endpoint.** Four-state model (STARTING/HEALTHY/DEGRADED/UNHEALTHY).
8. **SLO-based alerting, not threshold-heavy.**

---

## 9. Cross-Service Contracts

### 9.1 Event Contract

Every event MUST include:
```json
{
  "event_id": "evt_...",
  "type": "...",
  "timestamp": "...",
  "session_id": "...",
  "account_id": "...",
  "durable": true,
  "payload": {}
}
```

### 9.2 Request Envelope

Every request MUST include:
```json
{
  "request_id": "req_...",
  "trace_id": "trc_...",
  "channel": "mobile|web|watch|voice",
  "device": "device_id",
  "actor": { "type": "user|assistant|tool", "id": "..." },
  "timestamp": "...",
  "idempotency_key": "..."
}
```

### 9.3 Health Model (Four-State)

```
/health/startup   → STARTING / HEALTHY
/health/ready     → HEALTHY / DEGRADED / UNHEALTHY  
/health/live      → HEALTHY / UNHEALTHY
/health/degraded  → Status details
```

---

## 10. Security and Rights

### 10.1 Assurance Levels

| Level | Auth Required | Actions |
|------|--------------|---------|
| AAL1 | Password + something you know | Basic queries |
| AAL2 | Passkey or MFA | Tool execution |
| AAL3 | Step-up auth | Restricted actions |

### 10.2 Data Rights

- **Minimization:** Collect least data needed
- **Retention:** Explicit TTL per data class
- **Ambient recording:** Opt-in only, user toggle, retention limits
- **Health data:** Tightly consented, explicit use only

---

## 11. Enforcement

Every service doc must:
1. Reference this Constitution for key definitions
2. Document how it handles each Design Rule
3. Define its safety classes
4. Implement four-state health model
5. Emit typed events per Event Contract
6. Implement replay/compensation

**Violations:** Found in code reviews, caught in architecture reviews.

---

*Document owner: Architecture Team*  
*Version: 2.0 (Authoritative)*  
*Last updated: 2026-04-18*