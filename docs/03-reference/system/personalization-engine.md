# Butler Personalization and Ranking Engine

> **Version:** 1.0  
> **Updated:** 2026-04-19  
> **Owner:** Butler ML Team  
> **Sources:** The Algorithm (candidate generation + graph traversal), The Algorithm ML (ButlerHIN, recap/heavy ranker)

---

## Overview

Butler's personalization engine decides:
- **What memory** to surface in the current context
- **What notifications/tasks** to prioritize
- **What agent** (or sub-agent) should respond
- **What action** to suggest next

This is inspired by Twitter's recommendation pipeline architecture but rewritten Butler-native — purpose-built for personal AI OS personalization rather than social media engagement.

---

## Architecture

```
User request / session event
        │
        ▼
[ Candidate Generation ]        ← graph traversal + ANN retrieval + recency
        │
        ▼
[ Feature Hydration ]           ← session signals, preference features, temporal
        │
        ▼
[ LightRanker ]                 ← fast heuristic ranking (every request)
        │
        ▼
[ HeavyRanker (Phase 3) ]       ← neural ranking model (sampled / async)
        │
        ▼
[ Re-ranked candidates ]        ← injected into agent context
        │
        ▼
[ Recap / Summarization ]       ← long-horizon session summarization
```

---

## Stage 1: Candidate Generation

Inspired by The Algorithm's candidate generation services.

**Sources:**
| Source | Implementation | Weight |
|---|---|---|
| Recent episodic memory | Postgres time-range query | High |
| Semantic ANN search | Qdrant vector search | High |
| Graph neighborhood (ButlerHIN) | Neo4j 2-hop traversal | Medium |
| Collaborative signals (cross-session) | Redis sorted set | Low |
| Pinned/bookmarked items | User preference store | High (if relevant) |

**Default candidate budget:** 200 items per request  
**DEGRADED mode (health-aware):** 50 items — K-Graph skipped (see CandidateMixer load shedding)  
**UNHEALTHY mode:** Returns empty — no retrieval

The `CandidateMixer` in `backend/services/ml/mixer.py` implements this stage.

---

## Stage 2: Feature Hydration

Each candidate is enriched with features for ranking:

| Feature | Source | Type |
|---|---|---|
| `recency_score` | entity timestamp | float |
| `access_frequency` | memory access log (Redis) | float |
| `user_interest_score` | preference store | float |
| `session_relevance` | cosine similarity to current context embedding | float |
| `task_priority` | user-set priority or inferred urgency | int [0-3] |
| `entity_confidence` | knowledge graph confidence score | float |
| `is_pinned` | user preference flag | bool |
| `recent_correction` | user corrected this memory recently | bool |

Features are read from:
- Redis (online feature store): sub-ms latency features
- Postgres (structured preference store): user settings, priorities
- Qdrant (similarity features): ANN computed at retrieval time

---

## Stage 3: LightRanker

Fast, heuristic-based ranking running on every request. No ML model — pure scoring function.

```python
score = (
    0.35 * recency_score
  + 0.30 * session_relevance
  + 0.20 * user_interest_score
  + 0.10 * access_frequency
  + 0.05 * entity_confidence
  + (0.15 if is_pinned else 0)
  - (0.20 if recent_correction else 0)
)
```

Weights are configurable per-user and per-context type. Served in < 5ms.

---

## Stage 4: HeavyRanker (Phase 3)

A neural ranking model inspired by The Algorithm ML's heavy ranker and TwHIN graph embeddings, rewritten Butler-native as **ButlerHIN** (Butler Heterogeneous Interaction Network).

**ButlerHIN** computes embeddings for:
- Users (identity + behavioral profile)
- Topics (semantic clusters from memory)
- Entities (people, projects, events)
- Interactions (conversation sessions)

These are heterogeneous graph embeddings — different entity types share an embedding space but with type-specific encoders.

**Use in ranking:**
- `candidate_embedding ⊙ user_embedding` → relevance score
- Combined with LightRanker scores via learned blending layer

**Serving strategy:**
- HeavyRanker runs async (not on hot path)
- Results cached in Redis with 30-second TTL
- LightRanker used as fallback when HeavyRanker is unavailable

---

## Stage 5: Recap and Summarization Ranking

Inspired by The Algorithm ML recap ranking — applied to memory summarization and long-horizon recall.

When the session context budget approaches its limit:
1. Oldest epoch of conversation is **recap-ranked** — scored for summary-worthiness
2. High-ranking items are preserved verbatim in episodic memory
3. Low-ranking items are summarized at higher compression
4. The summary is appended to the session context window

This ensures the most important facts survive across session epochs.

---

## Use Cases

| Signal | Personalization Question |
|---|---|
| Memory retrieval | "What does the user need to remember right now?" |
| Notification prioritization | "Which of 12 pending notifications should I surface first?" |
| Agent routing | "Should this message go to coding agent, research agent, or general?" |
| Sub-agent spawning | "Should I spawn a specialized sub-agent for this task?" |
| Canvas suggestion | "What should I add to the user's active canvas?" |

---

## Online Feature Serving

- Redis sorted sets for access frequency counters (`ZINCRBY`)
- Redis hashes for per-user preference snapshots (refreshed every 5 minutes)
- Qdrant for semantic similarity (async vector lookup)
- No Postgres queries on the hot path — only Redis + in-memory cache

---

## Reference

- `backend/services/ml/mixer.py` — CandidateMixer implementation
- `backend/services/ml/ranking.py` — LightRanker scoring
- `docs/03-reference/system/digital-twin-memory.md` — Memory layer sources
- `docs/03-reference/system/model-improvement-pipeline.md` — How HeavyRanker is trained
- `docs/02-services/ml.md` — ML service specification
- `docs/02-services/search.md` — Search service integration


## Harvested Capabilities: Personalization Engine
**Source: the-algorithm**
- **Product Mixer Pipeline Execution:** Composition framework for creating resilient, multi-stage recommendation pipelines (Sourcing -> Light Rank -> Heavy Rank -> Filter).
- **GraphJet Collaborative Filtering:** In-memory, real-time traversal of engagement graphs to generate highly personalized candidate sets in <50ms.
- **SimClusters (Community Embeddings):** Using community overlap matrices instead of pure individual vectors to solve cold-start and discoverability issues.

