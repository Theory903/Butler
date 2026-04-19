# Data Flow (Runtime)

> **Purpose:** Real request journey through Butler  
> **Goal:** Concrete runtime path with proper boundaries, policy, observability
> **Version:** 2.0

---

## v2.0 Changes

- Fixed JWT validation (proper JWKS, not shared secret)
- Policy-gated tool execution
- Memory not just Redis list
- Four-state health model
- SLO-consistent timing
- Idempotency enforcement

---

## Example Request

User: "What's the weather in Tokyo?"

---

## 1. Client → Gateway

### Request

```http
POST /api/v1/chat
Authorization: Bearer <access_token>
Content-Type: application/json
Idempotency-Key: req_xyz789
Traceparent: 00-<trace>-<span>-01

{
  "message": "What's the weather in Tokyo?",
  "session_id": "sess_abc123",
  "request_id": "req_xyz789"
}
```

### Gateway Responsibilities

| Action | Implementation |
|--------|---------------|
| Transport termination | TLS 1.3 |
| Token validation | JWKS + RFC 9068 profile |
| Request normalization | Schema validation |
| Trace metadata | Add trace_id, span |
| Rate limiting | Sliding window |
| Quota enforcement | Per-user, per-endpoint |

### JWT Validation (Production)

**NOT this:**
```python
# WRONG - shared secret
jwt.decode(token, SECRET)
```

**THIS:**
```python
# CORRECT - proper validation
async def validate_token(self, token: str) -> TokenValidation:
    """Validate bearer access token per RFC 9068"""
    
    # 1. Get unverified header
    headers = jwt.get_unverified_header(token)
    
    # 2. Fetch JWKS
    jwks = await self.fetch_jwks()
    
    # 3. Get signing key
    key = jwks.get_key(headers.get("kid"))
    
    # 4. Validate claims
    claims = jwt.decode(
        token,
        key,
        algorithms=["RS256", "ES256"],
        issuer=self.config.issuer,
        audience=self.config.audience,
        options={
            "require": ["exp", "iss", "sub"],
            "verify_aud": True
        }
    )
    
    # 5. Check token type
    if claims.get("typ") != "at+jwt":
        raise InvalidTokenError("Wrong token type")
    
    return TokenValidation(
        user_id=claims["sub"],
        scopes=claims.get("scope", "").split(),
        assurance=claims.get("aal", "aal1")
    )
```

### Normalized Internal Request

```json
{
  "request_id": "req_xyz789",
  "trace_id": "trc_01abc123",
  "user_id": "user_123",
  "session_id": "sess_abc123",
  "message": "What's the weather in Tokyo?",
  "received_at": "2026-04-18T12:30:00Z",
  "channel": "mobile",
  "idempotency_key": "req_xyz789",
  "auth_context": {
    "subject": "user_123",
    "scopes": ["chat:send"],
    "assurance": "aal1"
  }
}
```

---

## 2. Gateway → Orchestrator

### Internal Call

```http
POST /orchestrate/process
X-Request-Id: req_xyz789
Traceparent: 00-<trace>-<span>-01

{
  "request_id": "req_xyz789",
  "trace_id": "trc_01abc123",
  "user_id": "user_123",
  "session_id": "sess_abc123",
  "message": "What's the weather in Tokyo?",
  "auth_context": {...}
}
```

### Boundary Enforcement

Gateway should NOT:
- Fetch memory directly
- Execute tools
- Generate response text
- Make policy decisions

That belongs to Orchestrator.

---

## 3. Orchestrator: Intent Understanding

### Step 3a: Intent/Entity Classification

```json
{
  "intent": "weather_lookup",
  "confidence": 0.96,
  "entities": {
    "location": "Tokyo"
  },
  "requires_tool": true,
  "clarification_needed": false
}
```

### Step 3b: Context Retrieval from Memory

```json
POST /memory/retrieve
{
  "user_id": "user_123",
  "session_id": "sess_abc123",
  "query": "What's the weather in Tokyo?",
  "types": ["session_history", "preferences", "recent_context"],
  "limit": 10
}
```

### Memory Response

```json
{
  "history": [
    {"role": "user", "content": "Hi"},
    {"role": "assistant", "content": "Hi. What do you need?"}
  ],
  "preferences": {
    "temperature_unit": "celsius"
  },
  "token_budget_used": 280,
  "retrieval_source": "hybrid"
}
```

**Memory is NOT just a Redis list.**

Memory provides:
- Session history with classification
- User preferences
- Semantic retrieval via Qdrant
- Graph relationships via Neo4j
- Writeback classification

---

## 4. Orchestrator: Policy-Aware Plan

### Execution Plan Creation

```json
{
  "plan_id": "plan_01abc",
  "steps": [
    {
      "type": "tool_call",
      "tool": "weather.get_current",
      "params": {
        "location": "Tokyo",
        "units": "celsius"
      },
      "idempotency_key": "req_xyz789:weather:get_current"
    }
  ],
  "approval_required": false,
  "policy_checked": true
}
```

### Policy Evaluation (OPA)

```python
async def evaluate_policy(
    self,
    plan: ExecutionPlan,
    context: ExecutionContext
) -> PolicyResult:
    """Evaluate execution plan against policy"""
    
    input_data = {
        "user": {
            "id": context.user_id,
            "tier": context.user_tier,
            "permissions": context.permissions
        },
        "tool": {
            "name": plan.steps[0].tool,
            "risk_tier": "low"
        },
        "approval": context.approval_state
    }
    
    result = await self.opa.evaluate("tool_execution", input_data)
    
    return PolicyResult(
        allow=result.allow,
        require_approval=result.require_approval,
        restrictions=result.restrictions
    )
```

---

## 5. Orchestrator → Tools

### Tool Execution Request

```json
POST /tools/execute
{
  "request_id": "req_xyz789",
  "user_id": "user_123",
  "session_id": "sess_abc123",
  "tool": "weather.get_current",
  "params": {
    "location": "Tokyo",
    "units": "celsius"
  },
  "idempotency_key": "req_xyz789:weather:get_current",
  "risk_tier": "low"
}
```

### Tool Responsibilities

| Action | Implementation |
|--------|---------------|
| Schema validation | JSON Schema check |
| Policy check | OPA evaluation |
| Credential resolution | Vault fetch + injection |
| Execution | Policy-gated runtime |
| Output verification | Schema + dangerous pattern scan |
| Audit | Immutable log + telemetry |

### Tool Result

```json
{
  "success": true,
  "tool": "weather.get_current",
  "result": {
    "location": "Tokyo",
    "temperature": 18,
    "unit": "celsius",
    "condition": "sunny"
  },
  "execution_time_ms": 145,
  "verification": {
    "schema_valid": true,
    "dangerous_pattern_scan": "passed"
  }
}
```

---

## 6. Orchestrator: Response Composition

### Assistant Response

```json
{
  "response_text": "Current weather in Tokyo is 18°C and sunny.",
  "intent": {
    "name": "weather_lookup",
    "confidence": 0.96
  },
  "tools_used": ["weather.get_current"],
  "memory_writeback": [
    {
      "type": "conversation_turn",
      "role": "user",
      "content": "What's the weather in Tokyo?"
    },
    {
      "type": "conversation_turn",
      "role": "assistant", 
      "content": "Current weather in Tokyo is 18°C and sunny."
    }
  ]
}
```

---

## 7. Orchestrator → Memory Writeback

### Writeback Request

```json
POST /memory/store
{
  "user_id": "user_123",
  "session_id": "sess_abc123",
  "entries": [
    {
      "type": "conversation_turn",
      "role": "user",
      "content": "What's the weather in Tokyo?"
    },
    {
      "type": "conversation_turn",
      "role": "assistant",
      "content": "Current weather in Tokyo is 18°C and sunny."
    }
  ]
}
```

### Memory Writeback Classification

```json
{
  "entry_types": {
    "conversation_turn": "history",
    "preference_update": "preference",
    "entity_extraction": "entity"
  },
  "retention": {
    "conversation_turn": "user_choice + 30 days",
    "preference": "forever",
    "entity": "session_scoped"
  },
  "indexing": {
    "conversation_turn": "hybrid",
    "entity": "semantic"
  }
}
```

---

## 8. Orchestrator → Gateway → Client

### Final Response

```json
{
  "request_id": "req_xyz789",
  "response": "Current weather in Tokyo is 18°C and sunny.",
  "intent": {
    "name": "weather_lookup",
    "confidence": 0.96
  },
  "tools_used": ["weather.get_current"],
  "timestamp": "2026-04-18T12:30:01Z"
}
```

---

## Runtime Diagram

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       ▼
┌──────────────────────────────────┐
│  GATEWAY                        │
│  ├─ Bearer token validation     │
│  ├─ Rate limit / quota         │
│  ├─ Request normalization     │
│  └─ Trace metadata           │
└──────┬───────────────────────┘
       │ Internal call
       ▼
┌──────────────────────────────────┐
│  ORCHESTRATOR                   │
│  ├─ Intent understanding       │
│  ├─ Context retrieval           │
│  ├─ Plan creation              │
│  ├─ Policy-aware selection    │
│  ├─ Response composition     │
│  └─ Memory writeback           │
└──────┬─────┬─────┬─────────────┘
       │     │    │
       ▼     ▼    ▼
┌──────────┬──────────┬──────────┐
│ Memory   │ Tools    │ Policy   │
│ (8003)  │ (8005)   │ (OPA)    │
│         │          │          │
│ retrieve│ execute │ evaluate│
│ store   │ verify  │ decide  │
└──────────┴──────────┴──────────┘
```

---

## Timing Model (Honest)

| Step | Target | Notes |
|------|--------|-------|
| Gateway processing | 5–20 ms | Token validation, rate limit |
| Intent understanding | 20–100 ms | Classification |
| Memory retrieval | 30–150 ms | Hybrid retrieval |
| Tool execution | 100–600 ms | External API call |
| Response composition | 20–100 ms | Text generation |
| Memory writeback | async / 10–50 ms | Background |
| **Total** | **200–1000 ms** | Typical realistic |

---

## Error Paths

### 1. Invalid Token (401)

```json
{
  "type": "https://docs.butler.ai/problems/authentication-failed",
  "title": "Authentication failed",
  "status": 401,
  "detail": "Access token is invalid or expired."
}
```

### 2. Memory Unavailable (Degraded)

- Return empty/cached context
- Continue request if possible
- Emit degraded-mode telemetry
- Alert on SLO breach

### 3. Tool Failure

```json
{
  "response": "I couldn't get the weather right now. Please try again.",
  "tools_used": ["weather.get_current"],
  "error": "provider_unavailable"
}
```

### 4. Policy Denial

- Deny execution
- Return safe refusal
- Audit the attempt

---

## Storage Model

| Storage | Use Case |
|---------|----------|
| **Redis** | Rate limits, hot cache, ephemeral context, streams |
| **PostgreSQL** | Users, sessions, workflow state, audit |
| **Qdrant** | Semantic memory retrieval |
| **Neo4j** | Graph relationships |

---

## Health Model (Four-State)

| Endpoint | Returns | Meaning |
|----------|---------|----------|
| `/health/startup` | "STARTING" / "HEALTHY" | Initialization |
| `/health/ready` | "HEALTHY" / "DEGRADED" / "UNHEALTHY" | Traffic eligibility |
| `/health/live` | "HEALTHY" / "UNHEALTHY" | Restart needed |
| `/health/degraded` | Status details | Partial failure |

---

## Anti-Patterns

| Anti-Pattern | Problem | Use Instead |
|--------------|---------|--------------|
| Shared secret JWT | Insecure | JWKS validation |
| Gateway fetches memory | Boundary violation | Orchestrator coordinates |
| Tool called directly from NL | No policy | Plan → Policy → Execute |
| Memory = Redis list | No structure | Classification system |
| One /health | Ambiguous | Four-state probes |

---

*Document owner: Architecture Team*  
*Version: 2.0 - Production Required*  
*Last updated: 2026-04-18*