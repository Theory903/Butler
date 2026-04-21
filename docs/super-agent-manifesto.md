# The OG Plan: Butler Super-Agent Master Manifesto (v1.0)

> **Authoritative Reference for Butler AI System**
> **Version:** 1.0
> **Date:** 2026-04-20
> **Status:** Production Ready

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [18 Canonical Services](#3-18-canonical-services)
4. [API Reference](#4-api-reference)
5. [Security Model](#5-security-model)
6. [Workflow Engine](#6-workflow-engine)
7. [Tool System](#7-tool-system)
8. [Data Architecture](#8-data-architecture)
9. [Operations](#9-operations)
10. [Implementation Guide](#10-implementation-guide)

---

## 1. Executive Summary

### 1.1 What is Butler?

Butler is an AI-powered personal assistant that executes tasks autonomously across digital and physical environments. The system is designed to handle 1 million users with 10,000 RPS peak throughput and P95 <1.5s latency.

### 1.2 Core Capabilities

| Capability | Description | Status |
|------------|------------|--------|
| Messaging | Send SMS/WhatsApp with contact lookup | ✅ |
| Search | Web search with RAG and source citation | ✅ |
| Reminders | Time/location-based, recurring | ✅ |
| Memory | Remember preferences, recall context | ✅ |
| Q&A | Factual questions with confidence scoring | ✅ |
| Voice | Full voice input/output (Phase 2) | 🔄 |
| Automation | Cross-app workflows (Phase 2) | 🔄 |
| Vision | Screen understanding (Phase 3) | 📋 |

### 1.3 Technology Stack

- **Frontend:** React Native (Expo)
- **Backend:** FastAPI (Python)
- **Database:** PostgreSQL + Neo4j + Qdrant + Redis
- **ML Runtime:** Dual-STT, SmartRouter (T0-T3)
- **Protocols:** HTTP/1.1, HTTP/2, WebSocket, gRPC, MCP, A2A/ACP

### 1.4 Design Principles

1. **Modular Monolith:** 18 canonical services designed for extraction-ready architecture
2. **Three Execution Layers:** Macro (orchestration), Routine (automation), Durable Workflow (multi-step)
3. **Hybrid Memory:** Graph (Neo4j) + Vector (Qdrant) + BM25 + Cross-encoder reranking
4. **Oracle-Grade:** RFC 9457 errors, four-state health model, security-first

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      CLIENTS                           │
│  (Mobile App, Web, WhatsApp, SMS, Voice, IoT)          │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      CDN/WAF                          │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    API GATEWAY (v3.1)                    │
│  - Transport termination                                  │
│  - Auth enforcement                                │
│  - Rate limiting                                  │
│  - Request normalization                          │
│  - Idempotency                                 │
└─────────────────────┬───────────────────────────────────┘
                      │
              ┌───────┴───────┐
              ▼               ▼
    ┌───────────────┐   ┌───────────────┐
    │   SYNC     │   │   ASYNC     │
    │   Gateway  │   │   Gateway   │
    └─────┬─────┘   └─────┬─────┘
          │               │
          ▼               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   ORCHESTRATION LAYER                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │  Intent   │  │   Plan    │  │ Execution │          │
│  │  Engine   │  │  Engine   │  │  Engine   │          │
│  └───────────┘  └───────────┘  └───────────┘          │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    SERVICE LAYER                           │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐  │
│  │ Memory │ │   ML   │ │ Tools  │ │ Search │ │ Realtime│  │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘  │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐  │
│  │ Device │ │ Vision │ │ Audio  │ │  Comm  │ │ Secur. │  │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘  │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     MEMORY LAYER                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │ PostgreSQL│  │  Neo4j  │  │ Qdrant  │  │  Redis   │ │
│  │ (relational)│ │ (graph) │ │(vector) │  │ (cache)  │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │
└───────────────────��─────────────────────────────────────┘
```

### 2.2 Service Boundaries

**Critical Rules:**
- Gateway NEVER calls Memory directly (always via Orchestrator)
- Auth + Security stay separate (defense in depth)
- Memory uses ML for embeddings, not vice versa
- Routes inject domain services (testability)
- Domain must NOT import FastAPI (boundary enforcement)

### 2.3 Four-State Health Model

```
STARTING → HEALTHY → DEGRADED → UNHEALTHY
   │         │          │         │
   └─────────┴──────────┴─────────┘
   
Each service implements:
- /health/live   - Is process alive?
- /health/ready  - Ready to serve traffic?
- /health/startup - Startup complete?
- /health/degraded - Operating but degraded
```

---

## 3. 18 Canonical Services

### 3.1 Service Matrix

| # | Service | Version | Type | Responsibilities |
|---|---------|---------|------|----------------|
| 1 | **Gateway** | 3.1 | Edge control, transport termination, auth, rate limiting |
| 2 | **Auth** | 3.1 | Identity, passkeys, OIDC, JWT families, sessions |
| 3 | **Orchestrator** | 3.1 | AI runtime, intent understanding, durable execution |
| 4 | **Memory** | 3.1 | Hybrid retrieval, temporal reasoning, user understanding |
| 5 | **ML** | 3.1 | Intent classification, recommendations, embeddings |
| 6 | **Search** | 3.1 | Web search, crawler, hybrid retrieval |
| 7 | **Tools** | 3.1 | Capability runtime, policy execution, MCP bridge |
| 8 | **Realtime** | 3.1 | Event streaming, typed events, resumable sessions |
| 9 | **Communication** | 3.1 | Multi-channel delivery, consent, provider failover |
| 10 | **Device** | 3.1 | Cross-device control, automation, ambient capture |
| 11 | **Vision** | 3.1 | Screen automation, OCR, multimodal reasoning |
| 12 | **Audio** | 3.1 | Speech processing, diarization, voice cloning |
| 13 | **Security** | 3.1 | Trust enforcement, PII redaction, content safety |
| 14 | **Observability** | 3.1 | Telemetry, OTel, SLO tracking |
| 15 | **Data** | 3.1 | Transactional backbone, domain schemas, RLS |
| 16 | **Workflow** | 3.1 | Durable execution, workflow engine |
| 17 | *(reserved)* | - | Future service |
| 18 | *(reserved)* | - | Future service |

### 3.2 Gateway Service (v3.1)

**Endpoints:**
- `POST /api/v1/chat` - Chat interface
- `POST /api/v1/stream/{session_id}` - Streaming response
- `WS /ws/chat` - WebSocket chat
- `GET /api/v1/tools` - List available tools
- `GET /health` - Health check

**Features:**
- Token bucket rate limiting
- Session continuity
- Idempotency keys
- JWT validation (JWKS)
- Request/response transformation

**Integrations:**
- Orchestrator (async processing)
- Auth/OIDC (authentication)
- Redis (caching, rate limiting)
- Hermes gateway helpers

### 3.3 Auth Service (v3.1)

**Endpoints:**
- `POST /auth/register` - User registration
- `POST /auth/login` - Login with credentials
- `POST /auth/refresh` - Refresh access token
- `GET /.well-known/jwks.json` - Public keys
- `POST /auth/passkeys/*` - Passkey operations

**Authentication Methods:**
- WebAuthn/Passkeys (primary)
- OIDC providers
- JWT with RS256/ES256 (never HS256)
- Refresh tokens (15min access/7day refresh)
- Argon2id password hashing

**Features:**
- Multi-account sessions
- Assurance levels (IAL1/IAL2)
- Token families
- Session management

### 3.4 Orchestrator Service (v3.1)

**Endpoints:**
- `POST /orchestrate/process` - Process user request
- `POST /orchestrate/resume` - Resume interrupted workflow
- `GET /orchestrate/status/{task_id}` - Task status

**Features:**
- Intent understanding (ButlerBlender)
- PlanEngine for task decomposition
- Durable execution with checkpointing
- Security guardrails (PII redaction)
- Parallel retrieval
- Workflow planning (DAG creation)

**Integrations:**
- Gateway (request intake)
- Memory (context retrieval)
- ML (intent classification)
- Tools (capability execution)
- PostgreSQL (state persistence)

### 3.5 Memory Service (v3.1)

**Endpoints:**
- `POST /memory/store` - Store memory
- `GET /memory/retrieve` - Retrieve memories
- `POST /memory/search` - Semantic search
- `GET /memory/graph/{entity_id}` - Knowledge graph

**Memory Types:**
- Episodic (conversations, events)
- Semantic (preferences, facts)
- Procedural (how to do things)
- Relational (entity connections)

**Hybrid Retrieval:**
- Graph (Neo4j) - Relationships
- Vector (Qdrant) - Semantic similarity
- BM25 - Keyword fallback
- Cross-encoder reranking

**Features:**
- Temporal reasoning
- Entity resolution
- User understanding layer
- Memory consolidation

### 3.6 ML Service (v3.1)

**Endpoints:**
- `POST /ml/intent/classify` - Classify user intent
- `POST /ml/embed` - Generate embeddings
- `POST /ml/rerank` - Rerank results
- `POST /ml/recommend` - Get recommendations

**SmartRouter Tiers:**
| Tier | Use Case | Latency | Cost |
|------|--------|--------|------|
| T0 | Common intents | <50ms | $0.001 |
| T1 | Standard queries | <200ms | $0.01 |
| T2 | Complex reasoning | <500ms | $0.10 |
| T3 | Deep research | <5s | $1.00 |

**Features:**
- Dual-STT strategy
- Model registry
- Retrieval→ranking cascade
- Intent alternatives

### 3.7 Tools Service (v3.1)

**Endpoints:**
- `GET /tools` - List tools
- `POST /tools/execute` - Execute tool
- `GET /tools/{name}/schema` - Tool schema
- `POST /tools/verify` - Verify execution

**Tool Categories:**
- Native (built-in Python)
- Hermes (Butler library)
- MCP (Model Context Protocol)
- Plugin (user-defined)

**Runtime Types:**
1. **manifest-only:** Metadata only
2. **MCP adapter:** External MCP server
3. **remote service:** HTTP proxy
4. **WASM sandbox:** Isolated execution

**Tool Execution Flow:**
```
1. Get tool from registry
2. Validate parameters
3. Check policy/gate
4. Execute in sandbox
5. Verify result
6. Return with status
```

### 3.8 Security Service (v3.1)

**Endpoints:**
- `POST /security/authorize` - Authorize action
- `POST /security/content/evaluate` - Evaluate content
- `POST /security/tool/validate` - Validate tool use

**Security Controls:**
- Trust classification (TRUSTED/MEDIUM_TRUST/UNTRUSTED)
- PII redaction
- Content safety evaluation
- Tool capability gates
- Prompt injection detection

**Encryption:**
- TLS 1.3 everywhere
- mTLS internal
- AES-256-GCM at rest
- Field-level encryption

---

## 4. API Reference

### 4.1 Base URLs

- **Production:** `https://api.butler.ai/v1`
- **Development:** `http://localhost:8000/v1`

### 4.2 Authentication

```bash
# Include JWT in Authorization header
Authorization: Bearer <jwt_token>

# Refresh token flow
POST /auth/refresh
{"refresh_token": "string"}
```

### 4.3 Core Endpoints

#### Chat

```bash
POST /api/v1/chat
{
  "message": "string",
  "user_id": "uuid",
  "session_id": "uuid",
  "context": {}
}
# Response: {"response": "string", "intent": "string", "confidence": 0.95}
```

#### Orchestrator

```bash
POST /orchestrate/process
{
  "text": "string",
  "context": {}
}
# Response: {"intent": "send_message", "confidence": 0.95, "entities": {}}

POST /orchestrate/execute
{
  "intent": "string",
  "entities": {},
  "context": {}
}
# Response: {"execution_id": "uuid", "status": "completed", "result": {}}
```

#### Memory

```bash
POST /memory/store
{
  "type": "episodic|semantic|procedural",
  "data": {},
  "user_id": "uuid"
}
# Response: {"id": "uuid", "success": true}

POST /memory/retrieve
{
  "query": "string",
  "user_id": "uuid",
  "limit": 5
}
# Response: [{"id": "uuid", "score": 0.95, "text": "..."}]
```

#### Tools

```bash
GET /tools
# Response: {"tools": [{"name": "string", "description": "..."}]}

POST /tools/execute
{
  "tool": "string",
  "params": {},
  "user_id": "uuid"
}
# Response: {"success": true, "result": {}, "verification": {}}
```

### 4.4 Error Handling (RFC 9457)

```json
{
  "error": {
    "code": "VALIDATION_001",
    "message": "Invalid parameters",
    "details": {}
  }
}
```

| Code | HTTP | Description |
|------|------|-------------|
| VALIDATION_001 | 400 | Invalid parameters |
| AUTH_001 | 401 | Invalid token |
| AUTH_002 | 401 | Expired token |
| PERMISSION_001 | 403 | Access denied |
| NOT_FOUND_001 | 404 | Resource not found |
| RATE_001 | 429 | Rate limited |
| INTERNAL_001 | 500 | Internal error |
| SERVICE_001 | 503 | Service unavailable |

### 4.5 Rate Limiting

Response headers:
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`

---

## 5. Security Model

### 5.1 Trust Boundaries

```
┌────────────────────────────────────────┐
│         UNTRUSTED (Client)              │
└─────────────┬──────────────────────────┘
              │ JWT
              ▼
┌────────────────────────────────────────┐
│         EDGE (Gateway)                   │
│  - Request sanitization               │
│  - Rate limiting                    │
│  - Auth validation                │
└─────────────┬──────────────────────────┘
              │ mTLS
              ▼
┌────────────────────────────────────────┐
│         INTERNAL (Services)            │
│  - Trust classification           │
│  - Channel separation          │
│  - Policy enforcement       │
└─────────────┬──────────────────────────┘
              │
              ▼
┌────────────────────────────────────────┐
│         SENSITIVE (Data)               │
│  - Field encryption            │
│  - PII redaction           │
│  - Audit logging          │
└────────────────────────────────────────┘
```

### 5.2 Data Classification

| Level | Data | Protection |
|-------|------|-----------|
| Public | Docs, code | None |
| Internal | Metrics | Auth required |
| Confidential | User data | Encryption |
| Restricted | Keys, tokens | Vault |

### 5.3 AI-Specific Security

OWASP Top 10 for LLMs addressed:
- ✅ Prompt injection detection
- ✅ Output validation
- ✅ Retrieval access control
- ✅ Model isolation
- ✅ Rate limiting (abuse prevention)

### 5.4 Key Management

- Envelope encryption with master keys in HSM
- Data encryption keys rotated every 90 days
- JWT keys rotated every 30 days
- Emergency procedures for key compromise

---

## 6. Workflow Engine

### 6.1 Three Execution Layers

#### Macro (Orchestration)
```typescript
interface Macro {
  id: UUID;
  name: string;
  trigger: 'text_pattern' | 'schedule' | 'manual';
  actions: MacroAction[];
  safety_class: 'safe_auto' | 'confirm' | 'restricted';
}
```

#### Routine (Automation)
```typescript
interface Routine {
  id: UUID;
  triggers: RoutineTrigger[];
  behavior: RoutineBehavior;
  enabled: boolean;
  status: 'active' | 'paused';
}
```

#### Durable Workflow (Multi-Step)
```typescript
interface Workflow {
  id: UUID;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  status: 'draft' | 'active' | 'paused' | 'completed' | 'failed';
  execution_policy: {
    timeout_sec: 86400;
    retry_policy: { max_attempts: 3 };
  };
}
```

### 6.2 Node Types

| Type | Description |
|------|-------------|
| trigger | Workflow initiation |
| action | Tool execution |
| condition | Branching logic |
| delay | Wait/sleep |
| approval | Human-in-loop |
| compensation | Rollback |

### 6.3 BWL (Butler Workflow Language)

```yaml
workflow:
  name: "Send Reminder"
  nodes:
    - id: "get_contact"
      type: "action"
      tool: "get_contact"
    - id: "check_time"
      type: "condition"
      expression: "time >= reminder_time"
    - id: "send_notification"
      type: "action"
      tool: "send_message"
  edges:
    - from: "get_contact"
      to: "check_time"
    - from: "check_time"
      to: "send_notification"
      condition: "true"
```

---

## 7. Tool System

### 7.1 Three Capability Systems

#### 1. Native Tools
- Built-in Python functions
- Direct import and execution
- Highest performance

#### 2. Hermes Tools
- Butler library functions
- Standardized schema
- Auto-documented

#### 3. MCP Tools
- Model Context Protocol
- External server integration
- Plugin architecture

### 7.2 Plugin Runtime Types

| Type | Execution | Isolation |
|------|-----------|-----------|
| manifest-only | None | N/A |
| MCP adapter | External process | Process |
| remote service | HTTP | Network |
| WASM sandbox | Extism | Sandbox |

### 7.3 Tool Registration Pipeline

```
1. Plugin Upload → POST /api/v1/plugins/upload
2. Validation → Schema check, required fields
3. Registration → Add to registry
4. Hot Reload → Refresh tool cache
5. Ready to Call → Available via /tools
```

### 7.4 Built-in Tools

| Tool | Description | Category |
|------|------------|----------|
| send_message | Send SMS/WhatsApp | communication |
| send_email | Send email | communication |
| get_weather | Weather lookup | information |
| web_search | Web search | information |
| set_reminder | Create reminder | productivity |
| create_task | Create task | productivity |
| get_contacts | contact lookup | data |

---

## 8. Data Architecture

### 8.1 PostgreSQL Schema

```sql
-- Users table
CREATE TABLE users (
  id UUID PRIMARY KEY,
  email VARCHAR(255) UNIQUE,
  phone VARCHAR(20),
  name VARCHAR(255),
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  last_active TIMESTAMP,
  status VARCHAR(20)
);

-- Sessions table
CREATE TABLE sessions (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  started_at TIMESTAMP,
  ended_at TIMESTAMP,
  device_info JSONB
);

-- Messages table
CREATE TABLE messages (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES sessions(id),
  role VARCHAR(20),  -- 'user'|'assistant'|'system'
  content TEXT,
  intent VARCHAR(100),
  confidence FLOAT,
  created_at TIMESTAMP
);

-- Tasks table
CREATE TABLE tasks (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES sessions(id),
  user_id UUID REFERENCES users(id),
  status VARCHAR(20),  -- 'pending'|'running'|'completed'|'failed'
  intent VARCHAR(100),
  plan JSONB,
  result JSONB,
  error TEXT
);

-- Preferences table
CREATE TABLE preferences (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  category VARCHAR(50),
  key VARCHAR(100),
  value JSONB
);
```

### 8.2 Neo4j Graph Schema

**Nodes:**
- User, Person, App, Workflow, Task, Preference, Conversation

**Relationships:**
- `(User)-[:KNOWS]->(Person)`
- `(User)-[:USES]->(App)`
- `(User)-[:CREATED]->(Workflow)`
- `(User)-[:PREFERS]->(Preference)`

### 8.3 Qdrant Collections

| Collection | Description | Dimensions |
|------------|-------------|------------|
| user_conversations | Session embeddings | 1024 |
| knowledge_base | Documentation | 1024 |
| embeddings_cache | Cached embeddings | 1024 |

### 8.4 Caching Strategy

| Data | TTL | Max Size |
|------|-----|---------|
| User sessions | 1h | 10MB |
| Embeddings | 24h | 100MB |
| Intent results | 1h | 50MB |

---

## 9. Operations

### 9.1 SLO Targets

| Metric | Target |
|--------|--------|
| Availability | 99.9% |
| Error rate | <1% |
| P99 latency | <1.5s |
| P95 latency | <500ms |

### 9.2 Incident Response

**Service Down:**
1. Check four-state health
2. Restart service
3. Check dependencies
4. Scale if needed
5. Rollback if post-deploy

**Database Failure:**
1. Verify primary down + replica lag <1s
2. Prevent split-brain (WAL flush)
3. Rebuild replicas (not pg_archivecleanup)
4. Use autovacuum (not VACUUM FULL)

**High Latency:**
1. Identify by service
2. Check resource exhaustion
3. Check cache hit rates
4. Check DB queries
5. Check external APIs

### 9.3 Deployment

**Environments:**
- Dev (local/mock)
- Staging (integration/test)
- Prod (real data)

**CI/CD Pipeline:**
1. PR checks (lint/type/unit tests)
2. Merge checks (integration/security)
3. Deploy to staging
4. Smoke tests
5. Deploy to production

### 9.4 Monitoring Dashboards

| Dashboard | Audience | Metrics |
|-----------|----------|----------|
| Executive | Leadership | Revenue, retention |
| Product | PM | Activation, funnels |
| ML Quality | Data team | Intent accuracy |
| Engineering | DevOps | Latency, errors |

---

## 10. Implementation Guide

### 10.1 MVP Build Order

**Phase 1: Foundation (9 hours)**
1. Gateway + Auth + JWT → 2 hours
2. Orchestrator intent parsing → 2 hours
3. Session history persistence → 1 hour
4. One starter tool → 2 hours
5. Orchestrator → Memory + Tools integration → 2 hours

**Phase 2: Expansion (16 hours)**
1. Memory hybrid retrieval → 4 hours
2. ML intent classification → 4 hours
3. WebSocket streaming → 2 hours
4. Multi-channel communication → 4 hours
5. Realtime events → 2 hours

**Phase 3: Intelligence (16 hours)**
1. Recommendations engine → 4 hours
2. Durable workflows → 4 hours
3. Plugin system → 4 hours
4. Observability → 4 hours

### 10.2 Quick Start

```bash
# Start system
docker-compose up -d
curl http://localhost:8000/health

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

### 10.3 Service Dependencies

```
Gateway
├── Auth
├── Orchestrator
│   ├── Memory
│   ├── ML
│   └── Tools
├── Realtime
├── Communication
└── Device

Memory
├── ML (embeddings)
├── Data
└── Neo4j/Qdrant/Redis

ML
├── Memory (context)
└── Tools (execution)

Realtime
├── Memory
└── Data
```

### 10.4 Code Quality Standards

- **Type Safety:** No `as any`, no `@ts-ignore`
- **Error Handling:** No empty catch blocks
- **Testing:** No deleting tests to "pass"
- **Security:** No hardcoded secrets

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| BWL | Butler Workflow Language |
| MCP | Model Context Protocol |
| RAG | Retrieval Augmented Generation |
| RFC 9457 | Problem Details for HTTP APIs |
| RLS | Row-Level Security |
| A2A/ACP | Agent-to-Agent / Agent Communication Protocol |
| JWKS | JSON Web Key Set |
| OTel | OpenTelemetry |

---

## Appendix B: File Structure

```
backend/
├── api/
│   ├── routes/         # HTTP endpoints
│   ├── schemas/       # DTOs
│   └── dependencies/   # FastAPI deps
├── domain/
│   ├── auth/         # Auth contracts
│   ├── orchestrator/   # Orchestrator contracts
│   ├── memory/       # Memory contracts
│   └── tools/        # Tool contracts
├── services/
│   ├── gateway/      # Gateway impl
│   ├── auth/        # Auth impl
│   ├── orchestrator/ # Orchestrator impl
│   ├── memory/      # Memory impl
│   └── ...
├── integrations/
│   └── hermes/      # Hermes tools
├── core/
│   ├── config/      # Configuration
│   ├── security/    # Security
│   ├── logging/    # Logging
│   └── middleware/  # Middleware
├── infrastructure/
│   ├── database/    # DB connection
│   ├── cache/     # Redis
│   └── queue/     # Message queue
└── main.py        # Entry point

docs/
├── 00-governance/   # Constitution, rules
├── 01-core/         # BRD, PRD, TRD, HLD, LLD
├── 02-services/     # Service specs
├── 03-reference/    # API, workflows, plugins
├── 04-operations/    # Runbooks, security
└── 05-development/  # Dev guides
```

---

## Appendix C: API Quick Reference

### Authentication
```bash
# Register
POST /api/v1/auth/register
{"email": "user@example.com", "password": "secret123", "name": "John"}

# Login  
POST /api/v1/auth/login
{"email": "user@example.com", "password": "secret123"}

# Refresh token
POST /api/v1/auth/refresh
{"refresh_token": "eyJ..."}
```

### Chat
```bash
# Send message
POST /api/v1/chat
{"message": "What's the weather?", "session_id": "uuid"}

# Stream response
WS /ws/chat?token=eyJ...
```

### Memory
```bash
# Store memory
POST /api/v1/memory
{"type": "preference", "key": "theme", "value": "dark"}

# Retrieve
GET /api/v1/memory?query=theme
```

### Tools
```bash
# List tools
GET /api/v1/tools

# Execute tool
POST /api/v1/tools/execute
{"tool": "send_message", "params": {"to": "+1234567890", "body": "Hello"}}
```

---

## 11. Implementation Details

### 11.1 Service Implementations

#### Auth Service
**File:** `services/auth/routes.py`

| Method | Handler | Description |
|--------|---------|--------------|
| `POST` | `register()` | Creates Account, Identity, Session, TokenFamily |
| `POST` | `login()` | Validates password, creates session + tokens |
| `POST` | `refresh()` | Validates refresh token, issues new access token |
| `GET` | `jwks()` | Exposes public JWKS document |

**Features:** Argon2id password hashing, RS256 JWT with token families, Session tracking with 30 day expiry

#### Orchestrator Service
**File:** `services/orchestrator/service.py`

| Method | Description |
|--------|-------------|
| `intake()` | Synchronous request pipeline (safety → redaction → routing → planning → execution) |
| `intake_streaming()` | Streaming SSE/WebSocket pipeline |
| `approve_request()` | Handles workflow approval decisions |
| `get_pending_approvals()` | Lists pending user approvals |
| `_trigger_compression()` | Triggers session history summarization |

**Features:** Input/output safety guards, PII redaction/restore pipeline, Context blending from memory, Durable workflow execution, Smart routing tiering, Automatic session compression at 20 turns

#### Memory Service
**File:** `services/memory/service.py`

| Method | Description |
|--------|-------------|
| `store()` | Stores memory with fact reconciliation/evolution |
| `recall()` | Semantic memory retrieval |
| `store_turn()` | Stores conversation turn + triggers understanding |
| `compress_session()` | Anchored iterative summarization |
| `build_context()` | Assembles full context pack for orchestrator |
| `end_session()` | Captures episode + triggers graph extraction |

**Features:** Memory evolution engine (contradiction/supersede detection), Entity resolution, Knowledge graph extraction, Anchored session summarization, Multi-tier memory storage

#### ML Runtime Service
**File:** `services/ml/runtime.py`

| Method | Description |
|--------|-------------|
| `execute_inference()` | Executes reasoning requests against model providers |
| `get_profile()` | Returns model configuration |

**Features:** Model registry with provider factory, Circuit breaker per provider, Adaptive load shedding (health-based), Concurrency control (semaphore), TriAttention support, Tiered rejection during degraded state

#### Tools Executor Service
**File:** `services/tools/executor.py`

| Method | Description |
|--------|-------------|
| `execute()` | Full tool execution pipeline (idempotency → validation → verification → dispatch → audit) |
| `compensate()` | Runs compensation handlers for failed tools |
| `validate_params()` | Validates parameters against tool schema |

**Features:** Idempotency caching (24h TTL), Parameter validation via JSON Schema, Pre/post execution verification, Full audit trail with redacted parameters, Sandbox profile selection (docker/process), Circuit breakers per risk tier

#### Gateway Transport Service
**File:** `services/gateway/transport.py`

| Class | Method | Description |
|-------|--------|-------------|
| `LeakyBucketRateLimiter` | `acquire()` | Rate limit token acquisition |
| `HermesTransportEdge` | `connect()` | Authenticates + establishes hardened WebSocket connection |
| `HermesTransportEdge` | `run_ping_pong_loop()` | Zombie connection detection |

**Features:** Layer 7 leaky bucket rate limiting (Redis-backed), Strict ping/pong timeouts, JWT authentication at transport boundary, Connection throttling, Backpressure handling

### 11.2 Domain Contracts

#### Auth Contract
```python
class AuthServiceContract(Protocol):
    async def register(self, email: str, password: str, name: str) -> Account: ...
    async def login(self, email: str, password: str) -> TokenPair: ...
    async def refresh(self, refresh_token: str) -> TokenPair: ...
    async def logout(self, session_id: UUID) -> None: ...
```

#### Orchestrator Contract
```python
class OrchestratorServiceContract(Protocol):
    async def intake(self, request: OrchestrationRequest) -> OrchestrationResponse: ...
    async def intake_streaming(self, request: OrchestrationRequest) -> AsyncIterator[Chunk]: ...
    async def approve_request(self, approval_id: UUID, decision: bool) -> ApprovalResult: ...
```

#### Memory Contract
```python
class MemoryServiceContract(Protocol):
    async def store(self, memory: Memory) -> MemoryResult: ...
    async def recall(self, query: RecallQuery) -> List[MemoryMatch]: ...
    async def build_context(self, session_id: UUID) -> ContextPack: ...
    async def end_session(self, session_id: UUID) -> Episode: ...
```

#### Tools Contract
```python
class ToolsServiceContract(Protocol):
    async def execute(self, tool_name: str, params: dict, user_id: UUID) -> ToolResult: ...
    async def compensate(self, execution_id: UUID) -> CompensationResult: ...
    async def validate_params(self, tool_name: str, params: dict) -> ValidationResult: ...
```

---

## 12. Complete API Routes

### 12.1 Gateway Routes

| Method | Path | Auth | Description |
|--------|------|-----|-------------|
| `POST` | `/api/v1/chat` | Bearer | Chat interface |
| `POST` | `/api/v1/chat/stream` | Bearer | Streaming chat |
| `GET` | `/api/v1/stream/{session_id}` | Bearer | Get stream |
| `WS` | `/api/v1/ws/chat` | Token | WebSocket chat |
| `POST` | `/api/v1/sessions/bootstrap` | Bearer | Bootstrap session |
| `GET` | `/api/v1/channels` | Bearer | List channels |
| `POST` | `/api/v1/voice/process` | Bearer | Voice processing |
| `GET` | `/health/live` | ❌ | Liveness probe |
| `GET` | `/health/ready` | ❌ | Readiness probe |
| `GET` | `/health/startup` | ❌ | Startup probe |

### 12.2 Auth Routes

| Method | Path | Auth | Description |
|--------|------|-----|-------------|
| `POST` | `/auth/register` | ❌ | User registration |
| `POST` | `/auth/login` | ❌ | Login |
| `POST` | `/auth/refresh` | ❌ | Refresh token |
| `POST` | `/auth/logout` | Bearer | Logout |
| `POST` | `/auth/switch` | Bearer | Switch account |
| `GET` | `/.well-known/jwks.json` | ❌ | JWKS |
| `GET` | `/auth/me` | Bearer | Current user |
| `POST` | `/auth/passkey/register/options` | Bearer | Passkey registration |
| `POST` | `/auth/passkey/register/verify` | Bearer | Verify passkey |
| `POST` | `/auth/passkey/login/options` | ❌ | Passkey login |
| `POST` | `/auth/passkey/login/verify` | ❌ | Verify login |
| `GET` | `/.well-known/openid-configuration` | ❌ | OIDC config |
| `POST` | `/auth/token` | ❌ | OAuth token |
| `GET` | `/auth/userinfo` | Bearer | User info |
| `GET` | `/auth/accounts` | Bearer | List accounts |
| `POST` | `/auth/accounts` | Bearer | Create account |
| `GET` | `/auth/sessions` | Bearer | List sessions |
| `DELETE` | `/auth/sessions/{sid}` | Bearer | Delete session |
| `POST` | `/auth/reauth` | Bearer | Re-authenticate |
| `POST` | `/auth/recovery/codes` | Bearer | Generate backup codes |
| `POST` | `/auth/recovery/redeem` | ❌ | Redeem backup code |
| `POST` | `/auth/password/reset/initiate` | ❌ | Password reset |
| `POST` | `/auth/password/reset/confirm` | ❌ | Confirm reset |

### 12.3 Orchestrator Routes

| Method | Path | Auth | Description |
|--------|------|-----|-------------|
| `POST` | `/orchestrator/intake` | Internal | Process request |
| `POST` | `/orchestrator/intake_streaming` | Internal | Streaming |
| `GET` | `/orchestrator/workflows/{id}` | Bearer | Get workflow |
| `GET` | `/orchestrator/approvals` | Bearer | List approvals |
| `POST` | `/orchestrator/approvals/{id}` | Bearer | Respond to approval |

### 12.4 Memory Routes

| Method | Path | Auth | Description |
|--------|------|-----|-------------|
| `POST` | `/memory/store` | Bearer | Store memory |
| `POST` | `/memory/recall` | Bearer | Recall memories |
| `POST` | `/memory/context` | Bearer | Build context |
| `POST` | `/memory/sessions/{sid}/end` | Bearer | End session |
| `GET` | `/memory/profile` | Bearer | User profile |

---

## 13. Code Examples

### 13.1 Authentication Flow

```python
from fastapi import APIRouter, Depends
from services.auth import AuthService

router = APIRouter()

@router.post("/auth/login")
async def login(request: LoginRequest, auth: AuthService = Depends()):
    # Validate credentials
    tokens = await auth.login(request.email, request.password)
    
    # Set secure cookie
    response = JSONResponse({"access_token": tokens.access})
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh,
        httponly=True,
        secure=True,
        samesite="lax"
    )
    return response
```

### 13.2 Chat Pipeline

```python
@router.post("/chat")
async def chat(
    request: ChatRequest,
    orchestrator: OrchestratorService = Depends(),
    auth: AuthService = Depends()
):
    # Validate JWT
    user = await auth.verify(request.token)
    
    # Process through orchestrator
    response = await orchestrator.intake(
        text=request.message,
        user_id=user.id,
        session_id=request.session_id
    )
    
    return response
```

### 13.3 Tool Execution

```python
@router.post("/tools/execute")
async def execute_tool(
    request: ToolRequest,
    executor: ToolExecutor = Depends()
):
    # Execute with full pipeline
    result = await executor.execute(
        tool_name=request.tool,
        params=request.params,
        user_id=request.user_id
    )
    
    return {
        "success": result.success,
        "result": result.data,
        "execution_id": result.execution_id
    }
```

### 13.4 Memory Storage

```python
@router.post("/memory/store")
async def store_memory(
    request: StoreMemoryRequest,
    memory: MemoryService = Depends()
):
    result = await memory.store(
        memory_type=request.type,
        data=request.data,
        user_id=request.user_id
    )
    
    return {"id": result.id, "success": True}
```

### 13.5 Streaming Response

```python
@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    orchestrator: OrchestratorService = Depends()
):
    async def generate():
        async for chunk in orchestrator.intake_streaming(
            text=request.message,
            user_id=request.user_id
        ):
            yield f"data: {chunk.json()}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )
```

---

## 14. Error Codes Reference

| Code | HTTP | Service | Description |
|------|------|---------|-------------|
| AUTH_001 | 401 | Auth | Invalid credentials |
| AUTH_002 | 401 | Auth | Token expired |
| AUTH_003 | 401 | Auth | Account locked |
| AUTH_004 | 403 | Auth | Insufficient permissions |
| GATEWAY_001 | 400 | Gateway | Invalid request format |
| GATEWAY_002 | 429 | Gateway | Rate limit exceeded |
| GATEWAY_003 | 503 | Gateway | Service overloaded |
| ORCHESTRATOR_001 | 400 | Orchestrator | Invalid intent |
| ORCHESTRATOR_002 | 400 | Orchestrator | Planning failed |
| ORCHESTRATOR_003 | 503 | Orchestrator | Execution timeout |
| MEMORY_001 | 400 | Memory | Storage failed |
| MEMORY_002 | 503 | Memory | Retrieval failed |
| TOOLS_001 | 400 | Tools | Invalid parameters |
| TOOLS_002 | 403 | Tools | Tool not allowed |
| TOOLS_003 | 503 | Tools | Execution failed |
| INTERNAL_001 | 500 | All | Internal error |
| SERVICE_001 | 503 | All | Service unavailable |

---

## 15. Advanced Patterns

### 15.1 Durable Execution Pattern

```python
class DurableExecutor:
    """Executes workflows with checkpoint/resume capability."""
    
    async def execute(self, workflow: Workflow, context: ExecutionContext):
        # Create execution record
        record = await self.db.create(ExecutionRecord(
            workflow_id=workflow.id,
            status="running",
            checkpoint=None
        ))
        
        try:
            for node in workflow.dag.topological_order():
                # Check for interruption
                if await self.is_interrupted(record.id):
                    # Save checkpoint and pause
                    await self.checkpoint(record)
                    return ExecutionResult(status="interrupted", checkpoint=record.checkpoint)
                
                # Execute node
                result = await self.execute_node(node, context)
                
                # Save checkpoint after each node
                record = await self.db.update(record.id,
                    checkpoint=result.state,
                    completed_nodes=[*record.completed_nodes, node.id]
                )
            
            return ExecutionResult(status="completed")
            
        except Exception as e:
            # Run compensation
            await self.compensate(record)
            raise
```

### 15.2 PII Redaction Pattern

```python
class PIIRedactionService:
    """Redacts PII from input/output."""
    
    DETECTORS = {
        "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "phone": r"\+?[1-9]\d{1,14}",
        "ssn": r"\d{3}-\d{2}-\d{4}",
        "credit_card": r"\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}"
    }
    
    def redact(self, text: str, preserve_tokens: list = None) -> str:
        """Replace PII with tokens."""
        for pii_type, pattern in self.DETECTORS.items():
            text = re.sub(pattern, f"[{pii_type}_redacted]", text)
        return text
    
    def restore(self, text: str, tokens: dict) -> str:
        """Replace tokens with original values."""
        for token_id, original_value in tokens.items():
            text = text.replace(f"[TOKEN_{token_id}]", original_value)
        return text
```

### 15.3 Idempotency Pattern

```python
class IdempotencyService:
    """Ensures safe retry with idempotency."""
    
    async def execute_idempotent(
        self,
        key: str,
        operation: Callable,
        ttl: int = 86400
    ):
        # Check cache
        cached = await self.redis.get(f"idempotent:{key}")
        if cached:
            return json.loads(cached)
        
        # Execute operation
        result = await operation()
        
        # Cache result
        await self.redis.setex(
            f"idempotent:{key}",
            ttl,
            json.dumps(result)
        )
        
        return result
```

### 15.4 Circuit Breaker Pattern

```python
class CircuitBreaker:
    """Prevents cascade failures."""
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = 0
        self.state = "closed"
        self.last_failure_time = None
    
    async def call(self, operation: Callable):
        if self.state == "open":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "half-open"
            else:
                raise CircuitBreakerOpen()
        
        try:
            result = await operation()
            if self.state == "half-open":
                self.state = "closed"
                self.failures = 0
            return result
        except Exception as e:
            self.failures += 1
            self.last_failure_time = time.time()
            if self.failures >= self.failure_threshold:
                self.state = "open"
            raise
```

### 15.5 Hybrid Memory Retrieval

```python
class HybridRetriever:
    """Combines graph, vector, and keyword search."""
    
    async def retrieve(self, query: str, user_id: UUID, limit: int = 5):
        results = []
        
        # 1. Vector search (Qdrant)
        vector_results = await self.qdrant.search(
            collection="user_conversations",
            query=query,
            limit=limit
        )
        results.extend(vector_results)
        
        # 2. Graph relationships (Neo4j)
        graph_results = await self.neo4j.query("""
            MATCH (u:User {id: $user_id})-[:KNOWS]->(e)
            WHERE e.name CONTAINS $query
            RETURN e
        """, {"user_id": user_id, "query": query})
        results.extend(graph_results)
        
        # 3. BM25 keyword search
        keyword_results = await self.elastic.search(
            index="conversations",
            query=query,
            limit=limit
        )
        results.extend(keyword_results)
        
        # 4. Cross-encoder reranking
        reranked = await self.reranker.rerank(query, results, top_k=limit)
        
        return reranked
```

---

## 16. Security Deep Dive

### 16.1 Trust Classification Model

```
┌─────────────────────────────────────────────────────────┐
│              TRUST CLASSIFICATION                   │
├─────────────────────────────────────────────────────────┤
│  TRUSTED          │  MEDIUM_TRUST    │  UNTRUSTED  │
│  (processed)     │  (sanitized)    │ (isolated) │
├─────────────────────────────────────────────────────────┤
│  • Auth tokens   │  • User input   │  • Web     │
│  • Internal    │  • Uploaded     │  • External │
│  • Config      │    files       │    APIs    │
│  • Database    │  • Search      │  • Webhooks│
│                 │    results     │           │
└─────────────────────────────────────────────────────────┘
```

### 16.2 Channel Pipeline

```python
class TrustChannelPipeline:
    """Processes content based on trust level."""
    
    async def process(self, content: str, classification: str):
        if classification == "TRUSTED":
            return content  # No processing needed
        
        elif classification == "MEDIUM_TRUST":
            # Sanitize and validate
            content = self.sanitize(content)
            content = self.validate(content)
            return content
        
        elif classification == "UNTRUSTED":
            # Full isolation with approval
            if await self.requires_approval(content):
                await self.request_human_approval(content)
            return self.isolate(content)
```

### 16.3 Tool Risk Tiers

| Tier | Actions | Approval | Examples |
|------|--------|----------|-----------|
| T1 (Low) | Read-only, no cost | Auto-approve | get_weather, search |
| T2 (Medium) | Limited write | Auto-approve | send_message |
| T3 (High) | Significant | User approval | send_money |
| T4 (Critical) | Irreversible | Dual approval | delete_data |

### 16.4 Encryption Hierarchy

```
┌────────────────────────────────────────────┐
│          ENCRYPTION KEY HIERARCHY         │
├────────────────────────────────────────────┤
│  Master Key (HSM)                         │
│    └─→ Data Encryption Key (DEK)           │
│        └─→ Field-Level Keys               │
│            └─→ Encrypted Fields          │
└────────────────────────────────────────────┘

Key Rotation Schedule:
- Master Key: Every 90 days
- DEK: Every 90 days  
- JWT Keys: Every 30 days
```

---

## 17. Scaling Patterns

### 17.1 Horizontal Scaling

```yaml
# Kubernetes deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gateway
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
  selector:
    matchLabels:
      app: gateway
  template:
    spec:
      containers:
      - name: gateway
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        readinessProbe:
          httpGet:
            path: /health/ready
          initialDelaySeconds: 10
        livenessProbe:
          httpGet:
            path: /health/live
          initialDelaySeconds: 5
```

### 17.2 Auto-Scaling

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: gateway-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: gateway
  minReplicas: 2
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Pods
    pods:
      metric:
        name: requests_per_second
      target:
        type: AverageValue
        averageValue: "100"
```

### 17.3 Database Connection Pooling

```python
# PgBouncer configuration
pgbouncer:
  listen_addr: 0.0.0.0
  listen_port: 6432
  pool_mode: transaction
  max_client_conn: 1000
  default_pool_size: 20
  min_pool_size: 5
  reserve_pool_size: 5
  reserve_pool_timeout: 5
```

### 17.4 Caching Strategy

| Data Type | Cache | TTL | Invalidation |
|----------|------|-----|-------------|
| User session | Redis | 1h | Logout |
| Intent results | Redis | 1h | New training |
| Embeddings | Redis | 24h | Model update |
| Preferences | Redis | 24h | Update |
| Graph edges | Redis | 1h | Graph update |
| API schemas | Local | 24h | Deploy |

---

## 18. Testing Strategy

### 18.1 Test Pyramid

```
           ┌─────────────┐
           │    E2E     │  (~10%)
           │   Tests    │
          ┌────────────┐
          │ Integration│  (~20%)
          │  Tests     │
         ┌────────────┐
         │   Unit     │  (~70%)
         │  Tests     │
        └────────────┘
```

### 18.2 Unit Test Example

```python
import pytest
from services.auth import AuthService
from domain.auth import Account, Identity

@pytest.fixture
def auth_service():
    return AuthService(db=MemoryDB(), redis=MemoryRedis())

@pytest.mark.asyncio
async def test_register_creates_account():
    service = auth_service()
    
    account = await service.register(
        email="test@example.com",
        password="secure123",
        name="Test User"
    )
    
    assert account.email == "test@example.com"
    assert account.name == "Test User"
    assert account.created_at is not None

@pytest.mark.asyncio
async def test_login_validates_password():
    service = auth_service()
    await service.register("test@example.com", "secure123", "Test")
    
    with pytest.raises(InvalidCredentials):
        await service.login("test@example.com", "wrong")
```

### 18.3 Integration Test Example

```python
@pytest.mark.asyncio
async def test_chat_end_to_end():
    # Setup
    auth = AuthService()
    orchestrator = OrchestratorService()
    memory = MemoryService()
    tools = ToolExecutor()
    
    # Register user
    user = await auth.register("test@example.com", "pass", "Test")
    
    # Chat
    response = await orchestrator.intake(
        text="What's the weather?",
        user_id=user.id,
        session_id=uuid4()
    )
    
    assert response.intent == "get_weather"
    assert response.actions is not None
```

### 18.4 Load Testing

```python
# k6 load test script
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 100 },  // Ramp up
    { duration: '5m', target: 100 }, // Stay at 100
    { duration: '2m', target: 0 }, // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const res = http.post('http://localhost:8000/api/v1/chat', 
    JSON.stringify({
      message: 'Hello',
      session_id: 'test-session'
    }),
    { headers: { 'Content-Type': 'application/json' } }
  );
  
  check(res, { 'status 200': (r) => r.status === 200 });
  sleep(0.1);
}
```

---

## 19. Monitoring & Observability

### 19.1 Key Metrics

| Metric | Type | Target |
|--------|------|--------|
| Request rate | Counter | 10K RPS |
| Latency P50 | Histogram | <100ms |
| Latency P95 | Histogram | <500ms |
| Latency P99 | Histogram | <1.5s |
| Error rate | Counter | <1% |
| Active sessions | Gauge | <50K |
| Workflow completion | Counter | >85% |

### 19.2 Tracing (OpenTelemetry)

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc import OTLPSpanExporter

trace.set_tracer_provider(TracerProvider())

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("orchestrator.intake")
async def orchestrate(request):
    # Span automatically captures:
    # - Duration
    # - Attributes (user_id, intent, etc.)
    # - Events (tool calls, errors)
    
    with tracer.start_as_current_span("planning") as span:
        span.set_attribute("planner.type", "fast")
        plan = await planner.create(request)
    
    with tracer.start_as_current_span("execution") as span:
        result = await executor.run(plan)
    
    return result
```

### 19.3 Logging

```python
import logging
from structlog import structlog

logger = structlog.get_logger()

# All logs must be structured JSON
logger.info(
    "tool_executed",
    tool="send_message",
    user_id=str(user_id),
    execution_time_ms=450,
    status="success"
)

# Log levels:
# - DEBUG: Detailed debugging
# - INFO: Normal operations
# - WARNING: Degraded performance
# - ERROR: Failures
# - CRITICAL: System down
```

---

## 20. Deployment

### 20.1 Docker Compose (Development)

```yaml
version: '3.8'
services:
  gateway:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://butler:butler@db:5432/butler
      - REDIS_URL=redis://redis
      - NEO4J_URI=bolt://neo4j:7687
      - QDRANT_URL=http://qdrant:6333
    depends_on:
      - db
      - redis
      - neo4j
      - qdrant
  
  db:
    image: postgres:15
    environment:
      POSTGRES_USER: butler
      POSTGRES_PASSWORD: butler
    volumes:
      - pgdata:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine
  
  neo4j:
    image: neo4j:5
    ports:
      - "7474:7474"
      - "7687:7687"
  
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"

volumes:
  pgdata:
```

### 20.2 Kubernetes (Production)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: butler-gateway
  labels:
    app: butler
    component: gateway
spec:
  replicas: 3
  selector:
    matchLabels:
      component: gateway
  template:
    metadata:
      labels:
        component: gateway
    spec:
      containers:
      - name: gateway
        image: butler/gateway:v1.0
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: butler-secrets
              key: database-url
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
```

---

## Glossary

| Term | Definition |
|------|------------|
| **A2A/ACP** | Agent-to-Agent / Agent Communication Protocol |
| **Argon2id** | Password hashing algorithm |
| **BWL** | Butler Workflow Language |
| **Chunk** | Streaming response segment |
| **DAG** | Directed Acyclic Graph |
| **Envelope Encryption** | Encryption with key hierarchy |
| **EWKS** | Encrypted JSON Web Key Set |
| **IAL** | Identity Assurance Level |
| **JWKS** | JSON Web Key Set |
| **MCP** | Model Context Protocol |
| **Neo4j** | Graph database |
| **OTel** | OpenTelemetry |
| **PII** | Personally Identifiable Information |
| **Qdrant** | Vector database |
| **RAG** | Retrieval Augmented Generation |
| **RFC 9457** | Problem Details for HTTP APIs |
| **RLS** | Row-Level Security |
| **RS256** | RSA signature with SHA-256 |
| **SLoE** | Service Level Objective |
| **SSE** | Server-Sent Events |
| **Token Family** | Related access/refresh tokens |
| **WS** | WebSocket |

---

## Document History

| Version | Date | Changes |
|----------|------|---------|
| 1.0 | 2026-04-20 | Initial comprehensive documentation |
| 1.1 | 2026-04-20 | Added implementation details and API routes |

---

> **End of Document**
> This is the authoritative source for Butler AI System. All team members should reference this document for implementation decisions.