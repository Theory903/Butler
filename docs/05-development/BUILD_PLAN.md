# Butler Build Plan - 0 to 100%

> **Version:** 1.0  
> **Status:** Authoritative  
> **Philosophy:** Production-grade from day 1, incorporate Hermes as library, not product identity

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                     Butler Backend                    │
├────────────────────────────────────────────────────────────────────────┤
│  backend/                                              │
│  ├── api/              # HTTP routes + schemas            │
│  ├── domain/           # Business logic (Butler-owned)      │
│  ├── services/         # Service implementations          │
│  ├── infrastructure/   # DB, Redis, external       │
│  ├── core/            # Shared utilities           │
│  └── integrations/    # Hermes library (consumed)  │
│      └── hermes/       # Active library import   │
└────────────────────────────────────────────────────────────────────────┘
```

## Hermes Library Integration (How It Works)

We're **consuming Hermes as a library**, not adopting it as product. Pattern:

```python
# WRONG ❌ - Raw imports leaking service contracts
from backend.integrations.hermes.run_agent import AIAgent

# CORRECT ✅ - Butler-owned wrapper around Hermes implementation
from backend.domain.orchestrator.runtime_adapter import ButlerRuntimeAdapter
# runtime_adapter internally uses Hermes run_agent.py
```

| Hermes Module | Butler Owner | Usage Mode |
|------------|-----------|----------|
| `hermes/agent/context_engine.py` | Memory | Adapt wrapper |
| `hermes/agent/memory_provider.py` | Memory | Adapt wrapper |
| `hermes/agent/runtime.py` | Orchestrator | Adapt wrapper |
| `hermes/tools/registry.py` | Tools | Active wrapper |
| `hermes/hermes_state.py` | Memory | Active wrapper |
| `hermes/gateway/session.py` | Gateway | Adapt wrapper |
| `hermes/acp_adapter/auth.py` | Auth | Reference only |

---

## Phase 0: Project Structure (0-5%)

### Deliverables

```python
backend/
├── pyproject.toml           # uv/poetry project
├── uv.lock
├── .env.example
├── Makefile
├── docker-compose.yml
├── Dockerfile
├── ruff.toml
├── pyproject.toml
├── api/
│   ├── __init__.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── health.py
│   │   └── gateway.py
│   └── schemas/
│       ├── __init__.py
│       └── requests.py
├── domain/
│   ├── __init__.py
│   ├── auth/
│   │   ├── __init__.py
│   │   └── models.py
│   ├── gateway/
│   │   └── models.py
│   └── core/
├── services/
│   ├── __init__.py
│   └── auth.py
├── infrastructure/
│   ├── __init__.py
│   ├── database.py
│   └── cache.py
├── integrations/
│   └── hermes/  # SYMLINK TO backend/integrations/hermes
└── main.py
```

### Files to Create

| File | Purpose |
|------|---------|
| `backend/pyproject.toml` | Project config + dependencies |
| `backend/api/__init__.py` | API package |
| `backend/domain/__init__.py` | Domain package |
| `backend/services/__init__.py` | Services package |
| `backend/infrastructure/__init__.py` | Infrastructure package |
| `backend/main.py` | FastAPI app entrypoint |
| `backend/Makefile` | Build commands |
| `backend/.env.example` | Environment template |

### Dependencies

```toml
# core dependencies
fastapi = "^0.110.0"
uvicorn = {extras = ["standard"], version = "^0.27.0"}
pydantic = "^2.6.0"
pydantic-settings = "^2.2.0"

# auth & security
python-jose = {extras = ["cryptography"], version = "^3.3.0"}
python-multipart = "^0.0.9"
passlib = "^1.7.4"
argon2-cffi = "^23.1.0"

# database
sqlalchemy = "^2.0.0"
asyncpg = "^0.29.0"
alembic = "^1.13.0"

# cache & sessions
redis = "^5.0.0"

# observability
structlog = "^24.1.0"
sentry-sdk = {extras = ["fastapi"], version = "^1.40.0"}

# hermes integration (kept as library)
typing-extensions = "^4.9.0"

# dev
pytest = "^8.0.0"
pytest-asyncio = "^0.23.0"
ruff = "^0.3.0"
pyright = "^1.11.0"
httpx = "^0.26.0"
```

---

## Phase 1: Foundation (5-25%)

### 1.1 Database & Infrastructure

**Goal:** PostgreSQL + Redis ready for all services

| Component | Files | Features |
|----------|-------|---------|
| Database | `infrastructure/database.py` | SQLAlchemy async, connection pool |
| Migrations | `infrastructure/migrations/` | Alembic setup |
| Cache | `infrastructure/cache.py` | Redis async, sessions |
| Config | `infrastructure/config.py` | pydantic-settings |

**Schema (PostgreSQL):**
```sql
-- accounts (Auth)
CREATE TABLE accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- identities (Auth)
CREATE TABLE identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES accounts(id),
    provider VARCHAR(32) NOT NULL,
    provider_subject TEXT NOT NULL,
    password_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- sessions (Auth)
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES accounts(id),
    device_id TEXT,
    client_type VARCHAR(32),
    auth_method VARCHAR(32),
    assurance_level VARCHAR(16),
    refresh_family_id UUID,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ
);

-- token_families (Auth)
CREATE TABLE token_families (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(id),
    rotation_counter INTEGER DEFAULT 0,
    invalidated_at TIMESTAMPTZ
);
```

### 1.2 Gateway Service v3.1 (Port 8000)

**Goal:** RFC 9457 errors, JWT validation, rate limiting, idempotency

| Feature | Implementation |
|---------|------------|
| RFC 9457 | Custom exception handler returning Problem Details |
| JWT validation | python-jose with JWKS |
| Rate limiting | Token bucket in Redis |
| Idempotency | Redis store with TTL |
| Request envelope | Canonical Butler envelope builder |

**Endpoints:**
```python
# Basic
GET  /api/v1/health/live   # No auth
GET  /api/v1/health/ready  # No auth  
GET  /api/v1/health/startup
POST /api/v1/auth/login    # Auth: Optional (stub)

# Core  
POST /api/v1/chat        # Auth: Required
GET  /api/v1/stream/{id}  # Auth: Required

# Internal
GET  /.well-known/jwks.json  # For other services
```

**Files:**
| File | Purpose |
|------|---------|
| `services/gateway/__init__.py` | Gateway service |
| `services/gateway/routes.py` | HTTP routes |
| `services/gateway/middleware.py` | Auth, rate limit |
| `services/gateway/errors.py` | RFC 9457 handling |
| `services/gateway/rate_limit.py` | Token bucket |
| `services/gateway/idempotency.py` | Idempotency |

### 1.3 Auth Service v2.0 (Port 8001)

**Goal:** JWKS signing, passkeys first-class, token families, AAL

| Feature | Implementation |
|---------|------------|
| JWKS | RSA/ECDSA key management endpoint |
| Passkeys | WebAuthn registration + authentication |
| Token families | Rotation + replay detection |
| AAL assurance | AAL1/AAL2/AAL3-ish model |
| Step-up | ACR values and verification |

**Hermes Integration:**
```python
# Reference patterns from hermes/acp_adapter/auth.py
# Adapt for Butler token contracts
```

**Endpoints:**
```python
POST /auth/register
POST /auth/login
POST /auth/logout
POST /auth/refresh
GET  /auth/sessions
GET  /.well-known/jwks.json
POST /auth/passkeys/register/options
POST /auth/passkeys/register/verify
POST /auth/passkeys/authenticate/options
POST /auth/passkeys/authenticate/verify
```

**Files:**
| File | Purpose |
|------|---------|
| `services/auth/__init__.py` | Auth service |
| `services/auth/routes.py` | HTTP routes |
| `services/auth/jwt.py` | JWKS + token issuance |
| `services/auth/passkeys.py` | WebAuthn flows |
| `services/auth/sessions.py` | Session management |
| `services/auth/passwords.py` | Password hashing (Argon2id) |

### Phase 1 Verification

```bash
# Start services
docker-compose up -d db cache

# Test health
curl http://localhost:8000/api/v1/health/live

# Test login flow
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@ Butler.ai", "password": "test123"}'

# Should return JWT token and session_id
```

---

## Phase 2: Core Execution Path (25-50%)

### 2.1 Memory Service v2.0 (Port 8003)

**Goal:** Session store, context retrieval, entity resolution

| Feature | Implementation |
|---------|------------|
| Session store | Redis + PostgreSQL |
| Context retrieval | Temporal model |
| Entity resolution | Entity linking |

**Hermes Integration:**
```python
# Adapt from hermes/hermes_state.py
# Use hermes/agent/memory_provider.py behind wrapper
```

**Files:**
| File | Purpose |
|------|---------|
| `services/memory/__init__.py` | Memory service |
| `services/memory/routes.py` | HTTP routes |
| `services/memory/session_store.py` | Session persistence |
| `services/memory/context.py` | Context building |

### 2.2 ML Service (Port 8006)

**Goal:** Embeddings, intent classification

| Feature | Implementation |
|---------|------------|
| Embeddings | OpenAI/Anthropic embeddings |
| Intent classification | Simple classifier |

**Endpoints:**
```python
POST /ml/embed
POST /ml/classify_intent
GET  /ml/intent_model
```

**Files:**
| File | Purpose |
|------|---------|
| `services/ml/__init__.py` | ML service |
| `services/ml/routes.py` | HTTP routes |
| `services/ml/embeddings.py` | Embedding generation |
| `services/ml/intent.py` | Intent classification |

### 2.3 Tools Service v2.0 (Port 8005)

**Goal:** Tool registry, capability runtime, policy enforcement

| Feature | Implementation |
|---------|------------|
| Tool registry | Database-backed |
| Execution | Sandboxed execution |
| Policy | Approval gates |

**Hermes Integration:**
```python
# Use hermes/tools/registry.py behind Butler wrapper
# Adapt hermes/tools/process_registry.py
```

**Files:**
| File | Purpose |
|------|---------|
| `services/tools/__init__.py` | Tools service |
| `services/tools/routes.py` | HTTP routes |
| `services/tools/registry.py` | Tool registry |
| `services/tools/executor.py` | Execution sandbox |
| `services/tools/policy.py` | Policy checks |

### Phase 2 Verification

```bash
# Test memory
curl -X POST http://localhost:8000/api/v1/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"session_id": "test"}'

# Test ML
curl -X POST http://localhost:8000/api/v1/ml/embed \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"text": "hello"}'

# Test tools list
curl http://localhost:8000/api/v1/tools \
  -H "Authorization: Bearer $TOKEN"
```

---

## Phase 3: Orchestration (50-70%)

### 3.1 Orchestrator Service v2.0 (Port 8002)

**Goal:** Intent→Plan→Execute loop, durable execution

| Feature | Implementation |
|---------|------------|
| Intent parsing | ML service integration |
| Planning | Task DAG builder |
| Execution | Step-by-step with state |
| Durable execution | Redis-backed state machine |
| Interrupts | Cancellation support |

**Hermes Integration:**
```python
# Use hermes/run_agent.py behind ButlerRuntimeAdapter
# Wraps hermes/agent/context_engine.py
# Wraps hermes/agent/runtime.py
```

**Files:**
| File | Purpose |
|------|---------|
| `services/orchestrator/__init__.py` | Orchestrator service |
| `services/orchestrator/routes.py` | HTTP routes |
| `services/orchestrator/intent.py` | Intent parsing |
| `services/orchestrator/plan.py` | Planning |
| `services/orchestrator/execute.py` | Execution engine |
| `services/orchestrator/state.py` | Durable state |

### Phase 3 Verification

```bash
# Test chat flow
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello", "session_id": "test"}'

# Should return: response, request_id, session_id
```

---

## Phase 4: Realtime (70-80%)

### 4.1 Realtime Service v2.0 (Port 8004)

**Goal:** WebSocket, SSE, streaming events

| Feature | Implementation |
|---------|------------|
| WebSocket | Upgrade flow handling |
| SSE | Server-sent events |
| Streaming events | Token/tool/approval events |

**Hermes Integration:**
```python
# Reference hermes/gateway/stream_consumer.py patterns
```

**Endpoints:**
```python
WS /ws/chat
GET  /stream/{session_id}
```

### Phase 4 Verification

```bash
# Test WebSocket (example with wscat)
wscat -c ws://localhost:8000/ws/chat -H "Authorization: Bearer $TOKEN"
```

---

## Phase 5: Advanced (80-100%)

### 5.1 Search Service (Port 8012)

**Goal:** RAG pipeline

| Feature | Implementation |
|---------|------------|
| Indexing | Document chunking |
| Retrieval | BM25 + semantic |
| Ranking | Re-ranking |

### 5.2 Communication Service (Port 8013)

**Goal:** Push, email, SMS notifications

| Feature | Implementation |
|---------|------------|
| Push | Device notifications |
| Email | SMTP/SendGrid |
| SMS | Twilio/etc |

### 5.3 Vision + Audio Services

| Service | Port | Features |
|---------|------|---------|
| Vision | 8018 | Screen understanding |
| Audio | 8019 | STT, TTS |

---

## Phase 6: Full Integration (100%)

### Verification Checklist

- [ ] `/api/v1/chat` returns response within 500ms
- [ ] Session stores user + assistant messages
- [ ] Same session_id returns history
- [ ] Invalid token returns 401
- [ ] Rate limiting enforced
- [ ] Idempotency replay returns cached response
- [ ] JWKS validation works
- [ ] All services respond to health probes
- [ ] WebSocket streaming works
- [ ] Error responses use RFC 9457 format

---

## Build Commands

```bash
# Phase 0: Structure
make setup

# Phase 1: Foundation
make db-migrate
make db-seed
make build-auth
make build-gateway

# Phase 2: Core
make build-memory
make build-ml
make build-tools

# Phase 3: Orchestration  
make build-orchestrator

# Phase 4: Realtime
make build-realtime

# Phase 5: Advanced
make build-search
make build-communication

# Phase 6: Full
make test-integration

# Run all
make up
make down
make logs
```

---

## Directory Structure (Final)

```
backend/
├── pyproject.toml
├── Makefile
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── api/
│   ├── __init__.py
│   ├── routes/
│   │   ├── health.py
│   │   ├── gateway.py
│   │   ├── auth.py
│   │   ├── orchestrator.py
│   │   ├── memory.py
│   │   ├── ml.py
│   │   ├── tools.py
│   │   └── realtime.py
│   └── schemas/
│       ├── requests.py
│       └── responses.py
├── domain/
│   ├── auth/
│   │   └── models.py
│   ├── gateway/
│   │   └── models.py
│   ├── orchestrator/
│   │   └── models.py
│   └── core/
│       └── exceptions.py
├── services/
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── jwt.py
│   │   ├── passkeys.py
│   │   ├── sessions.py
│   │   └── passwords.py
│   ├── gateway/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── middleware.py
│   │   ├── errors.py
│   │   ├── rate_limit.py
│   │   └── idempotency.py
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── intent.py
│   │   ├── plan.py
│   │   ├── execute.py
│   │   └── state.py
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── session_store.py
│   │   └── context.py
│   ├── ml/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── embeddings.py
│   │   └── intent.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── registry.py
│   │   ├── executor.py
│   │   └── policy.py
│   └── realtime/
│       ├── __init__.py
│       ├── routes.py
│       ├── websocket.py
│       └── events.py
├── infrastructure/
│   ├── config.py
│   ├── database.py
│   ├── cache.py
│   └── migrations/
├── core/
│   ├── config.py
│   ├── security.py
│   └── exceptions.py
├── integrations/
│   └── hermes/  # SYMLINK to: backend/integrations/hermes
└── main.py
```

---

*Build plan owner: Platform Team*  
*Version: 1.0*