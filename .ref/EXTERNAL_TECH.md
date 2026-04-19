# External Technology Adoption Reference

> **Status:** Research Complete
> **Version:** 1.0
> **Last Updated:** 2026-04-18
> **Source:** Claude Code Agent Research

---

## Executive Summary

This document analyzes four external technology stacks for Butler integration:

| Technology | License | Butler Fit | Adoption Status |
|------------|---------|------------|-----------------|
| pyturboquant | MIT | **RECOMMENDED** | Direct integration |
| TriAttention | Apache-2.0 | **RECOMMENDED** | Direct integration |
| twitter/the-algorithm | AGPL-3.0 | **ARCHITECTURE ONLY** | Design inspiration |
| twitter/the-algorithm-ml | AGPL-3.0 | **ARCHITECTURE ONLY** | Design inspiration |
| twitter-server | Apache-2.0 | **PATTERNS ONLY** | Service operability |

---

## 1. pyturboquant

### Overview

- **Purpose:** Online vector compression for embedding stores
- **License:** MIT
- **Repository:** pyturboquant
- **Key Capability:** Near-zero indexing time, online ingestion, dramatic RAM savings at 4 bits

### Butler Integration Points

#### Where it fits
- **Memory Service** - Compressed vector store for episodic memory
- **Search Service** - Archive recall for RAG
- **Data Layer** - Embedding storage tier

#### Architecture Pattern: Three-Tier Memory

```
Hot Cache: Redis
  ↓
Active Index: Qdrant/native ANN
  ↓
Compressed Store: TurboQuantIndex
  ↓
Cold Archive: Object storage
```

#### Best Use Cases

1. **Long-term personal memory archive**
   - 10M+ memory chunks across years
   - Local/private deployment
   - RAM-constrained environments

2. **Organization memory**
   - Documents, chats, meetings, actions compressed

3. **Social interest graph**
   - User-to-topic embeddings
   - User-to-person embeddings

#### Integration Code

```python
class TurboQuantMemoryBackend:
    def __init__(self, dim: int, bits: int = 4, metric: str = "ip"):
        self.index = TurboQuantIndex(dim=dim, bits=bits, metric=metric)
        self.ids: list[str] = []
        self.meta: list[dict] = []

    def add(self, ids: list[str], vectors: np.ndarray, metadata: list[dict]) -> None:
        tensor = torch.tensor(vectors, dtype=torch.float32)
        self.index.add(tensor)
        self.ids.extend(ids)
        self.meta.extend(metadata)

    def search(self, query_vector: np.ndarray, k: int = 20) -> list[dict]:
        q = torch.tensor(query_vector[None, :], dtype=torch.float32)
        distances, indices = self.index.search(q, k=k)
        results = []
        for score, idx in zip(distances[0].tolist(), indices[0].tolist()):
            if idx >= 0:
                results.append({
                    "id": self.ids[idx],
                    "score": score,
                    "metadata": self.meta[idx],
                })
        return results
```

#### Current Limitations

- Search is O(n) per query
- IVF/sub-linear search on roadmap
- Use as recall layer, not replacement for all ANN

---

## 2. TriAttention

### Overview

- **Purpose:** KV cache compression for long-context LLM inference
- **License:** Apache-2.0
- **Repository:** TriAttention
- **Key Capability:** Up to 10.7x KV memory reduction, 2.5x throughput gain

### Butler Integration Points

#### Where it fits
- **ML Service** - Local model runtime
- **Inference Path** - Long-context serving
- **Private Butler** - Single GPU deployment

#### Architecture Pattern: Dual Inference Classes

```
Class 1: Fast Chat
├── Small/medium models
├── TriAttention optional
└── Standard conversational path

Class 2: Long-Context Planner
├── Larger context budget
├── TriAttention enabled
└── Memory-heavy orchestration
```

#### Runtime Configuration

```yaml
runtime_profiles:
  local_reasoning_qwen3:
    provider: vllm
    triattention: true
    max_model_len: 32768
    kv_budget: 12000
    prefix_caching: false
    max_num_batched_tokens: 1024
    stats_path: /models/stats/qwen3_stats.pt

  cloud_fast_general:
    provider: external_api
    triattention: false
```

#### Important Caveats

1. **Prefix caching must be disabled** - Incompatible with KV compression
2. **Model-specific** - Requires supported model family
3. **Chat settings differ** - Use larger KV budget, cap prefill tokens

#### Best Use Cases

- Long personal assistant sessions
- Agentic planning workflows
- Local Private Butler (24GB GPU)
- Research/coding/debugging mode

---

## 3. twitter/the-algorithm

### Overview

- **Purpose:** Recommendation system architecture
- **License:** AGPL-3.0 ⚠️
- **Key Capability:** Multi-stage candidate sourcing + ranking pipeline

### ⚠️ LICENSING WARNING

This repository is under **AGPL-3.0**. This means:
- If modified and run over a network, you must offer source to users
- Direct code integration has legal implications
- Safe approach: Reimplement ideas clean-room style

### Butler Architecture Patterns to Adopt

| X Component | Butler Equivalent |
|------------|----------------|
| user-signal-service | User Signal Service |
| unified-user-actions | Butler Event Stream |
| real-graph | Butler Relationship Graph |
| TwHIN | ButlerHIN Embeddings |
| graph-feature-service | Feature Service |
| product-mixer | Action Mixer |
| trust_and_safety_models | Policy/Safety Filter |

### Components to Build

- **User Signal Service** - Track clicks, ignores, confirms, denials
- **Candidate Service** - Multi-source candidate retrieval
- **Feature Service** - User/action affinity features
- **Action Ranker** - Heavy ranker for action selection
- **Policy Filter** - Trust/safety filtering layer
- **Action Mixer** - Final composition

### NOT to Do

- Copy Scala/JVM service boundaries as-is
- Import tweet-centric schemas
- Use feed-serving assumptions

---

## 4. twitter/the-algorithm-ml

### Overview

- **Purpose:** ML models for recommendation (embeddings, rankers)
- **License:** AGPL-3.0 ⚠️
- **Key Models Representation-Scorer**

### What to Learn From

- **TwHIN:** Heterogeneous graph embeddings
- **Heavy Ranker:** Final-funnel scoring
- **Representation Manager:** Multi-entity embedding system

### Implementation Approach

Build Butler-native equivalents in Python:
- User/task/contact/workflow embeddings
- Cross-encoder rankers
- Feature store for pairwise features

---

## 5. twitter-server

### Overview

- **Purpose:** Production service template
- **License:** Apache-2.0
- **Key Features:** Admin HTTP, tracing, stats, lifecycle

### Patterns to Adopt

Every Butler service should have:

- `/health/live` - Liveness probe
- `/health/ready` - Readiness probe  
- `/health/startup` - Startup probe
- `/admin/metrics` - Metrics endpoint
- `/admin/config` - Configuration view
- `/admin/build` - Build info
- `/admin/circuit-breakers` - Circuit breaker status

---

## Integration Roadmap

### Phase 1 (Immediate)

| Task | Owner | Priority |
|------|------|----------|
| Add TurboQuantMemoryBackend to Memory | Memory | HIGH |
| Implement compressed recall pipeline | Memory | HIGH |
| Add TriAttention vLLM provider | ML Runtime | HIGH |

### Phase 2 (Near-term)

| Task | Owner | Priority |
|------|------|----------|
| Build candidate retrieval layer | ML | MEDIUM |
| Add lightweight ranker | ML | MEDIUM |
| Add user signal store | Data | MEDIUM |

### Phase 3 (Future)

| Task | Owner | Priority |
|------|------|----------|
| Heavy ranker implementation | ML | LOW |
| ButlerHIN embeddings | ML | LOW |
| Action Mixer layer | Orchestrator | LOW |

---

## Licensing Summary

| Technology | License | Direct Use | Reference Only |
|-----------|---------|------------|----------------|
| pyturboquant | MIT | ✅ Yes | - |
| TriAttention | Apache-2.0 | ✅ Yes | - |
| twitter/the-algorithm | AGPL-3.0 | ❌ No | ✅ Yes |
| twitter/the-algorithm-ml | AGPL-3.0 | ❌ No | ✅ Yes |
| twitter-server | Apache-2.0 | ✅ Patterns | - |

---

*Document owner: Architecture Team*
*Research complete: 2026-04-18*