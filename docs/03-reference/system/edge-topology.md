# Butler Edge Topology

> **Version:** 1.0  
> **Updated:** 2026-04-19  
> **Owner:** Butler Infra + Gateway Team  
> **Sources:** Nginx (edge patterns, rate limiting, streaming, caching)

---

## Overview

Butler's edge topology defines how traffic flows from clients (mobile apps, desktop companions, web, IoT, API consumers) through the ingress layer to the Butler backend. 

The design is inspired by Nginx's production-grade edge patterns — master/worker process model, leaky-bucket rate limiting, shared memory zones, WebSocket/SSE hardening, and layered timeouts — adapted for Butler's AI OS deployment model.

**EdgeRouter**: Butler's edge ingress layer, implemented via Nginx, serves as the primary traffic router and security gateway for all external connections.

---

## Topology Diagram

```
                                Internet
                                   │
                     ┌─────────────┴─────────────┐
                     │                           │
              ┌──────┴──────┐           ┌────────┴────────┐
              │  Device     │           │   Cloud Clients  │
              │  (mobile,   │           │   (web, API,    │
              │  desktop,   │           │   webhooks,     │
              │  IoT)       │           │   CLI, MCP)     │
              └──────┬──────┘           └────────┬────────┘
                     │                           │
              ┌──────▼───────────────────────────▼──────┐
              │              Nginx Edge Tier             │
              │   TLS termination, routing, caching,     │
              │   rate limiting, WebSocket/SSE upgrade   │
              └─────────────────┬───────────────────────┘
                                │
              ┌─────────────────▼───────────────────────┐
              │         Butler Gateway (FastAPI)          │
              │   Auth, ACP, idempotency, load shedding  │
              └──────┬──────────┬──────────┬────────────┘
                     │          │          │
              ┌──────▼──┐  ┌────▼────┐  ┌─▼──────────┐
              │Orchestr.│  │ Memory  │  │   Tools    │
              │  + ML   │  │ + Search│  │  Executor  │
              └─────────┘  └─────────┘  └────────────┘
```

---

## Edge Ingress

### TLS Termination

- TLS 1.3 required; TLS 1.2 allowed for legacy device compatibility
- ACME (Let's Encrypt) for edge certificates; auto-renewal
- HSTS header with `max-age=31536000; includeSubDomains; preload`
- OCSP stapling enabled
- HTTP/2 for API clients; HTTP/1.1 for legacy webhooks

### Routing Rules

| Path Pattern | Backend | Protocol |
|---|---|---|
| `/api/v1/*` | Butler Gateway | HTTP/2 |
| `/api/v1/realtime/*` | Butler Realtime (WebSocket) | WebSocket Upgrade |
| `/api/v1/stream/*` | Butler Gateway (SSE) | SSE (HTTP/1.1 keep-alive)|
| `/api/v1/.well-known/*` | Butler Gateway (JWKS) | HTTP/2 |
| `/static/*` | CDN / Nginx static | HTTP/2 |
| `/health` | Butler health endpoint | HTTP/1.1 |

---

## WebSocket and SSE

### WebSocket Hardening (from Nginx patterns)

- `Connection: Upgrade` header enforced
- `Upgrade: websocket` required
- Max frame size: 64KB (configurable per deployment)
- Ping interval: 30s; pong timeout: 10s → disconnect
- Origin validation against `ALLOWED_ORIGINS` allowlist

### SSE Configuration

- `Content-Type: text/event-stream`
- `Cache-Control: no-cache`
- `X-Accel-Buffering: no` (disables Nginx proxy buffering for SSE)
- Keep-alive: 60s comment heartbeat (`:\n\n`)
- Client reconnect: `retry: 3000` (3 second reconnect interval)

---

## Reverse Proxy and Cache

### Cache Tiers

| Cache Tier | Contents | TTL | Invalidation |
|---|---|---|---|
| **Nginx edge cache** | Static assets, JWKS endpoint | 1h (JWKS: 5min) | Cache-Control headers |
| **Redis application cache** | Tool results, search responses | 30s–300s | Key-based eviction |
| **Stale-while-revalidate** | Low-staleness-tolerance API responses | Background refresh | ETags |

### Cache Policies

- API responses (`/api/v1/*`): `Cache-Control: no-store` — never cached at edge
- JWKS: `Cache-Control: public, max-age=300` — cached 5 minutes
- Static assets: `Cache-Control: public, max-age=31536000, immutable`
- Health endpoints: `Cache-Control: no-cache`

---

## Rate Limiting (Nginx Leaky-Bucket Pattern)

**RateLimit**: Butler implements multi-layer rate limiting using Nginx's leaky-bucket algorithm to prevent abuse and ensure fair resource allocation.

Two layers of rate limiting:

### Layer 1: Nginx Edge (IP-based)
- `limit_req_zone $binary_remote_addr zone=butler_edge:10m rate=100r/s`
- Burst: 200 requests, no delay
- Purpose: DDoS protection, bot mitigation
- Action on exceed: `429 Too Many Requests` with `Retry-After` header

### Layer 2: Butler Gateway (User-based)
- Token bucket per `account_id` implemented in `backend/services/gateway/rate_limiter.py`
- Health-adaptive: 3x cost multiplier when node is DEGRADED
- 503 when node is UNHEALTHY
- Quotas configurable per tenant/plan

---

## Device and Cloud Split Ingress

Butler supports differentiated ingress paths for device vs. cloud clients:

| Path | Description | Special Handling |
|---|---|---|
| `api.butler.ai` | Standard cloud API | Full TLS, rate limiting, caching |
| `device.butler.ai` | Device companion traffic | Persistent connection priority, lower latency targets |
| `edge.butler.ai` | IoT/low-bandwidth clients | Compressed responses, MQTT-over-WebSocket bridge |
| `admin.butler.ai` | Platform admin | Stricter TLS, IP allowlist, hardware key bypass |

### Device-Specific Optimizations

- HTTP/3 (QUIC) for mobile clients where supported
- Connection coalescing — multiple device capabilities share a single TLS session
- Push priority: device notification traffic gets higher scheduler priority
- Edge-local caching for frequently accessed device settings (TTL: 30s)

---

## Stream Buffering Policy

| Stream Type | Nginx Buffering | Rationale |
|---|---|---|
| SSE event streams | Disabled (`X-Accel-Buffering: no`) | Real-time delivery |
| WebSocket frames | Disabled | Bidirectional real-time |
| REST API responses | Enabled (default) | Efficient for large payloads |
| File uploads | Enabled, 256MB client_max_body_size | Avoid OOM on proxy |

---

## Layered Timeouts

| Timeout | Value | Scope |
|---|---|---|
| `client_header_timeout` | 10s | Time to receive full request headers |
| `client_body_timeout` | 60s | Time between request body reads |
| `proxy_connect_timeout` | 5s | Time to connect to Butler Gateway |
| `proxy_read_timeout` | 120s | Time waiting for Butler response (generous for LLM streaming) |
| `proxy_send_timeout` | 30s | Time to send response to client |
| `keepalive_timeout` | 75s | HTTP keep-alive connection lifetime |
| WebSocket `proxy_read_timeout` | 3600s | Keep WS alive for 1 hour sessions |
| SSE `proxy_read_timeout` | 3600s | Keep SSE stream alive |

---

## Canary and Stable Deployment Lanes

Butler uses weighted traffic splitting at the Nginx edge for safe deployments:

```nginx
upstream butler_stable {
    server butler-stable:8000 weight=90;
}

upstream butler_canary {
    server butler-canary:8000 weight=10;
}
```

- Canary receives 10% of traffic by default
- Canary promotion: gradually increase weight as error rates stay within SLO
- Canary rollback: immediately route 100% to stable on alert

Traffic split header: `X-Butler-Lane: canary | stable` added to responses for observability.

---

## Security Hardening at Edge

- `server_tokens off` — suppress Nginx version
- `add_header X-Content-Type-Options nosniff`
- `add_header X-Frame-Options DENY`
- `add_header X-XSS-Protection "0"` (rely on CSP)
- `add_header Referrer-Policy strict-origin-when-cross-origin`
- Content-Security-Policy header (configured per frontend app)
- Request ID injected at edge: `add_header X-Request-ID $request_id`

---

## Reference

- `docker-compose.yml` — Local Nginx configuration
- `docs/04-operations/infra/INFRASTRUCTURE.md` — Production infra topology
- `docs/04-operations/deployment/DEPLOYMENT.md` — Deployment procedures
- `backend/services/gateway/rate_limiter.py` — Application-layer rate limiting
- `backend/core/middleware.py` — Request context and trace propagation


## Harvested Capabilities: Edge Topology & Rate Limits
**Source: NGINX Architecture**
- **Master/Worker Process Scaling:** Separation of control plane (Orchestrator) from data planes (Agent Runtime Workers) connected via shared memory IPC.
- **Leaky Bucket Rate Limiting:** Enforced at the boundary for API requests to ensure burst smoothing without dropping valid telemetry from devices.
- **Zero-Copy Socket Operations & Sendfile:** Avoid unnecessary user-space buffer copies for large model transports or file ingestion events.
- **Granular Stage Timeouts:** Explicit drop policies at every parsing stage (headers, body, transport, execution) to mitigate slowloris attacks and handle zombie agents.

