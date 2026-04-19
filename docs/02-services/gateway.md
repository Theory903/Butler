# Gateway Service - Technical Specification

> **For:** Engineering  
> **Status:** Active (v3.1) [GAPS: Reasoning Redaction, MCP]
> **Version:** 3.1  
> **Reference:** Butler-native edge gateway with explicit transport boundaries, RFC 9457 errors, and protocol-specific policy enforcement

---

## 1. Service Overview

### 1.1 Purpose
The Gateway service is the **edge control plane** for Butler. It terminates client-facing transports, normalizes requests into a Butler request envelope, enforces shared policy, and forwards work to the correct internal boundary.

### 1.2 Responsibilities
- Transport termination for HTTP, SSE, WebSocket, MCP, and limited internal protocols
- Authentication enforcement for human and machine actors
- Authorization checks that are safe to perform at the edge
- Request normalization into a canonical Butler envelope
- Idempotency handling for side-effecting public requests
- Rate limiting, quotas, and stream concurrency protection
- Response shaping, error normalization, and trace propagation
- Session bootstrap and transport continuity metadata

### 1.3 Boundaries

**GATEWAY OWNS:**
- transport termination
- protocol normalization
- auth enforcement
- edge-safe authorization checks
- request envelope shaping
- rate limiting and quotas
- idempotency enforcement
- trace / request / correlation IDs
- routing to the correct upstream boundary

**GATEWAY DOES NOT OWN:**
- memory retrieval
- direct memory persistence
- tool execution
- approval decisions
- agent lifecycle logic
- business rules
- long-running workflow state
- inference or model selection
- direct domain data access

### 1.4 Critical Butler Routing Rule

For Butler:
- **public human-facing traffic** goes through Gateway and usually lands on Orchestrator
- **internal control traffic** must use internal ingress or service-mesh policy, not the public default path
- **specialized direct routes** are allowed only when explicitly justified as edge-safe and documented

Gateway **never** calls Memory directly for retrieval or persistence. The golden path remains:

**Client → Gateway → Orchestrator → Memory / Tools / ML → Gateway response**

### 1.5 Hermes Library Integration
Gateway may reuse selective Hermes gateway helpers as an internal library, especially:

- `backend/integrations/hermes/gateway/session.py`
- `backend/integrations/hermes/gateway/session_context.py`
- `backend/integrations/hermes/gateway/delivery.py`
- `backend/integrations/hermes/gateway/channel_directory.py`

These are request-context and routing helpers, not product-defining behavior.

**Critical Boundary:** Gateway may use Hermes session helpers for request-context tracking only. It **MUST NOT** write directly to `hermes_state.py`, `state.py`, or any memory backend. All persistence still flows through the documented Butler path: Gateway → Orchestrator → Memory.

Gateway must **not** let the following redefine Butler transport behavior:

- `mcp_serve.py` (stdio/operator surface)
- `cli.py` / `rl_cli.py`
- raw ACP operator workflows
- platform-specific channel adapters under `gateway/platforms/*` before explicit promotion into Butler services

See `docs/services/hermes-library-map.md` for the full compatibility map.

---

## 2. Architecture

### 2.1 Edge Architecture

```text
                ┌────────────────────────────┐
                │       Edge Ingress         │
                │ CDN / WAF / TLS / H3       │
                └────────────┬───────────────┘
                             │
                  ┌──────────┴──────────┐
                  │   Gateway Runtime   │
                  ├──────────────────────┤
                  │ 1) Transport Adapter │
                  │   - HTTP/REST        │
                  │   - WebSocket        │
                  │   - SSE              │
                  │   - MCP HTTP         │
                  │   - Internal gRPC    │
                  ├──────────────────────┤
                  │ 2) Shared Policy     │
                  │   - authn/authz      │
                  │   - quotas           │
                  │   - idempotency      │
                  │   - tracing          │
                  │   - validation       │
                  ├──────────────────────┤
                  │ 3) Route Dispatch    │
                  │   - orchestrator     │
                  │   - media ingress    │
                  │   - session bootstrap│
                  │   - internal control │
                  └──────────┬───────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
   Orchestrator         Edge-safe services   Internal control ingress
   (primary path)       (health/media/etc.) (A2A/ACP, tool plane)
```

### 2.2 Dependencies

| Dependency | Type | Purpose |
|------------|------|---------|
| Redis | External | token bucket state, idempotency store, stream resume cache |
| Orchestrator | Internal | primary business-flow boundary |
| Auth / OIDC provider | Internal / External | token validation, user claims |
| Internal ingress / mesh | Internal | machine-to-machine policy |
| Hermes gateway helpers | Internal library | session and delivery compatibility patterns |

### 2.3 Transport Policy Model

Not every transport uses literally identical middleware. WebSocket upgrade flows, SSE streams, MCP framing, and gRPC metadata are all different in practice.

The correct rule is:

1. **transport-specific adapter**
2. **shared policy enforcement**
3. **route dispatch**
4. **transport-specific response encoder**

This gives Butler consistent auth, quotas, tracing, and error semantics without pretending every protocol is the same shape.

### 2.4 Protocol Support

| Protocol | Purpose | Exposure | Support level |
|----------|---------|----------|---------------|
| HTTP/1.1 | browser / API clients | Public | Native |
| HTTP/2 | mobile / efficient clients | Public | Native |
| HTTP/3 | edge ingress only | Public edge | Terminated at ingress |
| WebSocket | bidirectional realtime sessions | Public | Native |
| SSE | token/status streams | Public | Native |
| gRPC | internal service calls | Internal only | Native internal |
| MCP Streamable HTTP | model-context integration | Public / partner | Targeted compatibility |
| A2A / ACP-style control | internal agent control | Internal only | Butler-owned internal envelope |

**Important:**
- MCP support should be described as **targeting Streamable HTTP compatibility** and validated through a supported client matrix, not assumed universal by prose alone.
- ACP is treated here as a **Butler internal control envelope**, not a magically universal standard.

---

## 3. Canonical Butler Request Envelope

Every public transport is normalized into the same upstream request envelope before dispatch.

```json
{
  "actor_id": "usr_123",
  "session_id": "ses_456",
  "channel": "mobile|web|voice|mcp|internal",
  "device_id": "dev_789",
  "request_id": "req_abc",
  "trace_id": "trace_xyz",
  "tenant_id": "tenant_default",
  "auth_context": {
    "subject": "usr_123",
    "roles": ["user"],
    "auth_strength": "password|oidc|step_up",
    "approval_token": null,
    "delegated_credential_ref": null
  },
  "transport": {
    "protocol": "http|ws|sse|mcp|grpc",
    "ip": "203.0.113.10",
    "user_agent": "..."
  },
  "payload": {}
}
```

### 3.1 Why This Exists
This envelope ensures Butler can preserve:
- multi-device continuity
- channel-aware behavior
- trace propagation
- approval-sensitive metadata
- step-up auth evidence
- consistent upstream routing semantics

---

## 4. Session Continuity Rules

Gateway owns transport continuity, not memory semantics.

### 4.1 Rules
- Accept `session_id` when supplied by the client.
- Mint a new `session_id` when absent and return it in the response envelope.
- Attach `device_id`, `channel`, and `request_id` metadata to every forwarded request.
- Maintain stream resume metadata for SSE / WebSocket reconnects.
- Never store conversation history directly as Gateway-owned memory.

### 4.2 Resume Semantics
- **WebSocket:** reconnect with `session_id` and last acknowledged event ID.
- **SSE:** support resume via `Last-Event-ID` or explicit resume token.
- **MCP:** preserve session identifiers through MCP session headers.
- **Voice:** treat each upload/stream as part of a session, not a separate memory silo.

---

## 5. API Contracts

### 5.1 Public Human-Facing Endpoints

```yaml
POST /api/v1/chat
  Auth: Required (OIDC JWT)
  Idempotency-Key: Optional for safe retries
  Request:
    {
      "message": "string",
      "session_id": "uuid (optional)",
      "channel_context": {},
      "client_context": {}
    }
  Response (200):
    {
      "session_id": "uuid",
      "request_id": "req_xxx",
      "response": "string",
      "stream_available": true
    }

POST /api/v1/voice/process
  Auth: Required (OIDC JWT)
  Purpose: MVP convenience endpoint for small synchronous voice turns only
  Limits: small uploads only; larger or realtime voice uses streaming/session path
  Request:
    {
      "audio_data": "base64",
      "format": "wav|mp3|m4a",
      "session_id": "uuid (optional)"
    }
  Response (200):
    {
      "session_id": "uuid",
      "transcript": "string",
      "response": "string",
      "audio_data": "base64 (optional)"
    }

POST /api/v1/sessions/bootstrap
  Auth: Required
  Response:
    {
      "session_id": "uuid",
      "request_id": "req_xxx",
      "resume_token": "optional"
    }

GET /api/v1/stream/{session_id}
  Auth: Required
  Accept: text/event-stream
  Response: Butler streaming event contract

GET /api/v1/health
  Auth: None
  Response:
    { "status": "healthy", "version": "3.1" }
```

### 5.2 Protocol-Native Runtime Endpoints

```yaml
WS /ws/chat
  Auth: Required
  Purpose: realtime token + tool + approval events

POST /mcp
GET /mcp
  Auth: MCP protected-resource model
  Purpose: targeted MCP Streamable HTTP compatibility
  Notes:
    - JSON-RPC framing
    - session headers preserved
    - compatibility validated against supported client matrix
```

### 5.3 Internal Control Exposure

Internal control routes for agent coordination, ACP-like control messages, or tool-plane control must be behind internal ingress, mTLS, and workload identity. They are **not** part of the public default Gateway contract.

---

## 6. Idempotency Contract

Gateway owns idempotency for public side-effecting requests.

### 6.1 Covered Requests
- `POST /api/v1/chat` when retries can duplicate an expensive upstream action
- `POST /api/v1/voice/process`
- future action-producing requests such as reminders, communication sends, and automation triggers

### 6.2 Required Behavior
- Header name: `Idempotency-Key`
- Store: key + request hash + response envelope + expiry
- Replay same response for the same key and matching request body
- Reject same key with mismatched body using `409 Conflict`
- TTL: default 24 hours unless endpoint-specific override applies

### 6.3 Reference Flow

```python
class IdempotencyManager:
    async def check_or_reserve(self, key: str, request_hash: str):
        record = await self.store.get(key)
        if not record:
            await self.store.reserve(key, request_hash, ttl=86400)
            return "new"
        if record.request_hash != request_hash:
            raise ConflictError("Idempotency key reuse with different payload")
        return record.response_envelope
```

---

## 7. Streaming Event Contract

Butler streaming is not just token output. The edge contract must support execution-aware events.

### 7.1 Event Types

```json
{ "type": "start", "request_id": "req_xxx", "session_id": "ses_xxx" }
{ "type": "token", "delta": "Hello" }
{ "type": "tool_call", "tool": "search_web", "status": "started" }
{ "type": "tool_result", "tool": "search_web", "status": "completed" }
{ "type": "status", "stage": "retrieving_context" }
{ "type": "approval_required", "approval_id": "apr_xxx", "action": "send_email" }
{ "type": "final", "message": "Done" }
{ "type": "error", "problem": { "type": "...", "title": "..." } }
```

### 7.2 Guarantees
- event ordering is preserved within a stream
- reconnect uses resume token or last event ID when supported
- error events still use RFC 9457-compatible problem payloads
- stream contracts are consistent across SSE and WebSocket at the semantic level
- **Reasoning-tag redaction** [UNIMPLEMENTED]
- **Flood control / Backpressure** [UNIMPLEMENTED]

---

## 8. Core Logic

### 8.1 Canonical Rate Limiting Model

Gateway uses one canonical model:
- **token bucket** for request quotas
- **concurrency semaphores** for expensive long-lived streams
- **route-specific overrides** by endpoint and product tier
- **tenant-aware quotas** at the edge

Sliding-window analytics may still exist for reporting, but primary enforcement should not depend on multiple contradictory algorithms.

```python
class TokenBucketLimiter:
    async def allow(self, subject: str, route: str, capacity: int, refill_rate: float) -> bool:
        state = await self.redis.get_bucket(subject, route)
        state = refill(state, refill_rate)
        if state.tokens < 1:
            return False
        state.tokens -= 1
        await self.redis.save_bucket(subject, route, state)
        return True
```

### 8.2 Authentication Validation

```python
async def validate_access_token(token: str, jwks_client) -> UserClaims:
    claims = verify_jwt(
        token,
        jwks_client=jwks_client,
        expected_issuer=OIDC_ISSUER_URL,
        expected_audience=JWT_EXPECTED_AUDIENCE,
        accepted_algs=["RS256", "ES256"],
        require_typ="at+jwt",
    )
    return UserClaims(
        user_id=claims["sub"],
        session_id=claims.get("sid"),
        roles=claims.get("roles", []),
        auth_strength=claims.get("acr", "unknown"),
    )
```

### 8.3 Risk-Tiered Degradation

Redis failure must not imply a universal fail-open policy.

| Route class | Degraded behavior |
|---|---|
| health / low-risk metadata | continue |
| normal chat | emergency local limiter, then fail-soft |
| expensive voice / MCP / long stream | fail-closed or strict concurrency fallback |
| internal control routes | fail-closed |

---

## 9. Security

### 9.1 Human vs Workload Auth

| Auth Type | Protocol | Purpose |
|-----------|----------|---------|
| External users | OAuth 2.1 / OIDC JWT access tokens | browser, mobile, partner API |
| Internal services | mTLS + workload identity (SPIFFE/SPIRE) | service-to-service |
| MCP protected resources | MCP auth conventions + Butler policy | supported MCP clients |

### 9.2 Validation Rules
- Validate `iss`, `aud`, `typ`, signature, `exp`, and clock skew window
- No shared `HS256` production secrets
- No JWT reuse between internal services
- Preserve step-up auth evidence and approval token references in the request envelope

### 9.3 Input and Payload Rules

Per-endpoint payload limits are required.

| Endpoint | Limit |
|---|---|
| `/api/v1/chat` | 256KB |
| `/api/v1/voice/process` | 5MB MVP convenience limit |
| `/mcp` | 256KB structured payload unless negotiated otherwise |
| WebSocket frames | explicit frame cap enforced by runtime |

### 9.4 Standard Headers
- `RateLimit`
- `RateLimit-Policy`
- `Retry-After`
- `X-Request-ID`
- `Traceparent`

Avoid exposing only legacy `X-RateLimit-*` headers when standards are already documented.

---

## 10. Error Model

Gateway returns RFC 9457 Problem Details for non-streaming failures and embeds equivalent problem objects in streaming error events.

```json
{
  "type": "https://docs.butler.lasmoid.ai/problems/rate-limit-exceeded",
  "title": "Rate limit exceeded",
  "status": 429,
  "detail": "Per-user quota exceeded for /api/v1/chat.",
  "instance": "/api/v1/chat#req_01HXYZ...",
  "retry_after": 60,
  "limit_policy": "user;w=60;q=100"
}
```

---

## 11. Performance & Scaling

### 11.1 Benchmark-Conditioned Targets

All Gateway latency targets must be read as **edge-processing-only** targets, excluding upstream business latency.

Assumptions:
- warm JWKS cache
- Redis in the same region / AZ class
- no cold start
- request size within documented route limits
- tracing enabled at normal production sampling

| Metric | Target |
|--------|--------|
| Authenticated non-streaming edge processing P99 | <50ms |
| Chat-route edge processing P95 | <30ms |
| Stream setup P95 | <100ms |
| Sustained requests per pod | benchmarked against pod size, not assumed by prose |

### 11.2 Throughput Guidance
Targets must be published with pod CPU / memory shape during testing. A bare “500 RPS per pod” claim without hardware assumptions is not sufficient for implementation decisions.

### 11.3 Scaling Strategy
- stateless app runtime
- Redis-backed quota/idempotency state
- connection pooling for upstreams
- separate concurrency pools for long-lived streams
- dedicated internal ingress for machine control routes

---

## 12. Observability

### 12.1 Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `gateway.requests.total` | Counter | requests by route / transport |
| `gateway.requests.errors` | Counter | RFC 9457 type + status |
| `gateway.edge.latency` | Histogram | edge-only processing latency |
| `gateway.rate_limit.exceeded` | Counter | token bucket denials |
| `gateway.stream.concurrent` | Gauge | active streams |
| `gateway.idempotency.replay` | Counter | replayed responses |
| `gateway.auth.failures` | Counter | authn/authz failures |

### 12.2 Logged Fields
- request_id
- trace_id
- actor_id
- session_id
- channel
- protocol
- endpoint
- status_code
- latency_ms
- upstream_target

---

## 13. Deployment

### 13.1 Runtime Configuration

```bash
GATEWAY_PORT=8000
GATEWAY_WORKERS=4
REDIS_URL=redis://redis:6379
ORCHESTRATOR_URL=http://orchestrator:8002

# Production auth
OIDC_ISSUER_URL=https://issuer.example.com/
OIDC_JWKS_URL=https://issuer.example.com/.well-known/jwks.json
JWT_EXPECTED_AUDIENCE=butler-gateway
JWT_ACCEPTED_ALGS=RS256,ES256

# Local dev only
LOCAL_DEV_JWT_SECRET=change-me
LOCAL_DEV_JWT_ALGORITHM=HS256
```

### 13.2 Health Checks

```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/stream/health
curl http://localhost:8000/mcp/health
```

---

## 14. Testing Strategy

### 14.1 Required Tests
- token bucket correctness
- idempotency key replay and conflict handling
- OIDC JWT validation with JWKS rotation
- SSE / WebSocket stream event ordering
- session resume behavior
- protocol adapter parity for shared policy outputs
- internal ingress rejection on public routes

### 14.2 Load Tests
Load tests must distinguish:
- short non-streaming requests
- long-lived SSE streams
- WebSocket fan-out
- MCP request bursts
- degraded Redis scenarios

---

## 15. Backwards Compatibility

### 15.1 Migration Notes
- direct memory access stays prohibited
- public Gateway remains orchestrator-first
- MCP stays protocol-native rather than fake REST wrapper
- idempotency and request-envelope behavior are now explicit parts of the contract

---

## 16. Implementation Phases

| Phase | Description |
|-------|-------------|
| 1 | Public HTTP core: auth, validation, problem details, request envelope | [IMPLEMENTED] |
| 2 | Token bucket + idempotency + trace propagation | [IMPLEMENTED] |
| 3 | SSE / WebSocket streaming with event contract | [IMPLEMENTED] |
| 4 | MCP Streamable HTTP compatibility path + client matrix | [UNIMPLEMENTED] |
| 5 | Internal control ingress with workload identity and machine-only routes | [UNIMPLEMENTED] |

---

*Document owner: Gateway Team*  
*Last updated: 2026-04-18*  
*Version: 3.1 (Implementation-ready)*
