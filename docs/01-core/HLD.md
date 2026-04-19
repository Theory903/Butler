# HLD - High Level Design

> **For:** All Engineers, Architecture
> **Status:** v0.3 (Production-Ready)
> **Version:** 3.0
> **Reference:** Corrected specification with boundary fixes, RFC 9457 error model

---

## 1. System Overview

Butler is a **distributed AI runtime for human tasks** - a multimodal assistant with:
- Intent understanding
- Memory (graph + vector)
- Autonomous execution
- Cloud-native scalability

### 1.1 Design Principles

| Principle | Description |
|-----------|-------------|
| KISS | Keep It Simple, Stupid |
| SOLID | Clean architecture |
| Local-first | Offline capability |
| Event-driven | Async over sync |
| Stateless compute | Horizontal scaling |

---

## 2. High-Level Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENTS                                  │
│   Mobile (Expo) | Web | Voice | Automation                     │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                    CDN + WAF (Cloudflare)                       │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                    API GATEWAY (Kong/Nginx)                     │
│               Rate limit, Auth, Routing                          │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
        ┌───────────────────────────────────────────────────────┐
        │              LOAD BALANCER (ALB)                       │
        └────────────────────────┬───────────────────────────────┘
                                 ↓
        ┌─────────────────────────┴─────────────────────────────┐
        │              ORCHESTRATION LAYER                      │
        │  Intent Engine | Planner | Execution Engine | Subagent  │
        └────────────────────────────┬────────────────────────────┘
                                     ↓
        ┌────────────────────────────┴────────────────────────────┐
        │                  SERVICE LAYER                           │
        │  Memory | AI/ML | Tools | Search | Communication          │
        └────────────────────────────┬────────────────────────────┘
                                     ↓
        ┌────────────────────────────┴────────────────────────────┐
        │                   MEMORY LAYER                          │
        │         Neo4j | Qdrant | Redis | S3                     │
        └────────────────────────────┬────────────────────────────┘
                                     ↓
        ┌────────────────────────────┴────────────────────────────┐
        │                    DATA LAYER                           │
        │            PostgreSQL | Logs | Analytics                  │
        └─────────────────────────────────────────────────────────┘
```

---

## 3. Core Services

### 3.1 Service Matrix

| Service | Type | Scaling | Dependencies |
|---------|------|---------|--------------|
| Gateway | Sync | Horizontal | None |
| Orchestrator | Async | Horizontal | Memory, AI |
| Memory | Sync/Async | Vertical | DBs |
| AI/ML | Async | Horizontal | GPU |
| Tools | Sync | Horizontal | External APIs |
| Search | Async | Horizontal | Web APIs |
| Communication | Sync | Horizontal | 3rd party |
| Automation | Async | Horizontal | Device APIs |

### 3.2 Communication Patterns

| Pattern | Services | Use Case |
|---------|----------|----------|
| Sync REST | Gateway ↔ Orchestrator | Simple requests |
| Async (Queue) | Orchestrator ↔ AI/ML | Heavy processing |
| WebSocket | Gateway ↔ Client | Real-time updates |
| Streaming | Orchestrator ↔ Client | LLM responses |

---

## 4. Data Flow

### 4.1 Request Path (Simple)

```
User Input
    ↓
Gateway (Auth + Rate Limit)
    ↓
Intent Engine (classify)
    ↓
Memory (retrieve context)
    ↓
Response
```

**Latency:** <500ms

### 4.2 Request Path (Complex)

```
User Input
    ↓
Gateway
    ↓
Intent Engine
    ↓
Memory (hybrid search)
    ↓
LLM (generate + plan)
    ↓
Planner (DAG creation)
    ↓
Execution Engine (parallel)
    ↓
Tool Execution
    ↓
Verification
    ↓
Memory (update)
    ↓
Response
```

**Latency:** 1-5s

### 4.3 Edge Cases

| Scenario | Handling |
|----------|----------|
| No intent match | Ask for clarification |
| API timeout | Retry 3x, then fallback |
| Tool failure | Skip, notify user |
| LLM failure | Rule-based fallback |

---

## 5. Memory Architecture

### 5.1 Hybrid Retrieval

```text
Query
    ↓
┌─────────────────────────┐
│   Query Rewriter (LLM) │
└─────────────────────────┘
    ↓
┌─────────┬─────────┬─────────┐
│  Graph  │ Vector │  BM25   │
│ (Neo4j) │(Qdrant)│(keyword)│
└─────────┴─────────┴─────────┘
    ↓
┌─────────────────────────┐
│     Reranker (BGE)     │
└─────────────────────────┘
    ↓
Context
```

### 5.2 Memory Layers

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Hot | Redis | Recent conversations |
| Warm | Qdrant | Semantically similar |
| Cold | Neo4j | Long-term relationships |
| Archive | S3 | Full history |

---

## 6. ML Architecture

### 6.1 Intent Pipeline

```
Input Text
    ↓
Embedding (BGE)
    ↓
Intent Classifier (BERT)
    ↓
Confidence Check
    ↓
Intent + Entities
```

### 6.2 Recommendation Pipeline

```
User Context
    ↓
Feature Extraction
    ↓
Candidate Generation (Graph + Embeddings)
    ↓
Ranking (Wide & Deep)
    ↓
Reranking (Cross-encoder)
    ↓
Top-K Recommendations
```

### 6.3 Model Serving

| Model | Deployment | GPU |
|-------|------------|-----|
| BGE | K8s (CPU) | No |
| BERT | K8s (CPU) | No |
| GPT/Claude | External API | Provider |
| Custom | K8s (GPU) | Yes |

---

## 7. Scaling Strategy

### 7.1 Horizontal Scaling

| Service | Strategy | Trigger |
|---------|----------|---------|
| Gateway | Pods | CPU >70% |
| Orchestrator | Pods | Queue depth |
| AI/ML | Pods | GPU queue |
| Tools | Pods | Error rate |

### 7.2 Auto-Scaling Rules

```yaml
# HPA Example
metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
minReplicas: 3
maxReplicas: 50
```

### 7.3 Capacity Planning

| Phase | Users | RPS | Gateway Pods | Orchestrator Pods |
|-------|-------|-----|---------------|-------------------|
| Phase 1 | 1K | 100 | 2 | 2 |
| V1 | 10K | 1K | 5 | 10 |
| V2 | 100K | 5K | 20 | 50 |
| V3 | 1M | 10K | 50 | 100 |

---

## 8. Failure Handling

### 8.1 Circuit Breaker

| Service | Threshold | Action |
|---------|-----------|--------|
| LLM | 50% errors | Fallback to rules |
| Memory | 20% errors | Use cache only |
| Tools | 10% errors | Skip tool |

### 8.2 Retry Strategy

| Retry | Delay | Max |
|-------|-------|-----|
| 1st | 100ms | - |
| 2nd | 500ms | - |
| 3rd | 2s | - |
| Then | - | Fail |

### 8.3 Fallback Hierarchy

```
Primary (LLM)
    ↓ (fail)
Small LLM
    ↓ (fail)
Rule-based
    ↓ (fail)
"I couldn't process that"
```

---

## 9. Security Architecture

### 9.1 Trust Boundary

```text
┌─────────────────────────────┐
│      Untrusted (Client)      │
└──────────────┬──────────────┘
               ↓ JWT
┌──────────────┴──────────────┐
│        Gateway (Edge)        │
└──────────────┬──────────────┘
               ↓ mTLS
┌──────────────┴──────────────┐
│      Internal Services       │
└──────────────┬──────────────┘
               ↓
┌──────────────┴──────────────┐
│       Sensitive Data         │
└─────────────────────────────┘
```

### 9.2 Data Classification

| Level | Data | Protection |
|-------|------|-------------|
| Public | Docs, code | None |
| Internal | Metrics | Auth |
| Confidential | User data | Encryption |
| Restricted | Keys, tokens | Vault |

---

## 10. Observability

### 10.1 Metrics

| Category | Metrics |
|----------|---------|
| Traffic | RPS, concurrent, bandwidth |
| Latency | P50, P95, P99 by endpoint |
| Errors | Rate by type, code |
| Business | Task completion, DAU |

### 10.2 Tracing

- Every request gets trace_id
- Span per service
- Parents propagate

### 10.3 Alerting

| Alert | Threshold |
|-------|-----------|
| Error rate | >1% |
| Latency P99 | >5s |
| Pod restarts | >5/min |
| Queue depth | >10K |

---

## 11. Deployment Architecture

### 11.1 Environments

```
┌─────────┐  ┌─────────┐  ┌─────────┐
│  Dev    │→ │ Staging │→ │  Prod   │
└─────────┘  └─────────┘  └─────────┘
```

### 11.2 Regions

| Region | Type | Services |
|--------|------|----------|
| us-east-1 | Primary | All |
| us-west-2 | Secondary | Gateway, Orchestrator, Memory |
| eu-west-1 | Tertiary | Gateway only |

---

## 12. Component Responsibilities

### 12.1 Gateway
- Authentication (JWT)
- Rate limiting
- Routing
- Request validation

### 12.2 Orchestrator
- Request lifecycle
- Intent parsing
- Task planning
- Execution coordination

### 12.3 Memory
- Context retrieval
- Preference storage
- Relationship graph

### 12.4 AI/ML
- Intent classification
- Recommendations
- Predictions
- Embeddings

### 12.5 Tools
- Action execution
- Sandboxing
- Result verification

---

## 13. Protocol Standards

| Protocol | Standard | Implementation |
|----------|----------|----------------|
| HTTP/1.1 | RFC 9110 | REST API |
| HTTP/2 | RFC 9113 | Mobile/high-perf |
| HTTP/3 | RFC 9114 | Edge ingress only |
| WebSocket | RFC 6455 | Bidirectional realtime |
| SSE | HTML Standard | One-way streaming |
| gRPC | gRPC | Internal services |
| MCP | MCP 2025 | Tool context protocol |
| A2A/ACP | A2A | Agent control plane |

---

## 14. Performance Targets

### 14.1 Latency Budget (P50/P95/P99)

| Request Type | P50 | P95 | P99 |
|--------------|-----|-----|-----|
| Simple (intent) | 100ms | 200ms | 500ms |
| Medium (RAG) | 500ms | 1s | 2s |
| Complex (LLM) | 1s | 2s | 5s |
| Heavy (workflow) | 5s | 10s | 30s |

### 14.2 Throughput Targets

| Metric | Target |
|--------|--------|
| RPS (peak) | 10K |
| Concurrent sessions | 100K |
| WebSocket connections | 50K |

---

## 15. Observability Standards

| Category | Metrics |
|----------|---------|
| Traffic | RPS, concurrent, bandwidth |
| Latency | P50, P95, P99 by endpoint |
| Errors | Rate by type, code |
| Business | Task completion, DAU |

**Tracing:** Every request gets trace_id, span per service, parents propagate.

**Alerts:**
| Alert | Threshold |
|-------|-----------|
| Error rate | >1% |
| Latency P99 | >5s |
| Pod restarts | >5/min |
| Queue depth | >10K |

---

## 16. Error Response Standards (RFC 9457)

All error responses MUST follow RFC 9457 Problem Details format:

```json
{
  "type": "https://docs.butler.lasmoid.ai/problems/{error-type}",
  "title": "Error Title",
  "status": {http_code},
  "detail": "Human-readable description",
  "instance": "/api/v1/endpoint#req_xxx"
}
```

---

## 17. Backwards Compatibility

**Version 1.0 → 3.0 changes:**

- Error format migrated to RFC 9457 Problem Details
- Service boundaries clarified (Gateway NEVER calls Memory directly)
- Protocol alignment to RFC 9110/9113 standards
- Capacity planning phases renamed (MVP → Phase 1)

**Migration path:**
1. Update error handling to RFC 9457 format
2. Use Orchestrator for Memory access (not direct)
3. Adopt standard protocol implementations

---

## 18. Clear Service Boundaries

| Conflict | Resolution |
|----------|------------|
| Auth vs Security | Auth: identity/credentials/sessions. Security: enforcement/threat detection |
| Gateway vs Memory | Gateway NEVER calls Memory directly. Always via Orchestrator |
| Memory vs ML | Memory stores/queries vectors. ML generates embeddings. Memory calls ML for query embeddings |

---

*Document owner: Architecture Team*  
*Last updated: 2026-04-17*  
*Version: 3.0 (Production-Ready)*
