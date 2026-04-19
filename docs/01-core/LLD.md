# LLD - Low Level Design

> **For:** All Engineers
> **Status:** v0.3 (Production-Ready)
> **Version:** 3.0
> **Reference:** Corrected specification with boundary fixes, RFC 9457 error model

---

## 1. Database Schema

### 1.1 PostgreSQL (Core Data)

```sql
-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(20),
    name VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_active TIMESTAMP,
    status VARCHAR(20) DEFAULT 'active',
    metadata JSONB DEFAULT '{}'
);

-- Sessions table
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    started_at TIMESTAMP DEFAULT NOW(),
    ended_at TIMESTAMP,
    device_info JSONB,
    context JSONB DEFAULT '{}'
);

-- Messages table
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(id),
    role VARCHAR(20) NOT NULL, -- 'user', 'assistant', 'system'
    content TEXT NOT NULL,
    intent VARCHAR(50),
    confidence FLOAT,
    created_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Tasks table (for tracking execution)
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(id),
    user_id UUID REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'pending', -- pending, running, completed, failed
    intent VARCHAR(50),
    plan JSONB,
    result JSONB,
    error TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- User preferences table
CREATE TABLE preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    category VARCHAR(50) NOT NULL, -- 'messaging', 'notifications', etc.
    key VARCHAR(100) NOT NULL,
    value JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, category, key)
);

-- Indexes
CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_messages_session ON messages(session_id);
CREATE INDEX idx_tasks_user ON tasks(user_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_preferences_user ON preferences(user_id);
```

### 1.2 Neo4j Schema (Graph Memory)

```cypher
// Nodes
CREATE CONSTRAINT user_unique IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE;
CREATE CONSTRAINT person_unique IF NOT EXISTS FOR (p:Person) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT app_unique IF NOT EXISTS FOR (a:App) REQUIRE a.id IS UNIQUE;
CREATE CONSTRAINT workflow_unique IF NOT EXISTS FOR (w:Workflow) REQUIRE w.id IS UNIQUE;
CREATE CONSTRAINT task_unique IF NOT EXISTS FOR (t:Task) REQUIRE t.id IS UNIQUE;

// Node types
// User - the app user
// Person - contacts, people user interacts with
// App - applications user has
// Workflow - automation workflows
// Task - completed tasks
// Preference - stored preferences
// Conversation - conversation threads

// Relationships
// (User)-[:KNOWS]->(Person)
// (User)-[:USES]->(App)
// (User)-[:CREATED]->(Workflow)
// (User)-[:PREFERS]->(Preference)
// (Person)-[:SENT_MESSAGE]->(Message)
// (User)-[:HAD_CONVERSATION]->(Conversation)
```

### 1.3 Qdrant Collections

```python
# Collection: user_conversations
# - session_id: user context
# - created_at: timestamp
# - intent: classified intent

# Collection: knowledge_base
# - source: url or doc
# - created_at: timestamp
# - topic: classification

# Collection: embeddings_cache
# - text: original text
# - model: embedding model used
# - created_at: timestamp
```

---

## 2. API Contracts

### 2.1 Gateway API

```yaml
POST /api/v1/chat
Request:
  {
    "message": "string",
    "user_id": "uuid",
    "session_id": "uuid (optional)",
    "context": {}
  }
Response:
  {
    "response": "string",
    "session_id": "uuid",
    "intent": "string",
    "confidence": "float"
  }

POST /api/v1/voice/process
Request:
  {
    "audio_data": "base64",
    "user_id": "uuid"
  }
Response:
  {
    "transcript": "string",
    "response": "string",
    "audio_data": "base64"
  }

GET /api/v1/memory/{user_id}
Response:
  {
    "preferences": {},
    "recent_context": [],
    "relationships": []
  }
```

### 2.2 Internal Service APIs

```yaml
# Orchestrator -> Memory
POST /memory/retrieve
Request:
  {
    "query": "string",
    "user_id": "uuid",
    "limit": 5
  }
Response:
  {
    "context": [],
    "preferences": {},
    "relationships": []
  }

POST /memory/store
Request:
  {
    "type": "preference|conversation|relationship",
    "data": {},
    "user_id": "uuid"
  }
Response:
  { "success": true }

# Orchestrator -> AI
POST /ai/intent
Request:
  {
    "text": "string",
    "context": {}
  }
Response:
  {
    "intent": "string",
    "entities": {},
    "confidence": "float"
  }

POST /ai/recommend
Request:
  {
    "user_id": "uuid",
    "context": {}
  }
Response:
  {
    "recommendations": [
      { "action": "string", "score": "float" }
    ]
  }

# Orchestrator -> Tools
POST /tools/execute
Request:
  {
    "tool": "string",
    "params": {},
    "user_id": "uuid"
  }
Response:
  {
    "success": true,
    "result": {},
    "verification": {}
  }
```

---

## 3. Core Component Designs

### 3.1 Intent Engine

```python
class IntentEngine:
    def __init__(self):
        self.classifier = BERTClassifier()
        self.embedder = BGEEmbedder()
        self.fallback_rules = {}
    
    async def classify(self, text: str, context: dict) -> IntentResult:
        # Step 1: Fast rules check
        if match := self._rule_match(text):
            return match
        
        # Step 2: ML classification
        intent = await self.classifier.predict(text)
        
        # Step 3: Confidence check
        if intent.confidence < 0.7:
            # Step 4: LLM fallback
            intent = await self._llm_classify(text)
        
        return intent
    
    async def _llm_classify(self, text: str) -> IntentResult:
        # Use LLM for ambiguous cases
        prompt = f"""Classify intent: {text}
Options: send_message, web_search, set_reminder, answer_question, run_automation"""
        result = await llm.complete(prompt)
        return IntentResult(
            intent=result.intent,
            confidence=0.8,
            entities=result.entities
        )
```

### 3.2 Memory Retrieval

```python
class HybridRetriever:
    def __init__(self):
        self.graph = Neo4jClient()
        self.vector = QdrantClient()
        self.keyword = BM25()
        self.reranker = CrossEncoder()
    
    async def retrieve(self, query: str, user_id: str, limit: int = 5):
        # Step 1: Generate query embedding
        query_embedding = await self.embedder.embed(query)
        
        # Step 2: Parallel search
        graph_results = await self.graph.search(user_id, query)
        vector_results = await self.vector.search(query_embedding, limit)
        keyword_results = await self.keyword.search(query, limit)
        
        # Step 3: Merge results
        merged = self._merge_results(
            graph_results,
            vector_results,
            keyword_results
        )
        
        # Step 4: Rerank
        reranked = await self.reranker.rerank(query, merged[:20])
        
        # Step 5: Build context
        return self._build_context(reranked[:limit])
```

### 3.3 Tool Execution Engine

```python
class ToolExecutor:
    def __init__(self):
        self.registry = ToolRegistry()
        self.sandbox = Sandbox()
        self.verifier = ActionVerifier()
    
    async def execute(self, tool_name: str, params: dict, user_id: str):
        # Step 1: Get tool
        tool = self.registry.get(tool_name)
        if not tool:
            raise ToolNotFound(tool_name)
        
        # Step 2: Validate schema
        validated = tool.validate(params)
        
        # Step 3: Sandbox execution
        result = await self.sandbox.run(
            tool.execute,
            validated,
            timeout=tool.timeout
        )
        
        # Step 4: Verify result
        if not await self.verifier.verify(result):
            raise VerificationFailed(tool_name)
        
        # Step 5: Log for learning
        await self._log_execution(tool_name, params, result)
        
        return result
```

---

## 4. Caching Strategy

### 4.1 Cache Layers

| Cache | TTL | Size | Purpose |
|-------|-----|------|---------|
| Redis: User session | 1h | 10MB | Active sessions |
| Redis: Embeddings | 24h | 100MB | Query embeddings |
| Redis: Intent results | 1h | 50MB | Known intents |
| CDN: Static assets | 7d | 1GB | JS, images |

### 4.2 Cache Invalidation

```python
# Write-through for preferences
async def update_preference(user_id, key, value):
    await db.preferences.upsert(user_id, key, value)
    await redis.delete(f"pref:{user_id}")

# Event-based for context
async def on_message(session_id):
    await redis.expire(f"context:{session_id}", 3600)
```

---

## 5. Event System

### 5.1 Event Types

```python
class EventType(str, Enum):
    # User events
    USER_MESSAGE = "user.message"
    USER_ACTION = "user.action"
    
    # System events
    INTENT_CLASSIFIED = "intent.classified"
    TOOL_EXECUTED = "tool.executed"
    TASK_COMPLETED = "task.completed"
    
    # ML events
    RECOMMENDATION_GENERATED = "recommendation.generated"
    PREDICTION_MADE = "prediction.made"
```

### 5.2 Event Schema

```json
{
  "event_id": "uuid",
  "type": "string",
  "timestamp": "ISO8601",
  "user_id": "uuid",
  "data": {},
  "trace_id": "uuid",
  "span_id": "string"
}
```

---

## 6. Error Handling

### 6.1 Error Codes

| Code | Meaning | Action |
|------|---------|--------|
| E001 | Invalid input | Return 400, show error |
| E002 | Auth failure | Return 401, redirect login |
| E003 | Rate limit | Return 429, retry after |
| E004 | Tool failure | Skip tool, notify user |
| E005 | LLM failure | Fallback to rules |
| E006 | Timeout | Retry, then fail gracefully |
| E999 | Unknown | Log, return generic error |

### 6.2 Error Response Format

```json
{
  "error": {
    "code": "E004",
    "message": "Tool execution failed",
    "details": {},
    "trace_id": "uuid"
  }
}
```

---

## 8. Protocol Standards

| Protocol | Standard | Implementation |
|----------|----------|----------------|
| HTTP | RFC 9110 | REST endpoints |
| WebSocket | RFC 6455 | Bidirectional realtime |
| SSE | HTML Standard | Streaming responses |
| Error | RFC 9457 | Problem Details |

---

## 9. Performance Targets

### 9.1 Latency Targets (P50/P95/P99)

| Operation | P50 | P95 | P99 |
|-----------|-----|-----|-----|
| Auth check | 5ms | 10ms | 20ms |
| Rate limit | 2ms | 5ms | 10ms |
| Validation | 1ms | 3ms | 5ms |
| Memory retrieve | 50ms | 100ms | 200ms |
| Tool execution | 100ms | 500ms | 1s |

### 9.2 Throughput Targets

| Metric | Target |
|--------|--------|
| Requests per pod | 500 RPS |
| Max connections | 10K per pod |
| WebSocket connections | 50K |

---

## 10. Error Handling Standards (RFC 9457)

All error responses MUST use RFC 9457 Problem Details format:

```json
{
  "type": "https://docs.butler.lasmoid.ai/problems/{error-type}",
  "title": "Error Title",
  "status": {http_code},
  "detail": "Human-readable description",
  "instance": "/api/v1/endpoint#req_xxx",
  "trace_id": "uuid"
}
```

Standard error types:
| Type URI | HTTP | Description |
|----------|------|-------------|
| invalid-request | 400 | Invalid request body |
| authentication-failed | 401 | Authentication failed |
| authorization-failed | 403 | Authorization failed |
| not-found | 404 | Resource not found |
| rate-limit-exceeded | 429 | Rate limit exceeded |
| internal-error | 500 | Internal error |
| bad-gateway | 502 | Upstream unavailable |
| service-unavailable | 503 | Maintenance mode |
| gateway-timeout | 504 | Upstream slow |

---

## 11. Observability Requirements

### 11.1 Metrics

| Metric | Type | Description |
|--------|------|-------------|
| butler.requests.total | Counter | Total requests |
| butler.requests.errors | Counter | Errors by code |
| butler.latency | Histogram | P50/P95/P99 |
| butler.rate_limit.exceeded | Counter | Rate limited |
| butler.auth.failures | Counter | Auth failures |

### 11.2 Logs

```json
{
  "timestamp": "2026-04-17T10:30:00Z",
  "level": "INFO",
  "trace_id": "abc123",
  "user_id": "user456",
  "endpoint": "/api/v1/chat",
  "latency_ms": 45,
  "status": 200
}
```

### 11.3 Alerts

| Alert | Condition |
|-------|-----------|
| High error rate | >1% errors for 5min |
| High latency | P99 >500ms for 5min |
| Pod restarts | >3 per minute |

---

## 12. Circuit Breaker Configuration

```python
# Circuit breaker for external services
breaker = CircuitBreaker(
    failure_threshold=0.5,  # 50% errors triggers open
    recovery_timeout=30,    # seconds
    half_open_requests=3,  # Test requests in half-open
    expected_exception=HTTPError
)
```

Service-specific thresholds:
| Service | Threshold | Fallback |
|---------|-----------|----------|
| LLM | >50% errors | Rules |
| Memory | >20% errors | Cache |
| Tools | >10% errors | Skip |

---

## 13. Retry Strategy

| Retry | Delay | Max |
|-------|-------|-----|
| 1st | 100ms | - |
| 2nd | 500ms | - |
| 3rd | 2s | - |
| Then | - | Fail |

---

## 14. Backwards Compatibility

**Version 1.0 → 3.0 changes:**

- Error format migrated to RFC 9457 Problem Details
- Circuit breaker patterns added
- Observability requirements standardized

**Migration path:**
1. Update error handling to RFC 9457 format
2. Add trace_id to all log entries
3. Implement circuit breaker for external services

---

## 15. Configuration Management

### 15.1 Feature Flags

```json
{
  "features": {
    "voice_input": true,
    "voice_output": false,
    "automation": true,
    "recommendations": true,
    "prediction": false,
    "beta_features": false
  },
  "limits": {
    "max_session_duration": 3600,
    "max_messages_per_session": 100,
    "max_tool_calls_per_request": 10
  }
}
```

---

*Document owner: Architecture Team*  
*Last updated: 2026-04-17*  
*Version: 3.0 (Production-Ready)*
