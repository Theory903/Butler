# Build Order Guide

> **For:** Engineers
> **Version:** 4.0
> **Last Updated:** 2026-04-18

---

## Overview

This guide defines the **correct sequence** for building Butler services. Building in the wrong order causes integration pain, circular dependencies, and debugging trauma.

**Golden Rule:** Build dependencies first, consumers last.

---

## Phase 1: Foundation (Week 1-2)

Build these services first. Others depend on them.

### 1.1 Database & Infrastructure

| Service | Dependencies | Tests |
|---------|--------------|-------|
| PostgreSQL Schema | None | Migration tests |
| Redis Cache | None | Connection tests |
| Object Storage | None | Upload/download |

**Why first:** Every service needs persistence.

```bash
# Run migrations
alembic upgrade head

# Verify
psql -c "\dt" Butler
```

### 1.2 Auth Service

| Service | Dependencies | Tests |
|---------|--------------|-------|
| Auth | Database | Login, JWT, session tests |

**Why second:** Every subsequent service needs authentication.

```python
# Tests to write
tests/
├── test_login.py          # Credential validation
├── test_jwt.py            # Token generation/validation
├── test_session.py       # Session lifecycle
└── test_logout.py         # Session termination
```

### 1.3 Gateway (Basic)

| Service | Dependencies | Tests |
|---------|--------------|-------|
| Gateway | Auth (stub) | Routing, health, metrics |

**Why third:** Gateway is the entry point.

```python
# Routes to implement
/api/v1/health/live
/api/v1/health/ready
/api/v1/health/startup
/api/v1/auth/login  # stub for now
```

---

## Phase 2: Core Services (Week 2-3)

After foundation, build the core execution path.

### 2.1 Memory Service

| Service | Dependencies | Tests |
|---------|--------------|-------|
| Memory | Auth, Database | Store, retrieve, search |

**Why:** Orchestrator needs to look up context.

```bash
# Test with real embeddings
pytest tests/services/test_memory.py -v
```

### 2.2 ML Service (Basic)

| Service | Dependencies | Tests |
|---------|--------------|-------|
| ML | None | Embedding generation |

**Why:** Memory needs embeddings, Tools needs intent classification.

```python
# Tests to write
tests/
├── test_embed.py          # Embedding generation
└── test_intent.py         # Intent classification
```

### 2.3 Tools Service

| Service | Dependencies | Tests |
|---------|--------------|-------|
| Tools | Auth, Database | Registry, execution, sandbox |

**Why:** Orchestrator needs to execute actions.

```bash
# Test tool execution
pytest tests/services/test_tools.py -v
```

---

## Phase 3: Orchestration (Week 3-4)

Now build the brain that coordinates everything.

### 3.1 Orchestrator Service

| Service | Dependencies | Tests |
|---------|--------------|-------|
| Orchestrator | Auth, Memory, ML, Tools | Intent parsing, planning, execution |

**Why:** This is the brain. Everything else follows its decisions.

```python
# Tests to write
tests/
├── test_intent_parsing.py  # Extract intent + entities
├── test_planning.py        # Create task DAG
├── test_execution.py       # Execute steps
└── test_context.py         # Build context
```

### 3.2 Realtime Service

| Service | Dependencies | Tests |
|---------|--------------|-------|
| Realtime | Auth, Gateway | WebSocket, push notifications |

**Why:** Users expect real-time responses for long tasks.

---

## Phase 4: Integration (Week 4-5)

Now wire everything together.

### 4.1 Gateway (Full)

| Service | Dependencies | Tests |
|---------|--------------|-------|
| Gateway | All services | Load, rate limit, circuit breaker |

**Why:** Now wire to actual backend services.

```bash
# Full integration test
pytest tests/integration/test_full_flow.py -v
```

### 4.2 Communication Service

| Service | Dependencies | Tests |
|---------|--------------|-------|
| Communication | Auth | Push, email, SMS |

**Why:** Notifications for approvals and reminders.

---

## Phase 5: Advanced (Week 5+)

### 5.1 Search Service

| Service | Dependencies | Tests |
|---------|--------------|-------|
| Search | Auth, ML | RAG pipeline |

### 5.2 Device Service

| Service | Dependencies | Tests |
|---------|--------------|-------|
| Device | Auth | IoT control |

### 5.3 Vision Service

| Service | Dependencies | Tests |
|---------|--------------|-------|
| Vision | Auth, ML | Screen understanding |

### 5.4 Audio Service

| Service | Dependencies | Tests |
|---------|--------------|-------|
| Audio | Auth, ML | STT, TTS |

---

## Dependency Graph

```
                    ┌──────────────────────────────────────────────────┐
                    │                    GATEWAY                      │
                    │         (rate limit, auth, routing)             │
                    └──────────────────────────┬───────────────────┘
                                               │
                    ┌─────────────────────────┴───────────────────┐
                    │                  ORCHESTRATOR                 │
                    │        (intent → plan → execute)            │
                    └──────────────────────────┬────────────────────┘
                                             │
        ┌─────────────┬──────────────┬──────┴──────┬─────────────┐
        │             │              │             │             │
        ▼             ▼              ▼             ▼             ▼
┌─────────────┐ ┌──────────┐ ┌─────────────┐ ┌──────────┐ ┌──────────┐
│   MEMORY    │ │    ML    │ │   TOOLS    │ │ SEARCH  │ │  COMMS   │
│  (context)  │ │(embed)   │ │ (execute)  │ │ (RAG)   │ │ (notify) │
└─────────────┘ └──────────┘ └─────────────┘ └──────────┘ └──────────┘
        │             │              │             │             │
        └─────────────┴──────────────┴─────────────┴─────────────┘
                             │
                    ┌────────┴───────┐
                    │    DATABASE    │
                    │ (Postgres)     │
                    └────────────────┘
```

---

## Build Commands by Phase

### Phase 1: Foundation

```bash
# Database
make db-migrate
make db-seed

# Auth
make build-auth
pytest tests/services/test_auth.py
```

### Phase 2: Core

```bash
# Memory
make build-memory
pytest tests/services/test_memory.py

# ML
make build-ml
pytest tests/services/test_ml.py

# Tools
make build-tools
pytest tests/services/test_tools.py
```

### Phase 3: Orchestration

```bash
# Orchestrator
make build-orchestrator
pytest tests/services/test_orchestrator.py
```

### Phase 4: Integration

```bash
# Full gateway
make build-gateway-full
pytest tests/integration/test_full_flow.py

# Communication
make build-communication
pytest tests/services/test_communication.py
```

### Phase 5: Advanced

```bash
# Search
make build-search

# Device
make build-device

# Vision/Audio
make build-vision
make build-audio
```

---

## Verification Checklist

Before moving to next phase, verify:

- [ ] All tests pass (`pytest`)
- [ ] Lint passes (`ruff check .`)
- [ ] Type check passes (`pyright`)
- [ ] Integration tests pass
- [ ] Health endpoints respond (`/health/live`, `/health/ready`)
- [ ] Documentation updated

---

## Common Build Issues

### Circular Dependency

**Symptom:** ImportError when starting service.

**Fix:** Check dependency graph. Services should form a DAG, not a cycle.

### Missing Environment Variable

**Symptom:** ConfigurationError on startup.

**Fix:** Add to `.env` and reload.

### Test Database Conflicts

**Symptom:** Tests fail with foreign key errors.

**Fix:** Use test fixtures, separate test database.

---

## Next Steps

1. **Setup local**: [SETUP.md](./SETUP.md)
2. **Run locally**: [run-local.md](./run-local.md)
3. **Architecture**: [architecture.md](./architecture.md)

*Build order owner: Platform Team*
*Version: 4.0*