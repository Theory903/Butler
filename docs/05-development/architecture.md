# Backend Architecture

> **For:** Engineers
> **Version:** 4.0
> **Last Updated:** 2026-04-18

---

## Overview

Butler backend is a **modular monolith** built with FastAPI. Services are logically separated but run together initially, with the ability to extract into microservices later.

---

## Project Structure

```
backend/
├── api/                    # HTTP layer
│   ├── routes/            # Route handlers
│   ├── schemas/           # Pydantic models
│   └── dependencies/      # FastAPI dependencies
│
├── domain/                # Business logic
│   ├── auth/              # Authentication domain
│   ├── orchestrator/     # Orchestration domain
│   ├── memory/            # Memory domain
│   └── ...
│
├── services/              # Service implementations
│   ├── auth_service.py
│   ├── orchestrator_service.py
│   └── ...
│
├── infrastructure/        # External dependencies
│   ├── database/          # PostgreSQL
│   ├── cache/            # Redis
│   ├── vector_store/      # Qdrant
│   └── external/          # OpenAI, Twilio, etc.
│
├── core/                  # Shared
│   ├── config/            # Configuration
│   ├── security/          # Security utilities
│   └── logging/           # Logging
│
└── main.py               # App factory
```

---

## Design Principles

### 1. Routes = HTTP Only

Routes should contain **zero business logic**:

```python
# BAD - Business logic in route
@router.post("/chat")
async def chat(request: ChatRequest):
    user = await db.get_user(request.user_id)
    intent = classify_intent(request.message)
    if intent == "email":
        send_email(user.email, request.message)
    return {"response": "sent"}
```

```python
# GOOD - Route delegates to domain
@router.post("/chat")
async def chat(request: ChatRequest, orch: OrchestratorService = Depends(get_orchestrator)):
    result = await orch.process_message(
        user_id=request.user_id,
        message=request.message
    )
    return result
```

### 2. Domain = Business Logic

Domains contain all business rules:

```python
# domain/orchestrator/service.py
class OrchestratorService:
    def __init__(self, memory: MemoryService, tools: ToolsService):
        self.memory = memory
        self.tools = tools
    
    async def process_message(self, user_id: UUID, message: str) -> Response:
        # Intent classification
        intent = await self._classify_intent(message)
        
        # Context retrieval
        context = await self.memory.retrieve(user_id, message)
        
        # Tool selection and execution
        result = await self.tools.execute(intent, context)
        
        # Memory update
        await self.memory.store(user_id, message, result)
        
        return Response(content=result)
```

### 3. Services = Application Orchestration

Services coordinate between domains and infrastructure:

```python
# services/orchestrator.py
class OrchestratorService:
    """Orchestrates the agent loop."""
    
    async def chat(self, request: ChatRequest) -> ChatResponse:
        # 1. Validate request
        # 2. Build context
        # 3. Classify intent
        # 4. Create plan
        # 5. Execute steps
        # 6. Verify results
        # 7. Update memory
        # 8. Return response
```

### 4. Domain Must NOT Import FastAPI

Boundaries must be clean:

```
routes/ → domain/ → services/ → infrastructure/
         ↓
      FastAPI NOT ALLOWED
```

---

## Service Architecture

### Gateway Service

```python
# api/routes/gateway.py
router = APIRouter(prefix="/api/v1")

@router.post("/chat")
async def chat(request: ChatRequest, auth: AuthDependency, orch: Orchestrator):
    return await orch.chat(request)
```

**Responsibilities:**
- Authentication
- Rate limiting
- Request validation
- Response formatting
- Error handling (RFC 9457)
- Circuit breaking

### Auth Service

**Responsibilities:**
- User registration/login
- JWT token generation/validation
- Session management
- Password hashing (Argon2id)

**API:**
```
POST /api/v1/auth/login
POST /api/v1/auth/register
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
GET  /.well-known/jwks
```

### Orchestrator Service

**Responsibilities:**
- Intent classification
- Context building
- Task planning
- Step execution
- Result verification

**API:**
```
POST /api/v1/orchestrator/chat
POST /api/v1/orchestrator/execute
GET  /api/v1/orchestrator/status/{task_id}
POST /api/v1/orchestrator/cancel/{task_id}
```

### Memory Service

**Responsibilities:**
- Preference storage
- Context retrieval
- Hybrid search (graph + vector + keyword)
- Memory importance scoring
- Memory editing/deletion

**API:**
```
POST /api/v1/memory/store
POST /api/v1/memory/retrieve
POST /api/v1/memory/search
PUT  /api/v1/memory/{id}
DELETE /api/v1/memory/{id}
```

### ML Service

**Responsibilities:**
- Embedding generation
- Intent classification
- Ranking/reranking
- Recommendation

**API:**
```
POST /api/v1/ml/embed
POST /api/v1/ml/intent
POST /api/v1/ml/rerank
POST /api/v1/ml/recommend
```

### Tools Service

**Responsibilities:**
- Tool registry
- Schema validation
- Execution sandboxing
- Result verification

**API:**
```
GET  /api/v1/tools
POST /api/v1/tools/execute
POST /api/v1/tools/verify
```

---

## Data Flow

### Request Flow: Chat

```
User
  ↓
Gateway (Auth + Rate Limit)
  ↓
Orchestrator.chat()
  ├→ ML.intent_classify()     # What does user want?
  ├→ Memory.retrieve()         # What's relevant?
  ├→ Tools.execute()           # Do the thing
  └→ Memory.store()           # Remember this
  ↓
Response
```

### Event Flow

```
User Action
  ↓
Event (user.message.received)
  ↓
Event Bus (Redis Streams)
  ├→ Memory Service (store)
  ├→ Analytics (track)
  └→ ML Service (learn)
```

---

## Database Schema

### Core Tables

```sql
-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'active'
);

-- Sessions
CREATE TABLE sessions (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    device_id VARCHAR(100),
    channel VARCHAR(20),
    assurance VARCHAR(10),
    started_at TIMESTAMP,
    ended_at TIMESTAMP
);

-- Messages
CREATE TABLE messages (
    id UUID PRIMARY KEY,
    session_id UUID REFERENCES sessions(id),
    role VARCHAR(20),
    content TEXT,
    intent VARCHAR(50),
    confidence FLOAT,
    created_at TIMESTAMP
);

-- Tasks
CREATE TABLE tasks (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    status VARCHAR(20),
    intent VARCHAR(50),
    plan JSONB,
    result JSONB,
    created_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

---

## Infrastructure

### PostgreSQL

- Primary data store
- Connection pooling via PgBouncer
- ORM: SQLAlchemy 2.0

### Redis

- Session cache
- Event bus (Streams)
- Rate limiting

### Qdrant

- Vector similarity search
- Memory embeddings
- RAG context retrieval

### Neo4j

- Graph relationships
- Entity connections
- Social graph

---

## Security Model

### Authentication

- JWT with RS256
- JWKS endpoint
- Short-lived access tokens
- Refresh token rotation

### Authorization

- Role-based access
- API key scoping
- Session assurance levels

### Data Protection

- TLS 1.3 in transit
- AES-256-GCM at rest
- Argon2id password hashing

---

## Observability

### Metrics

```
butler.requests.total
butler.requests.errors
butler.latency
butler.rate_limit.exceeded
```

### Tracing

- OpenTelemetry semantic conventions
- Trace per request
- Span per service

### Logging

- Structured JSON
- Correlation IDs
- Log levels: ERROR, WARN, INFO, DEBUG

---

## Service Boundaries

| Rule | Enforcement |
|------|------------|
| Gateway NEVER calls Memory | Code review |
| Auth owns identity | Architecture review |
| Security owns enforcement | Architecture review |
| Domain must NOT import FastAPI | Linter rule |

---

## Performance Targets

| Metric | Target |
|--------|--------|
| P50 Latency | <100ms |
| P95 Latency | <500ms |
| P99 Latency | <1.5s |
| RPS | 10K |
| Concurrent | 100K |

---

## Next Steps

1. **Setup**: [SETUP.md](./SETUP.md)
2. **Build order**: [build-order.md](./build-order.md)
3. **Run locally**: [run-local.md](./run-local.md)

*Architecture doc owner: Platform Team*
*Version: 4.0*