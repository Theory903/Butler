# Butler AI - Agent Knowledge Base

> **For:** Future OpenCode sessions
> **Version:** 3.1 (Oracle-Grade v2.0)
> **Updated:** 2026-04-18

---

## What This Project Is

**Butler** = Personal AI system (not a chatbot wrapper):
- Modular AI execution with **18 services**
- Crosses digital (API/email/search) + physical (IoT devices) environments
- Production target: 1M users, 10K RPS, P95 <1.5s
- Three execution layers: Macro / Routine / Durable Workflow

---

## Project Structure

```
Butler/
├── app/              # React Native (Expo) mobile app
├── backend/         # FastAPI modular monolith
│   ├── api/         # HTTP routes + schemas
│   ├── domain/      # Auth, orchestrator, memory, tools...
│   ├── services/    # 16 service implementations
│   ├── core/       # Config, security, logging, deps
│   └── tests/
├── docs/            # Documentation (v3.1)
├── docker-compose.yml  # Services: api, db, cache
└── test-mvp.sh      # Quick system test
```

---

## Commands

### Start System
```bash
docker-compose up -d
curl http://localhost:8000/health
```

### Test MVP
```bash
# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "test123"}'

# Chat
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "hello", "session_id": "test"}'
```

### Backend Dev
```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
pytest
ruff check .
```

### Mobile App
```bash
cd app
npx expo start -- --tunnel
```

---

## Documentation

**Start here for ANY work in docs/:**
- [docs/index.md](./docs/index.md) - AI-optimized navigation for docs/
- [docs/AGENTS.md](./docs/AGENTS.md) - Implementation defaults
- [docs/README.md](./docs/README.md) - System overview

**Docs follow v2.0 Oracle-grade patterns:**
- Four-state health: STARTING → HEALTHY → DEGRADED → UNHEALTHY
- JWT with JWKS (RS256, RFC 9068) - never HS256
- RFC 9457 error format (Problem Details)
- MCP-first plugins
- No VACUUM FULL (use autovacuum)

---

## System Design Rules

**Reference:** [docs/rules/SYSTEM_RULES.md](./docs/rules/SYSTEM_RULES.md) - v2.0 Oracle-Grade

Key v2.0 updates:
- RFC 9457 Problem Details (not custom envelopes)
- No universal success envelopes
- Split health probes (/health/live, /health/ready, /health/startup)
- JWT: RS256/ES256 with JWKS, NO HS256, validate issuer/audience
- Password hashing: Argon2id (OWASP minimum)
- OpenTelemetry semantic conventions for tracing

---

## Critical Service Boundaries

| Rule | Why |
|------|-----|
| **Gateway NEVER calls Memory directly** | Always via Orchestrator |
| Auth + Security stay separate | Defense in depth |
| Memory uses ML for embeddings, not vice versa | Clean dependency |
| Routes inject domain services | Testability |
| Domain must NOT import FastAPI | Boundary enforcement |

---

## Backend Architecture (from backend/AGENTS.md)

```
backend/
├── api/routes/      # HTTP only - NO business logic
├── api/schemas/     # Request/response DTOs
├── domain/*/        # Business rules + contracts
├── infrastructure/ # Redis, Postgres, external providers
├── services/*/     # Application orchestration
└── main.py         # App assembly ONLY
```

---

## Key Files for Context

| Need | File |
|------|------|
| Service specs | docs/services/{service}.md |
| Runbooks | docs/runbooks/ |
| Security | docs/security/SECURITY.md |
| Dev setup | docs/dev/SETUP.md |
| Build sequence | docs/dev/build-order.md |

---

## Do NOT Do

- No business logic in route files
- No fake encryption in security service  
- No hardcoded secrets in service modules
- No module-level mutable state for auth/session
- No service coupling through route imports

---

## First Production Slice (per backend/AGENTS.md)

1. auth login + JWT (RS256)
2. authenticated chat entrypoint
3. session history persistence
4. one real starter tool
5. orchestrator uses memory + tools through interfaces

---

## External Technology Research

Reference: `.ref/EXTERNAL_TECH.md` - Research on external libraries

| Technology | License | Butler Fit | Status |
|------------|---------|------------|----------|
| pyturboquant | MIT | **RECOMMENDED** | Direct integration |
| TriAttention | Apache-2.0 | **RECOMMENDED** | Direct integration |
| twitter/the-algorithm | AGPL-3.0 | Design only | Legal review needed |
| twitter/the-algorithm-ml | AGPL-3.0 | Design only | Legal review needed |
| twitter-server | Apache-2.0 | Patterns | Service templates |

### Adoption Roadmap

**Phase 1 (Immediate):**
- Add TurboQuantMemoryBackend to Memory service (compressed recall tier)
- Add TriAttention vLLM provider to ML Runtime

**Phase 2 (Near-term):**
- Candidate retrieval layer
- User signal store
- Lightweight ranker

**Phase 3 (Future):**
- Heavy ranker
- ButlerHIN embeddings
- Action Mixer layer

---

*When in doubt: read docs/index.md first*