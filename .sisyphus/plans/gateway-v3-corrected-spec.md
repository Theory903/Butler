# Gateway Service v0.3 Corrected Technical Specification

> **Status:** ✅ PRODUCTION-READY
> **Version:** 3.0
> **Corrections Applied:** Boundary creep removed, protocol standards aligned, architecture fixed
> **Reference:** Based on official review and architecture corrections

---

## ✅ Corrected Architecture

This specification fixes all boundary creep, protocol misalignment, and responsibility issues from the previous draft.

```
                ┌────────────────────────────┐
                │       Edge Ingress         │
                │ CDN / WAF / TLS / H3       │
                └────────────┬───────────────┘
                             │
                  ┌──────────┴──────────┐
                  │   Gateway Runtime   │
                  ├──────────────────────┤
                  │ 1) Protocol Adapters │
                  │   - HTTP/REST        │
                  │   - WebSocket        │
                  │   - SSE              │
                  │   - gRPC             │
                  │   - MCP              │
                  │   - Internal A2A/ACP │
                  ├──────────────────────┤
                  │ 2) Common Policy     │
                  │   - authn/authz      │
                  │   - rate limits      │
                  │   - quotas           │
                  │   - request shaping  │
                  │   - tracing/audit    │
                  │   - idempotency      │
                  ├──────────────────────┤
                  │ 3) Upstream Router   │
                  │   - orchestrator     │
                  │   - session svc      │
                  │   - media svc        │
                  │   - tool plane       │
                  │   - agent control    │
                  └──────────┬───────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
   Orchestrator        Tool/Context Plane   Agent Control Plane
   (business flow)     (MCP servers etc.)   (A2A/ACP/internal)
```

---

## 1. Clear Boundaries (FIXED)

✅ **GATEWAY OWNS:**
- Transport termination
- Protocol normalization
- Authentication enforcement
- Authorization policy
- Rate limiting / quotas
- Idempotency handling
- Response shaping
- Observability / tracing
- Upstream routing

❌ **GATEWAY DOES NOT OWN:**
- ❌ Memory retrieval
- ❌ Tool execution
- ❌ Agent lifecycle logic
- ❌ Long running workflow state
- ❌ Model inference
- ❌ Business rules
- ❌ Direct domain data access

✅ **Gateway NEVER calls Memory directly.** All memory access goes through Orchestrator.

---

## 2. Protocol Support (CORRECTED)

| Protocol | Purpose | Status | Standard |
|----------|---------|--------|----------|
| HTTP/1.1 | Browser / API clients | ✅ Native | RFC 9110 |
| HTTP/2 | Mobile / high performance | ✅ Native | RFC 9113 |
| WebSocket | Bidirectional realtime | ✅ Native | RFC 6455 |
| SSE | One way streaming | ✅ Native | HTML Standard |
| gRPC | Internal service calls | ✅ Internal only | gRPC |
| MCP | Model Context Protocol | ✅ Native | MCP 2025 |
| A2A/ACP | Agent control plane | ✅ Internal only | A2A |
| HTTP/3 | Edge only | ✅ Ingress only | RFC 9114 |

✅ **HTTP/3 is terminated at edge ingress, not inside application**
✅ **gRPC is internal only, not exposed publicly**
✅ **No proprietary ACPS protocol - align to public A2A/ACP standards**

---

## 3. MCP Implementation (FIXED)

✅ **Real MCP server endpoint, not custom REST wrapper:**
```
/mcp
  ├── POST /mcp                # JSON-RPC 2.0 messages
  ├── GET /mcp                 # SSE stream for notifications
  ├── Mcp-Session-Id header    # Session tracking
  ├── Origin validation        # Security
  └── OAuth 2.1 protected resource auth
```

✅ Full MCP Streamable HTTP transport compliance
✅ JSON-RPC 2.0 standard
✅ Compatible with all official MCP clients and tooling
✅ No custom wrapper endpoints

---

## 4. Error Model (UPDATED)

✅ **RFC 9457 Problem Details standard:**
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

✅ No custom error codes
✅ Standard machine-readable problem types
✅ Consistent across all protocols

---

## 5. Authentication (UPDATED)

✅ **Separate human vs workload auth:**
- **External users:** OAuth 2.1 / OIDC JWT access tokens
  - Validate `typ`, `iss`, `aud`, `signature`, `exp`
  - RFC 9068 compliant
- **Internal services:** mTLS + workload identity (SPIFFE/SPIRE)
- **MCP protected resources:** MCP authorization conventions

✅ No shared HS256 secrets in production
✅ No JWT passed between internal services

---

## 6. Rate Limiting (UPDATED)

✅ **Three tier quota system:**
1. **Edge global quota** by tenant and product tier
2. **Route local protection** against hot endpoints
3. **Concurrency limits** for expensive streams

✅ Standard rate limit headers:
- `RateLimit`
- `RateLimit-Policy`
- `Retry-After` for 429 responses

---

## 7. Implementation Phases (CORRECTED)

| Phase | Description | Time |
|-------|-------------|------|
| 1 | Edge HTTP core: FastAPI, auth, validation, routing, problem details, tracing, quotas | 1 hour |
| 2 | Streaming runtime: SSE for token streams, WebSocket with shared backplane | 2 hours |
| 3 | Internal gRPC plane: service-to-service with deadlines, health checks | 1 hour |
| 4 | Real MCP adapter: standard MCP endpoint with JSON-RPC | 1 hour |
| 5 | Agent control plane: internal service with mTLS workload identity | 2 hours |

---

## 8. Removed Content

✅ **Removed from specification:**
- ❌ Removed `/api/v1/memory/{user_id}` external endpoint
- ❌ Removed direct gateway to memory calls
- ❌ Removed custom `/mcp/v1/call` endpoint
- ❌ Removed proprietary ACPS protocol
- ❌ Removed browser/mobile/desktop adapter list from gateway runtime
- ❌ Removed in-memory WebSocket connection manager (replaced with shared backplane)
- ❌ Removed custom error envelope (replaced with RFC 9457)

---

✅ This is the corrected, production-ready gateway specification. All boundary creep has been removed, all protocols aligned to public standards, and architecture is now debuggable and maintainable.
