# Butler Backend — Master Implementation Plan

> **Version:** 1.0  
> **Status:** Approved for execution  
> **Updated:** 2026-04-18  
> **Scope:** 0 → 100% production-grade backend for all 16 services  
> **Source of truth:** `docs/02-services/*.md`, `docs/AGENTS.md`, `docs/rules/SYSTEM_RULES.md`

---

## Executive Summary

Butler is a modular AI execution system with **16 services** spanning digital and physical environments. This plan takes the project from the current prototype state (skeleton routes, basic JWT, no domain logic) to a fully functional, production-grade backend.

### Current State (What Exists)

| Component | State | Quality |
|-----------|-------|---------|
| `infrastructure/config.py` | Settings loader | ✅ Acceptable |
| `infrastructure/database.py` | SQLAlchemy async engine | ✅ Acceptable |
| `infrastructure/cache.py` | Redis client wrapper | ✅ Acceptable |
| `domain/auth/models.py` | Account, Identity, Session, TokenFamily, PasskeyCredential | ⚠️ Incomplete — missing fields from Data spec |
| `services/auth/jwt.py` | RS256 signing with JWKSManager | ⚠️ Missing JWKS doc fields (n, e), no key rotation |
| `services/auth/routes.py` | Register, login, refresh, JWKS endpoint | ⚠️ Business logic in routes, no RFC 9457, no proper error model |
| `services/gateway/routes.py` | Health probes, rate limiter, stub chat | ⚠️ Not a real gateway — no envelope, no auth enforcement |
| `services/orchestrator/routes.py` | Hardcoded intent classifier, mock responses | ❌ Placeholder — no durable execution, no real logic |
| `services/memory/` | Empty directory | ❌ Not started |
| `services/tools/` | Empty directory | ❌ Not started |
| `services/ml/` | Empty directory | ❌ Not started |
| `services/realtime/` | Empty directory | ❌ Not started |
| `services/search/` | Empty directory | ❌ Not started |
| `services/communication/` | Empty directory | ❌ Not started |
| `docker-compose.yml` | Postgres 15 + Redis 7 | ✅ Good baseline |
| `pyproject.toml` | Core deps defined | ⚠️ Missing many production deps |

### Target State

A fully operational backend where:
1. A user can register, login, and get RS256 JWTs
2. Send a chat message through Gateway → Orchestrator → Memory/Tools → Response
3. Durable workflows survive restarts
4. Memory persists facts, episodes, and preferences
5. Tools execute with policy governance and verification
6. Real-time events stream to connected clients
7. All errors follow RFC 9457 Problem Details
8. Observability covers traces, metrics, and logs via OpenTelemetry

---

## Architecture Principles (Non-Negotiable)

These are drawn from `docs/AGENTS.md` and `docs/rules/SYSTEM_RULES.md`:

| Principle | Rule |
|-----------|------|
| **Error Format** | RFC 9457 Problem Details — no custom envelopes |
| **Health Probes** | `/health/live`, `/health/ready`, `/health/startup` — separate endpoints |
| **JWT** | RS256/ES256 with JWKS, **NO HS256**, validate issuer + audience |
| **Password Hashing** | Argon2id (OWASP minimum) |
| **Observability** | OpenTelemetry semantic conventions |
| **Service Boundaries** | Domain must NOT import FastAPI; routes must NOT contain business logic |
| **Gateway Rule** | Gateway NEVER calls Memory directly — always via Orchestrator |
| **Docs = Truth** | If code and docs disagree, docs win (or docs must be updated first) |

---

## Phase Overview

```
Phase 0: Foundation & Cross-Cutting        ██░░░░░░░░ ~15%
Phase 1: Auth & Identity                   ████░░░░░░ ~10%
Phase 2: Gateway & Request Pipeline        ██████░░░░ ~12%
Phase 3: Orchestrator & Durable Runtime    ████████░░ ~20%
Phase 4: Memory, Tools & Search            ██████████ ~25%
Phase 5: ML, Realtime & Communication      ██████████ ~10%
Phase 6: Security, Observability & Device  ██████████ ~8%
                                           ─────────── 100%
```

### Phase Dependency Graph

```
Phase 0 (Foundation)
    ├── Phase 1 (Auth)
    │     └── Phase 2 (Gateway)
    │           └── Phase 3 (Orchestrator)
    │                 ├── Phase 4 (Memory + Tools + Search)
    │                 │     └── Phase 5 (ML + Realtime + Communication)
    │                 └── Phase 6 (Security + Observability + Device/Vision/Audio)
```

---

## Phase 0: Foundation & Cross-Cutting Concerns

**Goal:** Establish the infrastructure every service depends on.  
**Plan:** [01-phase-0-foundation.md](./01-phase-0-foundation.md)

| Deliverable | Description |
|-------------|-------------|
| RFC 9457 error model | Shared `Problem` exception + FastAPI handler |
| Canonical request envelope | `ButlerEnvelope` Pydantic model |
| Structured logging | structlog + OpenTelemetry trace context |
| Database migrations | Alembic setup with the full Data spec schema |
| Health probe mixin | Reusable 3-endpoint health check |
| Domain base classes | `DomainService`, `Repository` abstractions |
| Test infrastructure | pytest fixtures, factory classes, test DB |
| API versioning | `/api/v1/` prefix convention |

---

## Phase 1: Auth & Identity Platform

**Goal:** Production-grade identity, session issuance, JWKS, and token lifecycle.  
**Plan:** [02-phase-1-auth.md](./02-phase-1-auth.md)

| Deliverable | Description |
|-------------|-------------|
| Account lifecycle | Create, soft-delete, status management |
| Multi-identity support | Password, passkey, OIDC stubs |
| Session management | Device binding, assurance levels, expiry |
| Token family rotation | Detect reuse → revoke family |
| JWKS endpoint | Full RFC 7517 document with RSA key material |
| Password hashing | Argon2id via `argon2-cffi` |
| Domain/service split | `domain/auth/` contracts → `services/auth/` implementation |

---

## Phase 2: Gateway & Request Pipeline

**Goal:** Edge control plane with auth enforcement, rate limiting, and canonical envelope.  
**Plan:** [03-phase-2-gateway.md](./03-phase-2-gateway.md)

| Deliverable | Description |
|-------------|-------------|
| Auth middleware | JWT verification via JWKS, session validation |
| Request envelope | Normalize all inbound to `ButlerEnvelope` |
| Rate limiting | Token bucket via Redis with sliding window |
| Idempotency | Redis-backed idempotency key enforcement |
| Chat endpoint | `POST /api/v1/chat` → Orchestrator dispatch |
| RFC 9457 errors | All gateway errors use Problem Details |
| CORS & security headers | Production-ready HTTP security |

---

## Phase 3: Orchestrator & Durable Runtime

**Goal:** Brain of Butler — intent routing, planning, durable task execution.  
**Plan:** [04-phase-3-orchestrator.md](./04-phase-3-orchestrator.md)

| Deliverable | Description |
|-------------|-------------|
| Intake pipeline | Receive envelope → classify intent → select mode |
| Execution modes | Macro (LLM-driven), Routine (template), Durable Workflow |
| Task state machine | pending → running → awaiting_approval → completed/failed |
| Plan engine | Step decomposition, dependency graph execution |
| Approval system | Pause task → emit approval request → resume on grant |
| Compensation | Undo side-effects on failure |
| Persistence | All task state in PostgreSQL, hot state in Redis |
| Session history | Persist conversation turns with Memory |

---

## Phase 4: Memory, Tools & Search

**Goal:** The working loop — remember, act, and retrieve evidence.  
**Plan:** [05-phase-4-memory-tools-search.md](./05-phase-4-memory-tools-search.md)

### Memory Service
| Deliverable | Description |
|-------------|-------------|
| Episodic memory | Conversation turns, interaction traces |
| Entity/fact memory | Named entities with temporal versioning |
| Preference memory | User preferences with confidence scores |
| Hybrid retrieval | Dense (embeddings) + sparse (keyword) + graph |
| Context builder | Assemble relevant context for Orchestrator |

### Tools Service
| Deliverable | Description |
|-------------|-------------|
| Tool registry | YAML-defined tools with risk tiers |
| Execution engine | Sandboxed tool execution with timeouts |
| Verification | Pre/post execution checks |
| Idempotency | Prevent duplicate side-effects |
| Compensation registry | Undo actions for each tool |

### Search Service
| Deliverable | Description |
|-------------|-------------|
| Query understanding | Classify mode, extract features, rewrite |
| Provider routing | Google, Crawl4AI, direct fetch |
| Content extraction | Trafilatura + fallback pipeline |
| Evidence pack | Structured output with citations |

---

## Phase 5: ML, Realtime & Communication

**Goal:** Intelligence, live delivery, and multi-channel messaging.  
**Plan:** [06-phase-5-ml-realtime-communication.md](./06-phase-5-ml-realtime-communication.md)

### ML Service
| Deliverable | Description |
|-------------|-------------|
| Intent classifier | Tiered T0-T3 with confidence calibration |
| Embedding engine | Dense text embeddings via BGE |
| Model registry | Version tracking, rollout policies |
| Feature store | Online feature serving API |

### Realtime Service
| Deliverable | Description |
|-------------|-------------|
| WebSocket manager | Connection lifecycle with ticket auth |
| Event streaming | Typed events with durable/ephemeral split |
| Presence engine | Connected, idle, active-device states |
| Resume/replay | Reconnect with cursor-based replay |

### Communication Service
| Deliverable | Description |
|-------------|-------------|
| Policy layer | Consent, quiet hours, sender verification |
| Delivery runtime | Priority queues with retry policies |
| Provider adapters | SMS (Twilio), Email (SendGrid), Push (FCM) stubs |
| Webhook ingestion | Signed webhook verification |

---

## Phase 6: Security, Observability, Device/Vision/Audio

**Goal:** Hardening, monitoring, and ambient intelligence.  
**Plan:** [07-phase-6-security-observability-ambient.md](./07-phase-6-security-observability-ambient.md)

### Security Service
| Deliverable | Description |
|-------------|-------------|
| Trust classification | Input source → trust level mapping |
| Content defense | Injection detection, channel separation |
| Policy decision point | OPA-compatible allow/deny evaluation |
| Tool capability gates | Scoped capabilities with approval classes |
| Memory isolation | Purpose-bound retrieval with redaction |

### Observability Platform
| Deliverable | Description |
|-------------|-------------|
| OTel instrumentation | Traces, metrics, logs for all services |
| Butler semantic conventions | Workflow/task/tool span attributes |
| SLO definitions | Availability, latency, completion targets |
| Health dashboards | Grafana-ready metric exposition |

### Device / Vision / Audio
| Deliverable | Description |
|-------------|-------------|
| Device registry | Capability-based device model |
| Vision pipeline | Detection, OCR, reasoning API stubs |
| Audio pipeline | STT/TTS API with dual-model strategy stubs |

---

## Build Order (File-Level)

This is the exact sequence of files to create/modify:

### Phase 0 (Foundation)
```
backend/core/__init__.py
backend/core/errors.py                    ← RFC 9457 Problem Details
backend/core/envelope.py                  ← Canonical Butler envelope
backend/core/logging.py                   ← structlog + OTel setup
backend/core/health.py                    ← Health probe mixin
backend/core/deps.py                      ← Dependency injection
backend/core/middleware.py                ← Request ID, timing, error handler
backend/domain/base.py                    ← DomainService / Repository base
backend/api/__init__.py
backend/api/schemas/__init__.py
backend/api/schemas/common.py            ← Shared response schemas
backend/alembic.ini
backend/alembic/env.py
backend/alembic/versions/001_initial.py  ← Full Data spec schema
backend/tests/conftest.py                ← Test fixtures
backend/tests/factories.py              ← Test data factories
```

### Phase 1 (Auth)
```
backend/domain/auth/__init__.py
backend/domain/auth/models.py            ← ENRICH with Data spec fields
backend/domain/auth/contracts.py         ← AuthService interface
backend/domain/auth/exceptions.py        ← Auth-specific errors
backend/services/auth/__init__.py
backend/services/auth/service.py         ← AuthService implementation
backend/services/auth/jwt.py             ← REWRITE with proper JWKS doc
backend/services/auth/password.py        ← Argon2id hasher
backend/api/routes/auth.py               ← NEW routes (thin layer)
backend/api/schemas/auth.py              ← Request/response DTOs
backend/tests/unit/test_auth_service.py
backend/tests/unit/test_jwt.py
```

### Phase 2 (Gateway)
```
backend/domain/gateway/__init__.py
backend/domain/gateway/contracts.py       ← Gateway service interface
backend/services/gateway/__init__.py
backend/services/gateway/service.py       ← Gateway service implementation
backend/services/gateway/rate_limiter.py  ← Token bucket rate limiter
backend/services/gateway/idempotency.py   ← Idempotency enforcement
backend/services/gateway/auth_middleware.py ← JWT verification middleware
backend/api/routes/gateway.py             ← Chat + health endpoints
backend/api/schemas/gateway.py            ← Chat request/response DTOs
backend/tests/unit/test_gateway.py
backend/tests/unit/test_rate_limiter.py
```

### Phase 3 (Orchestrator)
```
backend/domain/orchestrator/__init__.py
backend/domain/orchestrator/models.py     ← Task, Workflow ORM models
backend/domain/orchestrator/contracts.py  ← OrchestratorService interface
backend/domain/orchestrator/state.py      ← Task state machine
backend/domain/orchestrator/exceptions.py
backend/services/orchestrator/__init__.py
backend/services/orchestrator/service.py  ← Orchestrator implementation
backend/services/orchestrator/intake.py   ← Envelope → intent → mode
backend/services/orchestrator/planner.py  ← Plan decomposition
backend/services/orchestrator/executor.py ← Durable step execution
backend/services/orchestrator/approval.py ← Approval request/grant
backend/api/routes/orchestrator.py        ← Internal routes
backend/api/schemas/orchestrator.py
backend/tests/unit/test_orchestrator.py
backend/tests/unit/test_task_state.py
```

### Phase 4 (Memory + Tools + Search)
```
backend/domain/memory/models.py
backend/domain/memory/contracts.py
backend/services/memory/service.py
backend/services/memory/episodic.py
backend/services/memory/entity.py
backend/services/memory/retrieval.py
backend/api/routes/memory.py
backend/api/schemas/memory.py

backend/domain/tools/models.py
backend/domain/tools/contracts.py
backend/domain/tools/registry.py
backend/services/tools/service.py
backend/services/tools/executor.py
backend/services/tools/verification.py
backend/api/routes/tools.py
backend/api/schemas/tools.py

backend/domain/search/contracts.py
backend/services/search/service.py
backend/services/search/query.py
backend/services/search/extraction.py
backend/services/search/retrieval.py
backend/api/routes/search.py
backend/api/schemas/search.py
```

### Phase 5 (ML + Realtime + Communication)
```
backend/services/ml/service.py
backend/services/ml/intent.py
backend/services/ml/embeddings.py
backend/services/ml/registry.py
backend/api/routes/ml.py

backend/services/realtime/manager.py
backend/services/realtime/events.py
backend/services/realtime/presence.py
backend/api/routes/realtime.py

backend/services/communication/service.py
backend/services/communication/policy.py
backend/services/communication/delivery.py
backend/api/routes/communication.py
```

### Phase 6 (Security + Observability + Device/Vision/Audio)
```
backend/services/security/service.py
backend/services/security/trust.py
backend/services/security/defense.py
backend/services/security/policy.py
backend/api/routes/security.py

backend/core/observability.py
backend/core/metrics.py
backend/core/tracing.py

backend/services/device/service.py
backend/services/vision/service.py
backend/services/audio/service.py
```

---

## Verification Strategy

### Per-Phase Gates

| Phase | Verification |
|-------|-------------|
| Phase 0 | `pytest` passes, `ruff check .` clean, Alembic migrates |
| Phase 1 | Register → login → get JWT → verify claims → refresh works |
| Phase 2 | `curl /api/v1/chat` with JWT → receives envelope → rate limit triggers |
| Phase 3 | Chat → intent → plan → execute tool → persist result → respond |
| Phase 4 | Memory stores/retrieves context; tools execute with verification |
| Phase 5 | WebSocket connects, receives live events; ML classifies intent |
| Phase 6 | OTel traces complete request flow; security gates block bad input |

### End-to-End Smoke Test

```bash
# 1. Register
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@butler.lasmoid.ai","password":"S3cur3!Pass"}' | jq -r .access_token)

# 2. Chat (triggers full pipeline)
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"What is the weather in SF?","session_id":"test-session"}'

# 3. Verify health
curl http://localhost:8000/api/v1/health/ready

# 4. Verify JWKS
curl http://localhost:8000/.well-known/jwks.json
```

---

## Risk Register

| Risk | Mitigation |
|------|-----------|
| Schema changes break existing code | Alembic migrations with rollback scripts |
| Circular imports between services | Domain contracts (interfaces) with runtime injection |
| LLM provider outages | Fallback chain with abstain mode |
| Redis failures | Graceful degradation — local cache fallback |
| Test database conflicts | Isolated test DB via pytest fixture |
| Phase 3 complexity explosion | Strict state machine with explicit transitions only |

---

## Convention Guide

### Directory Structure
```
backend/
├── api/              # HTTP-only: routes + schemas + middleware
│   ├── routes/       # Thin route handlers — NO business logic
│   └── schemas/      # Pydantic request/response DTOs
├── core/             # Cross-cutting: errors, logging, health, deps
├── domain/           # Business rules: models + contracts + exceptions
│   ├── auth/
│   ├── orchestrator/
│   ├── memory/
│   └── tools/
├── services/         # Application logic: implements domain contracts
│   ├── auth/
│   ├── gateway/
│   ├── orchestrator/
│   ├── memory/
│   ├── tools/
│   └── ...
├── infrastructure/   # External: DB, Redis, config
├── alembic/          # Database migrations
└── tests/            # Unit + integration tests
```

### Naming Conventions
- **Domain models:** `domain/{service}/models.py` (SQLAlchemy ORM)
- **Contracts:** `domain/{service}/contracts.py` (Protocol/ABC interfaces)
- **Service impl:** `services/{service}/service.py` (implements contracts)
- **Routes:** `api/routes/{service}.py` (thin HTTP layer)
- **Schemas:** `api/schemas/{service}.py` (Pydantic DTOs)
- **Errors:** RFC 9457 `type` URIs: `https://docs.butler.lasmoid.ai/problems/{error-slug}`

---

## Next Steps

1. **Start execution with Phase 0** — [01-phase-0-foundation.md](./01-phase-0-foundation.md)
2. Each phase plan contains the exact file list, code contracts, and verification steps
3. After each phase, run the phase gate verification before proceeding
4. Update this master plan if scope changes arise

---

*This plan covers 16 services, ~120 files, and represents the complete 0→100% implementation of the Butler backend.*
