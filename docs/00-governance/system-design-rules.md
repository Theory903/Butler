# System Design Rules

> **Status:** Authoritative
> **Version:** 4.0
> **Last Updated:** 2026-04-18

---

## 1. Error Model (RFC 9457)

All services MUST use Problem Details format:

```json
{
  "type": "https://problems.butler.lasmoid.ai/{error-type}",
  "title": "Error Title",
  "status": 400,
  "detail": "Human-readable description",
  "instance": "/api/v1/endpoint#req_xxx"
}
```

**Standard error types:**

| Type | HTTP | Description |
|------|------|-----------|
| invalid-request | 400 | Request body invalid |
| authentication-failed | 401 | Auth failed |
| authorization-failed | 403 | Permission denied |
| not-found | 404 | Resource missing |
| rate-limit-exceeded | 429 | Too many requests |
| internal-error | 500 | Server error |
| bad-gateway | 502 | Upstream failed |
| service-unavailable | 503 | Maintenance |
| gateway-timeout | 504 | Upstream slow |

**DO NOT use:** `{"success": false, "error": "..."}` anywhere.

---

## 2. JWT Rules

- RS256 ONLY (no HS256)
- JWKS endpoint required
- Validate issuer (`iss`)
- Validate audience (`aud`)
- Short-lived access tokens (<15min)
- Refresh token rotation

---

## 3. Password Hashing

Argon2id ONLY per OWASP:
- Memory: 64MB minimum
- Iterations: 3 minimum
- Parallelism: 4 minimum

**DO NOT use:** bcrypt, scrypt, MD5, SHA-256

---

## 4. Health Probes

| Endpoint | Purpose | Failure Action |
|---------|---------|-----------|
| /health/live | Liveness | Restart pod |
| /health/ready | Readiness | Remove from LB |
| /health/startup | Startup complete | Route traffic |

Four states: STARTING → HEALTHY → DEGRADED → UNHEALTHY

---

## 5. Database Anti-Patterns

### NEVER DO:
- `VACUUM FULL` (use autovacuum)
- `pg_archivecleanup`
- Connection pooling misconfiguration
- Long-running transactions

### ALWAYS DO:
- Use PgBouncer for connection pooling
- Set statement_timeout
- Use prepared statements
- Monitor query plans

---

## 6. API Design

### URL Structure
```
/api/v1/{resource}/{action}
```

### Idempotency
All side-effect endpoints MUST support `Idempotency-Key` header.

### Versioning
Major version in URL: `/api/v1/`

### Rate Limiting
Per-user, sliding window. Return 429 with `Retry-After`.

---

## 7. Async Messaging

### Use Redis Streams for:
- Durable work distribution
- Consumer groups
- Acknowledgement tracking

### Use Pub/Sub ONLY for:
- Ephemeral fanout
- Real-time notifications

### NEVER use Pub/Sub for:
- Work that matters
- Queued processing

---

## 8. Observability

Use OpenTelemetry semantic conventions:

| Span | Naming |
|------|--------|
| HTTP server | `http.server.request` |
| HTTP client | `http.client.request` |
| Database | `db.query` |
| LLM | `ai.request` |

Required metrics:
- `butler.requests.total` (counter)
- `butler.latency` (histogram)
- `butler.errors` (counter)

---

## 9. Failover

### Database
1. Verify PRIMARY down (not just slow)
2. Verify REPLICA caught up
3. Promote REPLICA

### Never do:
- Automatic failover without verification
- Split-brain promotion

---

## 10. Circuit Breaker

| Service | Threshold | Fallback |
|---------|----------|---------|
| LLM | >50% errors | Rules |
| Memory | >20% errors | Cache |
| Tools | >10% errors | Skip |

---

*Rules owner: Architecture Team*
*Version: 4.0*