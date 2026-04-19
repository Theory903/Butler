# System Design Rules

> **For:** Engineering  
> **Status:** Authoritative Draft  
> **Version:** 2.0

---

## 1. Service Design Rules

### 1.1 Responsibility

```
✅ DO: Each service/module owns ONE business capability boundary
✅ DO: A service may contain multiple internal components, but one ownership surface
❌ DON'T: One service owning another service's source of truth
```

### 1.2 Communication

```
✅ DO: Prefer sync for user-critical low-latency calls
✅ DO: Prefer async for write-behind, notifications, analytics, event fanout, retries
✅ DO: Idempotent or compensatable side-effecting operations
❌ DON'T: Synchronous dependency chain longer than 3 hops on the hot path
❌ DON'T: Circular dependencies
```

### 1.3 Failure Handling

```
✅ DO: External/client-visible errors use RFC 9457 Problem Details
✅ DO: Internal failures include structured context (request ID, service, operation, dependency)
❌ DON'T: Expose stack traces or raw internal exception text to clients
❌ DON'T: Retry without explicit retryable failure classification
```

---

## 2. API Design Rules

### 2.1 HTTP and Resource Design

```
✅ DO: Use resource-oriented paths where possible
✅ DO: Version public APIs in the URL (/api/v1/...)
✅ DO: Use verbs in URLs only for true actions not natural resource state transitions
✅ DO: GET is safe, PUT/DELETE should be idempotent where applicable
✅ DO: POST is non-idempotent unless guarded
```

### 2.2 Response Rules

```
✅ DO NOT: Force a universal success envelope
✅ DO: Success responses return the resource/action result directly with proper HTTP status codes
✅ DO: Include request correlation via headers
✅ DO: Errors return RFC 9457 Problem Details payloads

RFC 9457 Problem Details format:
{
  "type": "https://docs.butler.lasmoid.ai/problems/{error-type}",
  "title": "Error Title",
  "status": {http_code},
  "detail": "Human-readable description",
  "instance": "/api/v1/endpoint#req_xxx"
}
```

### 2.3 Status Codes

| Code | Usage |
|------|-------|
| 200 | Success |
| 201 | Created |
| 202 | Accepted for async workflows |
| 204 | No content |
| 400 | Invalid request |
| 401 | Unauthenticated |
| 403 | Unauthorized |
| 404 | Not found |
| 409 | Conflict |
| 422 | Semantically invalid input |
| 429 | Rate limited |
| 500 | Internal error |
| 502 | Upstream failure |
| 503 | Unavailable |
| 504 | Upstream timeout |

---

## 3. Database Rules

### 3.1 Query Rules

```
✅ DO: Use parameterized queries
✅ DO: Index high-value filter and join paths
✅ DO: LIMIT result sets deliberately
✅ DO: Eliminate N+1 query patterns
❌ DON'T: SELECT * in application code
❌ DON'T: Full table scans in production paths without explicit justification
```

### 3.2 Write Rules

```
✅ DO: Validate before write
✅ DO: Use transactions for multi-row consistency boundaries
✅ DO: Batch writes where possible
✅ DO: Durable workflow/task state in primary relational store, not cache
❌ DON'T: Repeated per-item writes inside request loops when batch path exists
```

### 3.3 Schema Rules

```
✅ DO: UUID/ULID-style stable IDs
✅ DO: Every mutable table includes created_at and updated_at
✅ DO: JSONB only for truly flexible or sparse structures
✅ DO: Foreign keys and critical lookup paths must be indexed
```

---

## 4. Security Rules

### 4.1 Authentication

```
✅ DO: Access tokens must expire
✅ DO: Use refresh tokens with rotation/revocation controls
✅ DO: HTTPS/TLS required for all external traffic
✅ DO: Internal service auth must be workload-authenticated, preferably mTLS-backed
✅ DO: Password hashing MUST be Argon2id (OWASP-recommended)
✅ DO: JWT with asymmetric signing (RS256/ES256), JWKS-backed
✅ DO: Validate issuer and audience claims
❌ DON'T: HS256 in production (ever)
❌ DON'T: Shared secrets for token signing
```

### 4.2 Authorization

```
✅ DO: Authorization is server-side only
✅ DO: Enforce least privilege at route, action, and tool level
✅ DO: Sensitive actions require policy class and approval behavior
❌ DON'T: Trust client-declared role, scope, or tool permissions without server validation
```

### 4.3 Data Protection

```
✅ DO: Encrypt data in transit
✅ DO: Encrypt sensitive data at rest
✅ DO: PII must be masked or redacted in logs
❌ DON'T: Log credentials, tokens, secrets, or raw sensitive payloads
❌ DON'T: Store passwords with reversible encryption (must use hashing)
```

---

## 5. Performance Rules

### 5.1 Latency Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| Simple API read | <100ms p95 | Gateway overhead excluded |
| Gateway overhead | <20ms p95 | |
| Tool execution | <500ms p95 | Low-risk synchronous tools |
| DB query | <50ms p95 | Indexed hot paths |
| Cache lookup | <10ms p95 | |
| ML inference | Class-specific | Documented per model |

### 5.2 Resource Rules

```
✅ DO: Requests/limits required for all deployed services
✅ DO: CPU, memory, connection budgets are service-specific
✅ DO: Autoscaling should consider user pain signals, not CPU alone
```

### 5.3 Caching

```
✅ DO: Cache expensive and stable computations
✅ DO: Every cache entry must have TTL or explicit invalidation rule
❌ DON'T: Treat cache as the only durable truth
❌ DON'T: Cache secrets or highly sensitive auth artifacts in unsafe forms
```

---

## 6. Observability Rules

### 6.1 Logging

```
✅ DO: Structured JSON logs
✅ DO: Every request must have correlation/request ID
✅ DO: Log levels must be meaningful (DEBUG, INFO, WARN, ERROR)
❌ DON'T: Log sensitive data in raw form
```

### 6.2 Metrics

```
✅ DO: Emit RPS, error rate, latency percentiles, saturation, core business metrics
✅ DO: High-cardinality labels must be controlled
❌ DON'T: User IDs and session IDs in metric labels
```

### 6.3 Tracing

```
✅ DO: Distributed tracing required across service boundaries
✅ DO: One trace per request/workflow
✅ DO: Use OpenTelemetry semantic conventions for consistent attribute names
```

### 6.4 Health (Kubernetes-style Probes)

Every service MUST expose:

| Endpoint | Purpose | Kubernetes Probe |
|----------|---------|------------------|
| `/health/live` | Process is running | livenessProbe |
| `/health/ready` | Can serve traffic | readinessProbe |
| `/health/startup` | Startup completed | startupProbe |
| `/health/degraded` | (optional) Degraded mode | |

```
✅ DO: /health/live returns 200 if process is alive
✅ DO: /health/ready returns 200 if can serve traffic (DB connected, deps available)
✅ DO: /health/startup returns 200 when initialization complete
❌ DON'T: Single /health endpoint for all probe types
```

---

## 7. Testing Rules

### 7.1 Coverage

| Type | Target |
|------|--------|
| Unit | 80% for core domain logic |
| Integration | Critical persistence and boundary flows |
| E2E | All golden paths and high-risk flows |

### 7.2 Test Classes

```
✅ DO: Unit tests (fast, isolated)
✅ DO: Integration tests (real infra boundaries)
✅ DO: Contract tests (public/internal API compatibility)
✅ DO: Load/perf tests (critical paths)
✅ DO: Replay/idempotency tests (workflow and side-effecting operations)
❌ DON'T: Tests depend on execution order
❌ DON'T: Shared mutable hidden state
```

---

## 8. Deployment Rules

### 8.1 CI/CD

```
✅ DO: Lint, type check, and tests must pass before deploy
✅ DO: Build immutable images
✅ DO: Deploy to staging before production
✅ DO: Smoke tests after deploy
✅ DO: Rollback path required before production promotion
```

### 8.2 Release

```
✅ DO: Semantic versioning for public contracts
✅ DO: Changelog for externally visible changes
✅ DO: Feature flags for risky rollouts
✅ DO: DB migrations must be forward-safe and rollback-considered
```

---

## 9. Butler-Specific Non-Negotiables

```
✅ DO: Retrieve first, reason second
✅ DO: Durable before clever
✅ DO NOT: Silent ML-driven actions
✅ DO: Redis Pub/Sub is at-most-once (use Streams for durable messaging)
✅ DO: Gateway does transport, not business logic
✅ DO: Orchestrator decides, Tools execute
✅ DO: Memory stores and retrieves context, ML generates embeddings and ranking signals
✅ DO: Auth owns identity, Security owns enforcement
```

---

*Document owner: Architecture Team*  
*Last updated: 2026-04-18*  
*Version: 2.0 (Oracle-Grade)*

(End of file - total 259 lines)