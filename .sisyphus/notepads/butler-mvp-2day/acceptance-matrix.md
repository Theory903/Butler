# Butler MVP Acceptance Matrix

## Alpha Service Contracts (from docs)

### 1. Auth Service (POST /api/v1/auth/login)
**Source:** `docs/product/mvp-services.md` lines 92-105, `docs/dev/run-first-system.md` lines 103-128

**Request:**
```json
{
  "email": "string (email format)",
  "password": "string"
}
```

**Success Response (200):**
```json
{
  "token": "string (JWT)",
  "user_id": "string"
}
```

**Error Response (401):**
```json
{
  "detail": "Invalid credentials"
}
```

### 2. Chat Service (POST /api/v1/chat)
**Source:** `docs/product/mvp-services.md` lines 44-46, `docs/system/first-flow.md` lines 22-33, `docs/dev/run-first-system.md` lines 133-153

**Request:**
```json
{
  "message": "string",
  "session_id": "string"
}
```

**Headers:**
```
Authorization: Bearer <token>
Content-Type: application/json
```

**Success Response (200):**
```json
{
  "response": "string",
  "request_id": "string",
  "intent": {
    "type": "string",
    "action": "string"
  }
}
```

**Error Response (401):**
```json
{
  "detail": "Could not validate credentials"
}
```

### 3. Session History Service (GET /api/v1/session/{id})
**Source:** `docs/product/mvp-services.md` lines 45-46, `docs/system/first-flow.md` lines 64-65, `docs/dev/run-first-system.md` lines 159-175

**Request:**
```
GET /api/v1/session/{session_id}
```

**Headers:**
```
Authorization: Bearer <token>
```

**Success Response (200):**
```json
{
  "messages": [
    {
      "role": "string (user|assistant)",
      "content": "string",
      "timestamp": "string (ISO 8601)"
    }
  ]
}
```

**Error Response (401):**
```json
{
  "detail": "Could not validate credentials"
}
```

**Error Response (404):**
```json
{
  "detail": "Session not found"
}
```

### 4. Health Check Endpoints
**Source:** `docs/dev/run-first-system.md` lines 77-99

**Endpoint:** `GET /health` (gateway)
**Expected Response:** `{"status": "ok"}`

**Service-specific health:** `GET /service-name/health` for each MVP service

## Alpha Exclusions (What's NOT in MVP)
**Source:** `docs/product/mvp-services.md` lines 109-126

- Realtime (WebSocket) - Polling works for MVP
- OAuth providers - Password auth only
- 2FA - Post-MVP security
- ML/embeddings - Simple keyword match
- Voice - Text-first MVP
- Vision - Text-first MVP
- Search - Basic string match
- Communication - In-app only
- Workflows - Manual triggers only
- Device/IoT - Post-MVP
- Observability - Print debugging OK
- Data analytics - Post-MVP
- Security threat detection - Basic auth only

## Hermes-Derived Risk Checklist

### 1. Config Corruption / Secret Leakage
**Risk:** Saving runtime-expanded config back to persisted state
**Butler Guardrail:** Never persist resolved secrets or merged defaults back to disk
**Implementation:** Keep raw env placeholders separate from resolved runtime settings

### 2. Gateway Startup Ambiguity
**Risk:** Startup fails without clear surface reason
**Butler Guardrail:** Expose exact startup failure reason in logs and health output
**Implementation:** Health checks must include actionable failure details

### 3. Message Loss Under Load
**Risk:** Pending-message overwrite losing earlier requests
**Butler Guardrail:** Preserve ordered processing per session, never overwrite earlier pending work
**Implementation:** Append-only persistence for chat transcripts, ordered message processing

### 4. Observability Duplication
**Risk:** Logging setup called multiple times causing duplication
**Butler Guardrail:** Initialize logging once, include correlation/request IDs
**Implementation:** Idempotent logging bootstrap with per-request context

### 5. Managed Tool Seam Drift
**Risk:** Environment/token resolution silently drifting
**Butler Guardrail:** Explicit and test-backed tool execution/config resolution
**Implementation:** Clear seams between gateway/token resolution, token freshness checks

## Verification Evidence Location
All task evidence should be stored in: `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`

## Implementation Notes
- Docs take precedence over existing code when contracts differ
- MVP limited to 5 services: Gateway, Auth, Orchestrator, Memory, Tools
- Golden path: login -> chat -> session history
- Modular monolith architecture with preserved service boundaries
- Test-first implementation required for all remaining work