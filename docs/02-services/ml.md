# ML Service - Technical Specification

> **For:** Engineering, ML Team  
> **Status:** Active (v3.1) — SmartRouter fixed; TriAttention config hardened
> **Version:** 3.1
> **Reference:** Butler intelligence platform — understanding, representation, retrieval, ranking, prediction, and inference serving  
> **Last Updated:** 2026-04-19

---

## 0. v3.1 ML Hardening Notes

> **Updated in v3.1 (2026-04-19)**

### Bug Fix: `TRIATTENTION_ENABLED` Settings Key
The `get_smart_router()` dependency factory in `core/deps.py` was referencing `settings.TRI_ATTENTION_ENABLED` (camelCase underscore mismatch). The correct key in `infrastructure/config.py` is `TRIATTENTION_ENABLED`. Fixed in v3.1.

### `get_smart_router()` — Now Properly Exposed
`ButlerSmartRouter` is now provisioned via a proper `get_smart_router()` async dependency factory in `core/deps.py`. Previously it was called but the function didn't exist (runtime `NameError` at first request). Fixed in v3.1.

### SmartRouter T0–T3 Tiers
The tiering logic in `services/ml/smart_router.py` is active:
| Tier | Threshold | Action |
|------|-----------|--------|
| T0 | Pattern-matched simple response | Early return — no LLM call |
| T1 | Low-complexity, no tools | Cheap model (fast path) |
| T2 | Standard intent | Default model |
| T3 | Research/complex multi-step | Frontier model + DeepResearch |

### TriAttention (Profile B)
- Controlled by `TRIATTENTION_ENABLED` + `TRIATTENTION_HOST` in `.env`
- When enabled: `MLRuntimeManager` routes Profile B requests to external vLLM host with TriAttention KV compression
- `prefix_caching` is disabled automatically when TriAttention is active (enforced by `MLService`)
- **Status**: Integration structure in place; requires a deployed vLLM instance with TriAttention plugin

### Key Files
| File | Role |
|------|------|
| `services/ml/smart_router.py` | T0–T3 routing logic |
| `services/ml/runtime.py` | MLRuntimeManager — model profile resolution and execution |
| `services/ml/registry.py` | Model registry with rollout governance |
| `services/ml/ranking.py` | LightRanker (heuristic + feature signals) |
| `services/ml/features.py` | FeatureService — online behavioral signals |
| `core/deps.py` | `get_smart_router()` factory **[FIXED v3.1]** |

---

### 1.1 Purpose
The ML service is Butler's **intelligence platform** - a model platform for understanding, representation, retrieval, ranking, prediction, and inference serving across Butler services.

This is NOT a box of ML endpoints. This is a platform that supports:
- Intent understanding (tiered)
- Embeddings and representation
- Multi-stage retrieval and ranking
- Calibration and abstention
- Prediction and proactive signals
- Serving tiers (cheap to heavy)
- Feature store for online/offline parity
- Model registry with rollout governance

### 1.2 Responsibilities

**A. Understanding**
- Intent classification with confidence calibration
- Entity extraction
- Ambiguity detection
- Fallback classification (LLM-backed)
- Multi-intent support
- Abstain/clarify mode

**B. Representation**
- Text embeddings (dense)
- Rerank embeddings
- User/profile embeddings
- Workflow/tool/topic embeddings
- Relationship-context embeddings

**C. Retrieval**
- Two-tower candidate generation
- ANN query support
- Recall monitoring

**D. Ranking**
- Lightweight scorer
- Heavy reranker (cross-encoder)
- Calibration
- Diversity/freshness suppression
- Policy-aware final selection

**E. Prediction**
- Next-action prediction
- Next-tool prediction
- Next-workflow prediction
- Proactive timing prediction
- Surface selection prediction

**F. Platform**
- Feature store (online/offline parity)
- Model registry and versioning
- Evaluation pipeline
- Deployment/rollout policies
- Serving policies with batching

### 1.3 Boundaries

| Service | Separation |
|---------|-----------|
| Memory | Memory stores/queries. ML generates embeddings, rankers, predictors. Clear retrieval-first contract. |
| Orchestrator | ML provides signals. Orchestrator decides action. No silent action-driving. |
| Gateway | Gateway handles transport. ML handles inference. |
| Tools | Tools own tool execution. ML recommends which tools. |

**Service does NOT own:**
- Long-term data storage (Memory)
- Action execution (Tools/Orchestrator)
- User input transport (Gateway)
- Credential management (Auth)

### 1.4 Hermes Library Integration
ML is a **secondary consumer** of Hermes ML compatibility code.

**Best Hermes reuse targets:**
- `agent/model_metadata.py` for provider metadata and context-window knowledge
- `agent/prompt_caching.py` for provider prompt-cache behavior
- `agent/usage_pricing.py` for token/cost accounting support

**Not delegated to Hermes:**
- Butler model ownership contracts
- Embedding generation contracts
- Evaluation thresholds
- Serving lifecycle
- Feature store design

| Hermes path | Mode |
|---|---|
| `agent/model_metadata.py` | Active now |
| `agent/prompt_caching.py` | Adapt behind wrapper |
| `agent/usage_pricing.py` | Active now |

See `docs/services/hermes-library-map.md` for complete path map.

---

## 2. Architecture

### 2.1 Platform Architecture (Online/Offline Split)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  Offline Data/Event Plane              │
├─────────────────────────────────────────────────────┤
│  - User interactions, feedback, annotations        │
│  - Feature pipelines                               │
│  - Training datasets                              │
│  - Evaluation jobs                               │
│  - Label collection                              │
└─────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Model Platform                      │
├─────────────────────────────────────────────────────┤
│  - Training jobs                                    │
│  - Model registry + versioning                    │
│  - Validation + shadow mode                       │
│  - Canary/rollout policies                        │
│  - Drift monitoring                              │
│  - Embedding version migration                   │
└─────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Online Inference Plane            │
├─────────────────────────────────────────────────────┤
│  ├─ Understanding Models (intent, entity, NER)   │
│  ├─ Embedding Models (dense, rerank)                │
│  ├─ Retrieval Models (two-tower, ANN)               │
│  ├─ Ranking Models (light scorer, heavy reranker)   │
│  ├─ Prediction Models (next-action, next-tool)     │
│  └─ Serving Layer (batching, cache, routing)       │
└─────────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Consumers                        │
├─────────────────────────────────────────────────────┤
│  - Orchestrator (intent, recommendations)             │
│  - Memory (embeddings, recall candidates)          │
│  - Tools (tool recommendations)                    │
│  - Realtime (prediction signals)                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Retrieval → Ranking Cascade

```
Text query
     ↓
Stage 1: Two-tower retrieval (ANN - optimized for recall)
     ↓
Top-K candidates (e.g., 100)
     ↓
Stage 2: Lightweight scorer (fast, feature-based)
     ↓
Top-20 candidates
     ↓
Stage 3: Heavy reranker (cross-encoder / feature-rich)
     ↓
Top-5 candidates
     ↓
Stage 4: Policy filter + calibration + diversity
     ��
Final selection (passed to Orchestrator)
```

**Rule:** Retrieve first, then enrich, rerank, and decide. Two-tower narrows the candidate set; Butler services still rely on graph logic, policy checks, and orchestrator reasoning for final decisions.

---

## 3. Model Definitions

### 3.1 Intent Classifier (Tiered)

| Tier | Model | Purpose | Latency Target |
|------|------|---------|----------------|
| T0 | Rules + exact match | Deterministic shortcuts | <5ms |
| T1 | Small fast classifier | Simple intent, high confidence | <20ms |
| T2 | Medium classifier | Structured intent + entity | <50ms |
| T3 | LLM-backed | Ambiguity, multi-intent, fallback | <500ms |

**Output contract:**
```json
{
  "intent": "send_message",
  "confidence": 0.95,
  "tier": "T1",
  "alternatives": [
    { "intent": "set_reminder", "confidence": 0.03 }
  ],
  "entities": { "to": "mom", "message": "be home soon" },
  "requires_clarification": false,
  "multi_intent": false
}
```

**Confidence handling:**
- Calibration curve tracking
- Threshold-based abstention
- "Ask clarification" trigger when confidence < 0.7
- Unknown intent detection (open-set robustness)

### 3.2 Embedding Model

```yaml
embedding_families:
  dense_text:
    model: "BAAI/bge-large-en-v1.5"
    dimensions: 1024
    max_tokens: 512
    normalized: true
    lifecycle: "active"
    
  rerank:
    model: "BAAI/bge-reranker-v2"
    dimensions: 1024
    max_tokens: 512
    lifecycle: "active"
    
  multilingual:
    model: "BAAI/bge-m3"
    dimensions: 1024
    max_tokens: 512
    multilingual: true
    lifecycle: "deferred"
```

**Response contract:**
```json
{
  "embedding": [0.1, 0.2, ...],
  "model_id": "bge-large-en-v1.5",
  "dimensions": 1024,
  "token_count": 128,
  "truncation_applied": false,
  "normalized": true,
  "embedding_version": "v2"
}
```

### 3.3 Two-Tower Retrieval Models

| Tower Pair | Purpose | Primary Consumer |
|------------|---------|------------------|
| User ↔ Workflow | Workflow candidate generation | Orchestrator |
| User ↔ Tool | Tool candidate generation | Orchestrator / Tools |
| User ↔ Memory Item | Memory recall candidates | Memory |
| User ↔ Interest / Topic | Profile-aware preference | Memory |
| User ↔ Relationship | Social-context retrieval | Memory / Orchestrator |

**Training signals (positive):**
- accepted suggestion
- executed workflow
- chosen tool
- retrieval candidate used in final answer

**Training signals (negative):**
- ignored suggestion
- rejected workflow
- corrected recommendation
- dismissed memory candidate

### 3.4 Prediction Models

**Use cases:**
- Next likely tool
- Next likely workflow
- Next likely response action
- Proactive prompt timing
- Active surface selection

**Output contract:**
```json
{
  "predictions": [
    { "action": "set_reminder", "probability": 0.45 },
    { "action": "send_message", "probability": 0.30 }
  ],
  "uncertainty": 0.15,
  "context_window": ["search_web", "send_message"],
  "device_channel": "mobile"
}
```

---

## 4. Feature Platform

### 4.1 Online/Offline Parity

The ML service MUST have feature store capabilities for both training and inference.

| Feature Type | Offline (Training) | Online (Inference) |
|------------|-----------------|-------------------|
| User features | Batch extract | API endpoint |
| Context features | Batch extract | API endpoint |
| Temporal features | Timestamp pipeline | Real-time clock |
| Device features | Logged |API call |

### 4.2 Feature Serving API

```yaml
GET /ml/features/online
  Request:
    { "user_id": "...", "feature_names": ["interaction_count", "preferred_tools"] }
  Response:
    { "features": { "interaction_count": 150, "preferred_tools": ["search", "send"] } }
```

### 4.3 Freshness SLAs

| Feature Category | Max Staleness |
|---------------|-------------|
| User interaction count | <5 min |
| Tool preferences | <1 hour |
| Temporal patterns | <24 hours |
| Relationship context | <1 hour |

---

## 5. Model Serving

### 5.1 Serving Tiers

| Tier | Models | Use Case | Latency Target |
|------|-------|--------|----------|
| Fast | intent T0/T1, embeddings | Classification, similarity | <50ms |
| Balanced | light scorers, medium classifiers | Pre-ranking | <100ms |
| Heavy | reranker, LLM fallback | Deep ranking, ambiguity | <500ms |
| Batch | all models | Retraining, evaluation | Best throughput |
| Edge | distilled models | On-device hints | <10ms |

### 5.2 Dynamic Batching

For high-throughput serving, implement dynamic batching:
- Max batch size: configurable
- Max wait time: 50ms default
- Backpressure handling: queue depth limits
- Cancellation: graceful request drop

### 5.3 Model Registry and Rollout

```yaml
model_registry:
  intent_v2:
    path: "s3://models/intent/v2"
    status: "production"
    rollout: "100%"
    metrics: "accuracy=0.92"
    
  intent_v3:
    path: "s3://models/intent/v3"
    status: "canary"
    rollout: "10%"
    shadow_of: "intent_v2"
    metrics: "accuracy=0.94"
    
rollout_policy:
  canary_duration: "24h"
  metrics_to_watch: ["accuracy", "latency_p99", "error_rate"]
  auto_promote: true if delta > 0.01
  rollback_on: "accuracy_drop > 0.02"
```

### 5.4 Fallback Chain

```python
class ModelFallback:
    async def predict(self, input_data):
        # Try fast path first
        try:
            return await self.fast_model.predict(input_data)
        except ModelOverloadedError:
            # Fall back to warm pool
            return await self.warm_pool.predict(input_data)
        except Exception:
            # Final fallback - return abstain
            return {"abstain": True, "reason": "model_unavailable"}
```

---

## 6. Training Pipeline

### 6.1 Event Classes

For Butler feedback loops, collect these event classes:

| Event | Source | Training Use |
|------|-------|--------------|
| intent.accepted | Orchestrator | Intent classifier |
| intent.rejected | Orchestrator | Intent classifier (negative) |
| plan.succeeded | Orchestrator | Recommendation |
| plan.failed | Orchestrator | Recommendation |
| tool.suggestion.accepted | Tools | Tool ranker |
| tool.suggestion.rejected | Tools | Tool ranker |
| memory.candidate.used | Memory | Retrieval |
| memory.candidate.ignored | Memory | Retrieval |
| approval.granted | Orchestrator | Policy |
| approval.denied | Orchestrator | Policy |
| workflow.completed | Orchestrator | Prediction |
| workflow.abandoned | Orchestrator | Prediction |
| proactive.accepted | Orchestrator | Prediction |
| proactive.dismissed | Orchestrator | Prediction |
| response.edited | User | Ranking calibration |

### 6.2 Retraining Triggers

| Model | Schedule | Performance Trigger | Data Trigger |
|-------|----------|-----------------|---------------|
| Intent | Weekly | accuracy < 85% | +10K samples |
| Embeddings | Monthly | recall < 80% | +50K samples |
| Recommendations | Daily | hit_rate < 25% | N/A |
| Reranker | Weekly | ndcg < 0.75 | +5K samples |

---

## 7. Evaluation

### 7.1 Tiered Metrics

**Intent:**
- accuracy, macro F1, calibration error, abstain rate, clarification success rate

**Retrieval:**
- Recall@K, candidate coverage, latency per stage, retrieval freshness

**Ranking:**
- NDCG@K, MRR, preference/dislike suppression, diversity constraints

**Prediction:**
- Precision@1, MRR, time-aware accuracy, proactive usefulness rate

**Serving:**
- P95/P99 by model, cost per 1K inferences, GPU utilization, batch efficiency, cache hit ratio

### 7.2 Evaluation Pipeline

```python
class EvaluationPipeline:
    async def run_daily_evaluation(self):
        results = {}
        
        # Intent
        intent_data = await load_latest_dataset("intent")
        results["intent"] = await self.evaluate_intent(intent_data)
        
        # Retrieval
        retrieval_data = await load_latest_dataset("retrieval")
        results["retrieval"] = await self.evaluate_retrieval(retrieval_data)
        
        # Ranking
        ranking_data = await load_latest_dataset("ranking")
        results["ranking"] = await self.evaluate_ranking(ranking_data)
        
        # Serving
        results["serving"] = await self.evaluate_serving()
        
        await self.check_thresholds(results)
        return results
```

---

## 8. API Contracts

### 8.1 Intent

```yaml
POST /ml/intent/classify
  Request: { "text": "...", "context": {}, "options": {} }
  Response: { "intent": "...", "confidence": 0.95, "tier": "T1", ... }
```

### 8.2 Embeddings

```yaml
POST /ml/embed
  Request: { "text": "...", "model": "bge-large", "normalize": true }
  Response: { "embedding": [...], "model_id": "...", "dimensions": 1024, ... }
```

### 8.3 Retrieval

```yaml
POST /ml/retrieve/workflows
  Request: { "user_id": "...", "limit": 10 }
  Response: { "candidates": [{ "workflow_id": "...", "score": 0.95 }] }

POST /ml/retrieve/tools
  Request: { "user_id": "...", "context": {}, "limit": 5 }
  Response: { "candidates": [{ "tool_id": "...", "score": 0.88 }] }

POST /ml/retrieve/memory-candidates
  Request: { "user_id": "...", "query": "...", "limit": 5 }
  Response: { "candidates": [{ "memory_id": "...", "score": 0.82 }] }
```

### 8.4 Ranking

```yaml
POST /ml/rerank
  Request: { "query": "...", "candidates": [...], "policy_filter": true }
  Response: { "ranked": [...], "calibrated_scores": [...] }
```

### 8.5 Calibration

```yaml
POST /ml/calibrate
  Request: { "model": "intent_v2", "dataset": "calibration_set" }
  Response: { "calibration_curve": [...], "abstain_threshold": 0.7 }
```

### 8.6 Features

```yaml
GET /ml/features/online
  Request: { "user_id": "...", "feature_names": [...] }
  Response: { "features": {...}, "freshness": "2m" }
```

### 8.7 Model Registry

```yaml
GET /ml/models/status
  Response: { "models": [{ "name": "intent_v2", "status": "production", "rollout": "100%" }] }

POST /ml/models/rollback
  Request: { "model": "intent_v2" }
  Response: { "status": "rolled_back", "previous": "intent_v1" }
```

---

## 9. Observability

### 9.1 ML-Specific Metrics

| Metric | Type | Alert Threshold |
|--------|------|----------------|
| retrieval.recall.proxy | gauge | <0.80 |
| ranker.agreement.drift | gauge | >0.05 |
| calibration.drift | gauge | >0.02 |
| serving.gpu.utilization | gauge | <50% |
| serving.batch.fill_rate | gauge | <0.60 |
| serving.cost.per_1k | histogram | >$0.50 |
| feature.freshness.lag | histogram | >300s |
| embedding.version.mismatch | counter | >100/day |

### 9.2 Trace Attributes

- butler.model_id
- butler.model_tier
- butler.retrieval_stage
- butler.candidate_count

---

## 10. Runbook Quick Reference

### 10.1 Model Performance Alert

```bash
# Check evaluation
curl http://ml:8006/metrics/evaluation

# View recent predictions
kubectl logs -l app=ml | grep "prediction" | tail -100

# Rollback model
curl -X POST http://ml:8006/ml/models/rollback -d '{"model": "intent_v3"}'
```

### 10.2 High Latency

```bash
# Check GPU
nvidia-smi

# Check batch queue
curl http://ml:8006/workers/status

# Scale
kubectl scale deployment/ml-worker --replicas=6
```

### 10.3 Serving Failure

```bash
# Check fallback chain
curl http://ml:8006/ml/models/fallback_status

# Clear warm cache
curl -X POST http://ml:8006/cache/clear
```

---

## 11. Implementation Phases

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Basic classifiers, embeddings, and served runtime | [IMPLEMENTED] |
| 2 | Feature Store (Signal Store) and Lightweight Ranker | [IMPLEMENTED] |
| 3 | Federated CandidateMixer and HeavyRanker (Cross-Encoder) | [IMPLEMENTED] |
| 4 | SmartRouter (T0-T3) and Tri-Attention Serving | [IMPLEMENTED] |
| 5 | Distributed training and automated model calibration | [UNIMPLEMENTED] |

---

*Document owner: ML Team*  
*Last updated: 2026-04-19*  
*Version: 3.0 (Active)*

(End of file - total 529 lines)