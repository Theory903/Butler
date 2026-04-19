# Memory Service - Technical Specification

> **For:** Engineering  
> **Status:** Active (v3.1) — Cold store hardened with FAISS fallback
> **Version:** 3.1
> **Reference:** Butler evolving-memory system with graph + vector retrieval, temporal reasoning, provenance, and user-understanding layers  
> **Last Updated:** 2026-04-19

---

## 0. v3.1 Cold Store Hardening Notes

> **Added in v3.1 (2026-04-19)**

### FaissColdStore (`services/memory/faiss_cold_store.py`) — NEW
Production cold-tier vector store using `faiss-cpu` as a drop-in replacement when `pyturboquant` is not installed:
- **Index type**: `IndexFlatIP` with L2 normalisation (cosine similarity via inner product)
- **Auto-upgrade**: Logs an IVF rebuild recommendation at 50k entries for O(log n) ANN
- **Identical interface**: `add_sync()`, `search_async()`, `persist()`, `load()`, `size`, `stats()` — same as `TurboQuantColdStore`
- **Simulated mode**: Works without `faiss-cpu` via hash-derived stub vectors (dev/test)

### `get_cold_store()` Factory (`services/memory/turboquant_store.py`)
Call instead of instantiating directly. Selects the best available backend at startup:
```python
from services.memory.turboquant_store import get_cold_store
cold_store = get_cold_store(dim=1536, snapshot_path=settings.TURBOQUANT_INDEX_PATH or None)
```
- Returns `TurboQuantColdStore` if `pyturboquant` is installed
- Returns `FaissColdStore` otherwise
- All callers unchanged — both implement the same interface

### `deps.py` Wiring
The memory service factory in `core/deps.py` now calls `get_cold_store()` with the snapshot path from `settings.TURBOQUANT_INDEX_PATH`. Set this in `.env` to enable crash-safe persistence.

### Key Files
| File | Role |
|------|------|
| `services/memory/faiss_cold_store.py` | FAISS cold tier **[NEW v3.1]** |
| `services/memory/turboquant_store.py` | TurboQuant cold tier + `get_cold_store()` factory |
| `services/memory/turboquant.py` | Legacy `TurboQuantMemoryBackend` (kept for reference) |
| `services/memory/memory_store.py` | `ButlerMemoryStore` — HOT/WARM/COLD write routing |

---

### 1.1 Purpose
The Memory service provides **evolving agent memory** for Butler. It does not merely store searchable history; it maintains facts, episodes, identities, relationships, preferences, dislikes, routines, and context signals that can be updated, reconciled, forgotten, and explained.

### 1.2 Responsibilities
- Hybrid memory persistence across graph, vector, relational, and cache layers
- Episodic memory capture for conversations, actions, and outcomes
- Entity resolution and identity linking across people, devices, channels, and sessions
- Fact extraction, reconciliation, contradiction handling, and supersession
- Temporal reasoning support for “what was true then” vs “what is true now”
- Retrieval fusion across graph, vector, keyword, preference, and recency signals
- Context assembly for Orchestrator under token and policy constraints
- User understanding/profile maintenance: interests, dislikes, relationships, routines, and short-term intent
- Provenance, retention, privacy, and forgetting policy enforcement

### 1.3 Boundaries
- Does NOT process business logic
- Does NOT execute tools or workflows
- Does NOT own embedding generation or reranker inference models
- Does NOT perform direct channel delivery or transport handling
- Does NOT expose unconstrained whole-user memory dumps by default

### 1.4 Clear Separation: Memory vs ML

| Aspect | Memory Service | ML Service |
|--------|----------------|-----------|
| Embeddings | Consumes embeddings | Generates embeddings |
| Cross-encoder inference | Coordinates rerank requests | Runs rerank models |
| Retrieval fusion | Owns score fusion and selection | Supplies model outputs |
| Context assembly | Owns token-budgeted context | Supplies model-side helpers |
| Memory extraction policy | Owns memory write rules | Supplies extraction/classification models |

**Flow:** Memory receives write or retrieval intent → requests ML support when embeddings / extraction / rerank inference are needed → applies Butler-owned memory semantics and policies.

### 1.5 Hermes Library Integration
Memory is one of the main Butler consumers of Hermes-backed storage and context helpers.

**Best Hermes reuse targets:**
- `backend/integrations/hermes/hermes_state.py`
- `backend/integrations/hermes/state.py`
- `backend/integrations/hermes/agent/memory_manager.py`
- `backend/integrations/hermes/agent/memory_provider.py`
- `backend/integrations/hermes/agent/context_compressor.py`
- `backend/integrations/hermes/plugins/memory/*`

**Mode classification:**

| Hermes path | Mode |
|---|---|
| `hermes_state.py` | Adapt behind wrapper |
| `state.py` | Active now / compatibility-backed session storage |
| `agent/memory_manager.py` | Adapt behind wrapper |
| `agent/memory_provider.py` | Adapt behind wrapper |
| `agent/context_compressor.py` | Active now / reference for context budget enforcement |
| `plugins/memory/*` | Deferred / pluggable backend inventory |

**Butler still owns:**
- canonical memory schema
- provider activation policy
- temporal / contradiction semantics
- retention and privacy rules
- service-to-service retrieval contracts

See `docs/services/hermes-library-map.md` for the complete path map.

---

## 2. Memory Design Principles

### 2.1 Memory Is Not Just Retrieval
Butler memory must support:
- remembering
- updating
- merging
- superseding
- invalidating
- forgetting
- explaining why something is believed

The service is therefore not just a vector-search layer. It is a **memory engine** with explicit evolution rules.

### 2.2 Core Principles
- **Graph + vector together:** semantic similarity alone is not enough for personal AI memory
- **Soft invalidation over hard delete:** preserve temporal history when facts change
- **Retrieval-time resolution:** avoid collapsing all nuance at write time
- **Provenance-first:** Butler should know why it knows something
- **Negative signals are first-class:** dislikes and repeated rejections matter
- **Short-term and long-term state are separate:** current intent is not the same as durable preference

---

## 3. Architecture

### 3.1 Internal Components

```text
┌─────────────────────────────────────────────────────────────────────┐
│                           Memory Service                           │
├─────────────────────────────────────────────────────────────────────┤
│ Graph Store Client      │ Neo4j relationships, identity, provenance│
│ Vector Store Client     │ Qdrant semantic recall                    │
│ Preference Store Client │ PostgreSQL explicit preferences/constraints│
│ Cache Layer             │ Redis hot context + active profile state  │
├─────────────────────────────────────────────────────────────────────┤
│ Episodic Memory Engine  │ Sessions, actions, outcomes               │
│ Entity Resolution Engine│ People/device/channel identity linking    │
│ Memory Evolution Engine │ merge/update/supersede/contradict         │
│ Retrieval Fusion Engine │ graph+vector+keyword+profile scoring      │
│ Rerank Coordinator      │ delegates rerank to ML [UNIMPLEMENTED]    │
│ Context Builder         │ token-budgeted [PROXY: char-count]        │
│ User Understanding Layer│ interests/dislikes/routines/relationships │
│ Provenance Manager      │ source lineage and evidence               │
│ Retention & Privacy     │ forgetting, expiry, redaction, archive    │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Dependencies

| Dependency | Type | Purpose |
|------------|------|---------|
| Neo4j | External | graph memory, identity graph, provenance edges |
| Qdrant | External | semantic memory retrieval |
| PostgreSQL | External | explicit preferences, dislikes, constraints, structured summaries |
| Redis | External | hot context cache, active profile state, resume/session memory helpers |
| ML Service | Internal | embeddings, extraction inference, rerank inference |
| Object storage | External | archived episodic payloads and compaction artifacts |

### 3.3 BM25 / Keyword Backend
Keyword search must have a real owner. For Butler MVP and early scale, Memory uses **PostgreSQL full-text search** for keyword fallback and exact lexical signals. OpenSearch or a dedicated text engine can be introduced later when operationally justified.

---

## 4. Data Flow

### 4.1 Retrieval Flow

```text
Query Request
      ↓
Optional two-tower candidate generation
  ├─ User ↔ Memory item
  ├─ User ↔ Interest / Topic
  └─ User ↔ Relationship context
      ↓
Query embedding request to ML
      ↓
Parallel retrieval
  ├─ Graph traversal (Neo4j)
  ├─ Vector similarity (Qdrant)
  ├─ Keyword search (PostgreSQL FTS)
  ├─ Preference/profile retrieval
  └─ Episodic recall
      ↓
Retrieval Fusion Engine
      ↓
Rerank Coordinator → ML rerank inference
      ↓
Context Builder
      ↓
Return ranked context package
```

### 4.2 Memory Evolution Pipeline

```text
Raw interaction / imported fact / tool result
      ↓
Event Interpreter
      ↓
Fact & entity extraction
      ↓
Entity resolution
      ↓
Conflict / contradiction detection
      ↓
Memory action decision
  ├─ create
  ├─ reinforce
  ├─ merge
  ├─ supersede
  ├─ contradict
  └─ requires_review
      ↓
Persistence + provenance update
      ↓
Index / cache refresh
```

### 4.3 User Understanding Pipeline

```text
Behavior signals
  ├─ accepted suggestions
  ├─ rejected suggestions
  ├─ repeated topic queries
  ├─ tool usage patterns
  ├─ communication frequency
  └─ explicit stated preferences
      ↓
Preference Extractor + Negative Signal Engine
      ↓
Multi-interest / relationship update
      ↓
Short-term intent + long-term profile refresh
      ↓
Available to retrieval fusion and orchestrator context building
```

---

## 5. Core Logic

### 5.1 Retrieval Fusion Engine

Memory retrieval must not stop at “normalize scores somehow.” Butler uses explicit score fusion.

Two-tower retrieval is useful here as a **candidate-generation primitive**, not as the final truth engine. Its job is to narrow the search space before graph traversal, temporal filters, contradiction checks, and reranking refine the result.

```python
final_candidate_score = (
    alpha * semantic_score +
    beta  * keyword_score +
    gamma * graph_relevance +
    delta * preference_affinity +
    epsilon * relationship_relevance +
    zeta * recency_score +
    eta * stability_score -
    theta * contradiction_penalty -
    iota * dislike_penalty
)
```

The reranker adjusts final ordering, but it does **not** erase all upstream signal engineering.

### 5.2 Rerank Coordinator

Memory does not own reranker models. It owns candidate preparation and fused-ranking semantics.

```python
class RerankCoordinator:
    """[UNIMPLEMENTED] - Currently uses LocalReranker stub"""
    async def rerank(self, query: str, candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
        payload = [self._to_rerank_doc(c) for c in candidates]
        # rerank_scores = await self.ml.rerank(query=query, candidates=payload)
        # return self._merge_rerank_scores(candidates, rerank_scores)
        return candidates  # stub
```

### 5.3 Memory Evolution Actions

Every incoming fact-like write is classified as one of:
- `new`
- `reinforces`
- `updates`
- `contradicts`
- `obsolete`
- `requires_review`

Contradictions should default to **soft invalidation / supersession**, not destructive deletion.

### 5.4 Temporal Memory Model

Every memory item should carry temporal semantics:

```json
{
  "observed_at": "2026-04-18T10:00:00Z",
  "last_confirmed_at": "2026-04-18T10:05:00Z",
  "valid_from": "2026-04-18T10:00:00Z",
  "valid_until": null,
  "freshness_score": 0.82,
  "stability_class": "ephemeral|routine|identity|long_term_fact",
  "supersedes_memory_id": null
}
```

This lets Butler answer:
- what is true now
- what was true then
- what changed
- what is stale but still historically useful

### 5.5 Entity Resolution Engine

Memory must unify entities across channels and artifacts.

Responsibilities:
- alias resolution
- confidence-scored entity merges
- device / channel / person linking
- cross-session identity stitching
- human-review path for sensitive merges

### 5.6 Episodic Memory Engine

Butler should not reduce all interactions to flat conversation vectors.

Episode schema:

```json
{
  "episode_id": "ep_123",
  "user_id": "usr_123",
  "session_id": "ses_456",
  "channel": "mobile",
  "goal": "book dinner",
  "events": [],
  "entities": [],
  "outcome": "completed|failed|abandoned",
  "lessons": [],
  "created_at": "..."
}
```

### 5.7 User Understanding Layer

Memory owns a first-class **User Understanding & Preference Graph**.

It maintains:
- interests
- dislikes / aversions
- important people and relationships
- routines and recurring patterns
- short-term intent state
- long-term stable profile

This is what stops Butler from remembering random facts while still failing to understand the user.

### 5.8 Two-Tower Candidate Retrieval

Memory can optionally use dedicated two-tower retrieval models for fast pre-filtering when corpora become large.

Recommended towers:
- **User ↔ Memory Item** for episodic recall and context retrieval
- **User ↔ Interest / Topic** for profile-aware preference recall
- **User ↔ Person / Relationship Context** for social grounding

Role in pipeline:

```text
user/query/context
      ↓
two-tower retrieval
      ↓
top-K candidates
      ↓
graph + keyword + temporal enrichment
      ↓
fusion + rerank
      ↓
context builder
```

This model family should **not** be used alone for contradiction resolution, approval-sensitive decisions, or final truth ranking.

When deployed, it should sit inside a retrieve-then-rank cascade:

```text
memory corpus
      ↓
two-tower retrieval
      ↓
candidate enrichment (graph, temporal, dislikes, provenance)
      ↓
rerank coordinator
      ↓
context builder
```

---

## 6. API Contracts

### 6.1 Retrieval & Context APIs

```yaml
POST /memory/retrieve
  Request:
    {
      "query": "string",
      "user_id": "uuid",
      "limit": 10,
      "types": ["fact", "episode", "preference", "relationship"],
      "include_superseded": false
    }
  Response:
    {
      "context": [...],
      "token_count": 1500,
      "sources": ["graph", "vector", "keyword", "profile"]
    }

POST /memory/context/build
  Request:
    {
      "user_id": "uuid",
      "query": "string",
      "budget_tokens": 4000,
      "session_id": "uuid"
    }
  Response:
    {
      "parts": [...],
      "token_count": 3920,
      "profile_signals": [...]
    }
```

### 6.2 Write / Evolution APIs

```yaml
POST /memory/store
  Request:
    {
      "type": "fact|episode|conversation|relationship|preference|identity",
      "user_id": "uuid",
      "data": {},
      "metadata": {}
    }

POST /memory/facts/upsert
  Request:
    {
      "user_id": "uuid",
      "fact": {},
      "conflict_policy": "auto|review|required"
    }

POST /memory/reconcile
  Request:
    {
      "user_id": "uuid",
      "memory_ids": ["..."],
      "strategy": "merge|supersede|invalidate"
    }

POST /memory/forget
  Request:
    {
      "user_id": "uuid",
      "memory_id": "uuid",
      "mode": "soft|hard"
    }
```

### 6.3 Episodic & Entity APIs

```yaml
POST /memory/episodes/store
POST /memory/episodes/retrieve
POST /memory/entities/resolve
```

### 6.4 User Understanding APIs

```yaml
POST /memory/profile/update-signals
POST /memory/profile/extract-preferences
POST /memory/profile/extract-dislikes
POST /memory/profile/update-relationships
POST /memory/profile/get-interest-map
POST /memory/profile/get-dislike-map
POST /memory/profile/get-relationship-map
POST /memory/profile/get-active-intent
```

### 6.5 Deliberately Avoided Endpoint
Avoid broad `GET /memory/{user_id}` full dumps by default. If a user summary endpoint is needed later, it must be projection-limited, redacted, and authorization-scoped.

---

## 7. Data Schema

### 7.1 Canonical Memory Item

```json
{
  "memory_id": "uuid",
  "user_id": "uuid",
  "type": "preference|fact|episode|conversation|identity|workflow",
  "content": "...",
  "confidence": 0.91,
  "observed_at": "...",
  "last_confirmed_at": "...",
  "source_type": "chat|voice|vision|tool|import",
  "source_id": "...",
  "sensitivity": "low|medium|high",
  "freshness_score": 0.77,
  "status": "active|superseded|contradicted|archived|forgotten",
  "derived_from": [],
  "entity_refs": [],
  "provenance": {}
}
```

### 7.2 Neo4j Graph Schema

```cypher
// Node families
(u:User {id})
(p:Person {id, display_name})
(i:Identity {id, channel, handle})
(pref:Preference {id, key, explicit})
(d:Dislike {id, key})
(r:Routine {id, name})
(s:SessionIntent {id, focus})
(e:Episode {id, outcome})
(f:MemoryFact {id, status, observed_at})
(dev:Device {id, platform})
(doc:Document {id, source_type})

// Relationship families
(u)-[:INTERESTED_IN {weight, confidence}]->(pref)
(u)-[:DISLIKES {weight, confidence}]->(d)
(u)-[:CLOSE_TO {strength, recency}]->(p)
(u)-[:USES_DEVICE]->(dev)
(u)-[:CURRENTLY_FOCUSED_ON]->(s)
(e)-[:DERIVED_FROM]->(doc)
(f)-[:SUPERCEDES]->(f)
(f)-[:CONTRADICTS]->(f)
(f)-[:OBSERVED_IN]->(e)
(p)-[:CONTACTS_VIA]->(i)
```

### 7.3 Qdrant Payload Design

```python
{
    "memory_id": "uuid",
    "user_id": "uuid",
    "session_id": "uuid",
    "type": "conversation|episode|knowledge|preference|fact",
    "content": "text",
    "source_type": "chat|voice|vision|tool|import",
    "source_id": "...",
    "channel": "mobile|web|voice|mcp|internal",
    "confidence": 0.91,
    "sensitivity": "medium",
    "freshness_score": 0.77,
    "status": "active",
    "entity_refs": ["person:123", "topic:robotics"],
    "fact_refs": ["fact:abc"],
    "created_at": "timestamp"
}
```

Vector dimension should follow the actual deployed embedding model, not a hardcoded ritual default.

### 7.4 PostgreSQL Structured Stores

```sql
CREATE TABLE explicit_preferences (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    category TEXT NOT NULL,
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    confidence NUMERIC,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE explicit_dislikes (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    key TEXT NOT NULL,
    reason JSONB,
    confidence NUMERIC,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE user_constraints (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    constraint_type TEXT NOT NULL,
    value JSONB NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

---

## 8. Caching Strategy

Cache by **semantic purpose**, not fake hardware hierarchy.

### 8.1 Cache Families

| Cache | Purpose | TTL |
|------|---------|-----|
| `hot_context_cache` | recent context bundles | 5 min |
| `preference_cache` | active preference / dislike profile | 30 min |
| `retrieval_result_cache` | query retrieval sets | 5 min |
| `entity_resolution_cache` | alias / match results | 15 min |
| `active_intent_cache` | short-term session focus | 15 min |

### 8.2 Invalidation Strategy
- versioned keys preferred over wildcard scans
- user-profile version bumps invalidate dependent caches
- superseded or contradicted facts invalidate retrieval caches referencing them
- forgetting requests trigger targeted purge + archive policy

---

## 9. Retention, Forgetting, and Privacy

### 9.1 Forgetting Modes
- user-requested deletion
- TTL-based expiry for ephemeral memories
- contradiction-based downgrade / supersession
- summarization compaction for long episodic trails
- privacy-driven redaction for sensitive fields

### 9.2 Policy Table

| Type | Hot | Warm | Archive | Deletion |
|------|-----|------|---------|----------|
| conversation episode | 7 days | 90 days | yes | compaction or delete by policy |
| identity facts | cached selectively | long-lived | yes | never hard-delete without policy |
| explicit preferences | active | long-lived | optional | user-controlled |
| inferred dislikes | active | medium-term | optional | decay + explicit override |
| short-term intent | 15 min cache | no archive by default | no | automatic expiry |

### 9.3 Provenance Requirement
Memory items must preserve:
- source interaction
- extraction method
- derived-from IDs
- confidence
- verifier or review state
- last observed timestamp

Without provenance, Butler cannot safely justify or retract what it “remembers.”

---

## 10. Failure Handling

### 10.1 Failure Modes

| Failure | Behavior | Recovery |
|---------|----------|----------|
| Neo4j unavailable | graph enrichment reduced | vector + keyword fallback |
| Qdrant unavailable | semantic recall reduced | graph + keyword fallback |
| PostgreSQL unavailable | explicit preference writes blocked | retry / queue / degraded read mode |
| Redis unavailable | cache miss + higher latency | direct stores + emergency throttling |
| ML unavailable | no fresh embeddings/rerank/extraction | cached vectors + degraded retrieval |

### 10.2 Circuit Policy
Circuit breakers are per-dependency, not one giant shared switch. Retrieval should degrade gracefully, but write-time contradiction handling may require deferred reconciliation if ML assistance is unavailable.

---

## 11. Performance & Scaling

### 11.1 Targets

| Metric | Target |
|--------|--------|
| Retrieval latency P95 | <200ms excluding upstream LLM response |
| Store latency P95 | <75ms for structured writes |
| Context build latency P95 | <250ms |
| Active profile refresh | <100ms cached / <300ms uncached |

### 11.2 Scaling Strategy
- Neo4j graph indexes + read scaling
- Qdrant distributed collections with payload indexes
- PostgreSQL partitioning / indexing for explicit stores
- Redis cluster for hot-state caches
- object storage for archived episodic payloads

### 11.3 Neo4j / Vector Guidance
- graph should represent identity, relationships, provenance, and temporal edges—not decorative entity wallpaper
- use Neo4j graph traversal as a retrieval enrichment layer, not a separate silo
- avoid hydrating heavyweight vector payloads into graph-heavy read paths unless deliberately designed

---

## 12. Security & Privacy

### 12.1 Encryption
- AES-256-GCM for sensitive data at rest
- envelope encryption for key hierarchy
- field-level encryption for high-sensitivity memory items

### 12.2 Access Control
- users can access only their own memory unless delegated policy exists
- internal services access memory through explicit service identity and scoped permissions
- highly sensitive profile data should be redacted by default in debug/admin surfaces

### 12.3 Memory Poisoning Controls
- provenance tagging on all imported/extracted facts
- confidence thresholds before promotion into durable profile state
- contradiction detection before write confirmation
- quarantine / review path for suspicious or externally injected facts

---

## 13. Observability

### 13.1 Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `memory.retrieve.latency` | Histogram | retrieval latency |
| `memory.store.latency` | Histogram | write latency |
| `memory.fusion.score_mix` | Histogram | score distribution by signal family |
| `memory.entity_resolution.conflicts` | Counter | unresolved entity conflicts |
| `memory.contradictions.detected` | Counter | contradiction events |
| `memory.superseded.total` | Counter | memories superseded |
| `memory.profile.refresh.latency` | Histogram | user-understanding refresh latency |
| `memory.cache.hit_rate` | Gauge | cache performance |

### 13.2 Logged Events

```json
{
  "timestamp": "2026-04-18T10:30:00Z",
  "event": "memory.reconcile",
  "user_id": "user123",
  "memory_id": "mem_abc",
  "action": "supersede",
  "source_type": "chat",
  "confidence": 0.91,
  "derived_from": ["msg_1", "msg_2"]
}
```

---

## 14. Testing Strategy

### 14.1 Required Tests
- graph + vector + keyword retrieval fusion
- contradiction / supersession behavior
- temporal recall correctness
- entity resolution confidence thresholds
- episodic write + retrieve flow
- explicit dislike penalty in ranking
- forgetting and redaction correctness
- provenance preservation across updates

### 14.2 Benchmark Expectations
- benchmark retrieval with and without graph enrichment
- benchmark cache hit vs cache miss paths
- benchmark active-profile and short-term intent refresh
- benchmark degraded-mode retrieval with one dependency unavailable

---

## 15. Butler User Understanding Layer

### 15.1 Purpose
Build a dynamic, multi-interest, negative-aware, relationship-aware user profile similar to modern recommendation and social-graph systems.

### 15.2 Responsibilities
- infer interests from repeated behavior
- infer dislikes from explicit and implicit negative signals
- map and rank relationships
- track short-term vs long-term preferences
- maintain context-specific preference state
- expose profile features to Orchestrator and retrieval fusion

### 15.3 Signals

**Positive signals:**
- accepted suggestion
- repeated use
- long dwell / repeated revisit
- save / bookmark
- repeated topic queries

**Negative signals:**
- dismiss
- skip
- explicit dislike
- undo
- immediate abandon
- correction after recommendation

**Relationship signals:**
- reply speed
- message frequency
- channel used
- co-occurrence in tasks
- calendar association

### 15.4 Ranking Rule

```python
profile_affinity_score = (
    alpha * interest_weight +
    beta * relationship_strength +
    gamma * recency +
    delta * acceptance_rate -
    epsilon * dislike_penalty
)
```

This profile signal is fused into retrieval and context-building decisions, not treated as a separate toy feature.

---

## 16. Implementation Phases

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Vector (Qdrant) and Relational (Postgres) core stores | [IMPLEMENTED] |
| 2 | Hybrid Retrieval Fusion and Context Builder | [IMPLEMENTED] |
| 3 | Cross-Encoder Reranker integration (via ML HeavyRanker) | [IMPLEMENTED] |
| 4 | TurboQuant Cold Store and Long-Term Context archival | [IMPLEMENTED] |
| 5 | Neo4j Graph Memory and Knowledge Extraction Engine | [PARTIAL] |

---

*Document owner: Memory Team*  
*Last updated: 2026-04-19*  
*Version: 3.0 (Active)*
