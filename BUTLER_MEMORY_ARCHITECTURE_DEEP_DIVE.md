# Butler Memory Architecture - Deep Dive

> **Complete breakdown of Butler's memory system across all layers, services, and execution paths**
> 
> **Generated:** 2026-04-27
> **Scope:** Every memory-related component, interface, and data flow

---

## Executive Summary

Butler's memory is **not just a vector database**. It is a multi-tier, evolving memory engine with:

- **5 Storage Tiers**: HOT (Redis), WARM (Qdrant), COLD (TurboQuant/FAISS), GRAPH (Neo4j), STRUCT (PostgreSQL)
- **3 Memory Types**: Episodic (sessions), Semantic (facts), Profile (preferences/dislikes)
- **4 Retrieval Signals**: Semantic similarity, graph traversal, keyword matching, personalization
- **3 Evolution Actions**: Create, Reinforce, Merge, Supersede, Contradict
- **2 Context Layers**: Session-local (hot) and User-wide (warm/cold/struct)

Memory flows through **4 architectural layers**:
1. **Domain Layer** - Contracts, models, policies
2. **Service Layer** - Business logic, orchestration
3. **Infrastructure Layer** - Storage backends
4. **Integration Layer** - Hermes, CrewAI, Orchestrator

---

## 1. Domain Layer (backend/domain/memory/)

### 1.1 Contracts (contracts.py)

**Purpose:** Define all memory interfaces for dependency injection and testability.

#### Core Contracts:

```python
# Main service contract
class MemoryServiceContract(DomainService):
    async def store(account_id, memory_type, content, **kwargs) -> MemoryEntry
    async def recall(account_id, query, memory_types=None, limit=10) -> list[MemoryEntry]
    async def store_turn(account_id, session_id, role, content, **kwargs) -> ConversationTurn
    async def get_session_history(account_id, session_id, limit=50) -> list[ConversationTurn]
    async def build_context(account_id, query, session_id) -> ContextPack
    async def update_entity(account_id, entity_name, facts: dict) -> MemoryEntry
    async def set_preference(account_id, key, value, confidence) -> MemoryEntry
```

#### Infrastructure Contracts (keep domain clean):

```python
# Write abstraction - ButlerMemoryStore implements this
class IMemoryWriteStore(DomainService):
    async def write(request: MemoryWriteRequest, tenant_id: str) -> Any
    async def archive(account_id: str, entry_id: Any) -> None

# Cold store abstraction - TurboQuant/FAISS implement this
class IColdStore(DomainService):
    async def recall(account_id: str, query: str, top_k: int = 5) -> list[Any]
    def index(entry_id: str, embedding: list[float], payload: dict) -> None

# Retrieval abstraction - RetrievalFusionEngine implements this
class IRetrievalEngine(DomainService):
    async def search(account_id, query, memory_types=None, limit=20) -> list[Any]

# Narrow recorder slice - EpisodicMemoryEngine uses this
class IMemoryRecorder(DomainService):
    async def store(account_id, memory_type, content, **kwargs) -> MemoryEntry
    async def get_session_history(account_id, session_id, limit=50) -> list[ConversationTurn]
```

#### Context Pack:

```python
class ContextPack(BaseModel):
    session_history: list              # Recent conversation turns
    relevant_memories: list             # Retrieved memory entries
    preferences: list                  # User preferences
    entities: list                     # Resolved entities
    summary_anchor: str | None         # Session summary
    context_token_budget: int          # Token budget used
```

### 1.2 Models (models.py)

**Purpose:** SQLAlchemy ORM models for all memory tables.

#### Canonical Memory Entry:

```python
class MemoryEntry(Base):
    id: UUID (PK)
    tenant_id: UUID (indexed)           # Multi-tenant isolation
    account_id: UUID (indexed)
    memory_type: str (indexed)          # session_message, preference, entity, etc.
    content: JSONB                      # Flexible content storage
    embedding: Vector(1536) | None      # pgvector for semantic search
    importance: float (default 0.5)
    confidence: float (default 1.0)
    source: str (default "conversation")
    session_id: str | None (indexed)
    tags: JSONB (default [])
    status: MemoryStatus (default ACTIVE)  # ACTIVE, DEPRECATED, CONFLICTED
    metadata_col: JSONB | None
    valid_from: datetime (indexed)
    valid_until: datetime | None
    superseded_by: UUID | None (FK to memory_entries.id)
    created_at: datetime (indexed)
    last_accessed_at: datetime
    access_count: int (default 0)
```

#### Conversation Turn:

```python
class ConversationTurn(Base):
    id: UUID (PK)
    tenant_id: UUID (indexed)
    account_id: UUID (indexed)
    session_id: str (indexed)
    role: str (indexed)                 # user, assistant, system, tool
    content: Text
    turn_index: int
    intent: str | None (indexed)
    tool_calls: JSONB | None
    metadata_col: JSONB | None
    created_at: datetime (indexed)
```

#### Knowledge Graph Models:

```python
class KnowledgeEntity(Base):
    id: UUID (PK)
    tenant_id: UUID (indexed)
    account_id: UUID (indexed)
    entity_type: str (indexed)          # PERSON, ORG, PLACE, etc.
    name: str
    summary: Text | None
    name_embedding: Vector(1536) | None
    metadata_col: JSONB
    status: MemoryStatus
    valid_until: datetime | None
    superseded_by: UUID | None

class KnowledgeEdge(Base):
    id: UUID (PK)
    tenant_id: UUID (indexed)
    account_id: UUID (indexed)
    source_id: UUID (FK to knowledge_entities.id)
    target_id: UUID (FK to knowledge_entities.id)
    relation_type: str (indexed)
    metadata_col: JSONB
    created_at: datetime

class MemoryEntityLink(Base):
    memory_id: UUID (FK to memory_entries.id, PK)
    entity_id: UUID (FK to knowledge_entities.id, PK)
```

#### User Profile Models:

```python
class ExplicitPreference(Base):
    id: UUID (PK)
    tenant_id: UUID (indexed)
    account_id: UUID (indexed)
    category: str (indexed)
    key: str (unique with tenant_id, account_id)
    value: JSONB
    confidence: float
    created_at: datetime
    updated_at: datetime

class ExplicitDislike(Base):
    id: UUID (PK)
    tenant_id: UUID (indexed)
    account_id: UUID (indexed)
    key: str (unique with tenant_id, account_id)
    reason: JSONB | None
    confidence: float
    created_at: datetime
    updated_at: datetime

class UserConstraint(Base):
    id: UUID (PK)
    tenant_id: UUID (indexed)
    account_id: UUID (indexed)
    constraint_type: str (indexed)
    value: JSONB
    active: bool (default True, indexed)
    created_at: datetime
    updated_at: datetime
```

#### Episodic Memory:

```python
class Episode(Base):
    id: UUID (PK)
    tenant_id: UUID (indexed)
    account_id: UUID (indexed)
    session_id: str | None (indexed)
    goal: Text | None
    outcome: str                         # completed, failed, abandoned
    events: JSONB (default [])
    lessons: JSONB (default [])
    created_at: datetime (indexed)

class Routine(Base):
    id: UUID (PK)
    tenant_id: UUID (indexed)
    account_id: UUID (indexed)
    name: str (indexed)
    occurrences: int (default 1)
    metadata_col: JSONB
    created_at: datetime
    last_observed_at: datetime
```

#### Knowledge Chunks:

```python
class KnowledgeChunk(Base):
    id: UUID (PK)
    tenant_id: UUID (indexed)
    account_id: UUID (indexed)
    text: Text
    index: int (default 0)
    source_type: str (indexed)          # document, email, meeting, etc.
    source_id: UUID (indexed)
    embedding: Vector(1536) | None
    created_at: datetime (indexed)

class ChunkEntityLink(Base):
    chunk_id: UUID (FK to knowledge_chunks.id, PK)
    entity_id: UUID (FK to knowledge_entities.id, PK)
```

### 1.3 Write Policy (write_policy.py)

**Purpose:** Canonical routing policy for memory writes across storage tiers.

#### Storage Tiers:

```python
class StorageTier(StrEnum):
    HOT = "hot"        # Redis - rolling session context (24h TTL)
    WARM = "warm"      # Qdrant - active semantic retrieval
    COLD = "cold"      # TurboQuant/FAISS - archival long-tail
    GRAPH = "graph"    # Neo4j - entity relationships
    STRUCT = "struct"  # PostgreSQL - canonical source of truth
```

#### Write Request:

```python
@dataclass
class MemoryWriteRequest:
    memory_type: str                      # session_message, preference, entity, etc.
    content: Any
    importance: float = 0.5
    age_days: float = 0.0
    account_id: str = ""
    session_id: str | None = None
    provenance: str = "conversation"      # conversation, tool, crawl, import, system
    has_pii: bool = False
    is_scrubbed: bool = False
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
```

#### Routing Rules:

**session_message:**
- Default: HOT only (ephemeral session context)
- If durable (tool_call, contains_decision, importance >= 0.8): HOT + STRUCT
- Hermes sidecar copy: always for replay/search

**preference/dislike:**
- STRUCT + WARM + GRAPH
- Canonical structured record + semantic search + graph traversal

**relationship:**
- GRAPH + STRUCT + (WARM if importance >= 0.6)
- Graph-first with canonical audit record

**entity:**
- STRUCT + WARM + GRAPH
- Durable structured + semantic + graph

**episode:**
- If age_days > 30: STRUCT + COLD (archive)
- If importance >= 0.85: STRUCT + WARM + (GRAPH if graph-worthy)
- Default: STRUCT + WARM

**tool_trace:**
- If age_days > 7 and not audit-sensitive: STRUCT + COLD
- Default: STRUCT (audit-sensitive always STRUCT)

**chunk (document/email/meeting/research):**
- web_crawl_chunk: if age_days > 14 or importance < 0.35 → COLD only
- If age_days > 60: STRUCT + COLD
- Default: STRUCT + WARM

**summary_anchor:**
- STRUCT + (HOT if session_id) + WARM
- Durable + session-local + semantic

**workflow_state:**
- STRUCT + (HOT if session_id)
- Canonical operational state + hot availability

**audit_event:**
- STRUCT only
- Canonical and immutable

#### PII Enforcement:

- PII-sensitive data NEVER routed to COLD (right-to-erasure concerns)
- If ConsentManager requires scrubbing and data is unscrubbed: block WARM/STRUCT/GRAPH writes
- PII detection: explicit has_pii flag OR metadata.sensitivity in {"pii", "high", "sensitive"}

### 1.4 Evolution (evolution.py)

**Purpose:** Define memory evolution actions for fact reconciliation.

```python
class MemoryAction(StrEnum):
    CREATE = "create"           # New fact, no conflicts
    REINFORCE = "reinforce"     # Confirms existing, boost confidence
    MERGE = "merge"             # Adds complementary detail
    SUPERSEDE = "supersede"     # Newer version replaces old
    CONTRADICT = "contradict"   # Conflict detected, needs review
    OBSOLETE = "obsolete"       # Fact is no longer true
    REQUIRES_REVIEW = "requires_review"  # Human review needed

@dataclass
class ReconciledFact:
    action: MemoryAction
    target_memory_id: UUID | None
    reason: str
    confidence_delta: float = 0.0
```

### 1.5 Policy (policy.py)

**Purpose:** Memory access and retention policies.

### 1.6 Scopes (scopes.py)

**Purpose:** Memory visibility and isolation scopes.

### 1.7 Session Store (session_store.py)

**Purpose:** Session-local memory management.

---

## 2. Service Layer (backend/services/memory/)

### 2.1 MemoryService (service.py)

**Purpose:** Main integration layer for all memory operations.

#### Dependencies:

```python
class MemoryService(MemoryServiceContract):
    def __init__(
        self,
        db: AsyncSession,                      # PostgreSQL
        redis: Redis,                           # Redis
        embedder: EmbeddingContract,            # ML embeddings
        retrieval: RetrievalFusionEngine,       # Hybrid search
        evolution: MemoryEvolutionEngine,       # Fact reconciliation
        resolution: EntityResolutionEngine,     # Entity linking
        understanding: UnderstandingService,   # User preferences
        context_builder: ContextBuilder,       # Token-budgeted context
        knowledge_repo: KnowledgeRepoContract, # Graph storage
        extraction: KnowledgeExtractionEngine, # Graph extraction
        store: IMemoryWriteStore,              # Multi-tier writes
        summarizer: AnchoredSummarizer,        # Session compression
        episodic: IMemoryRecorder | None,      # Episode capture
        consent_manager: ConsentManager | None, # Privacy
        memory_policy: MemoryPolicy | None,    # Access rules
        operation_router: OperationRouter | None, # Admission control
    )
```

#### Core Methods:

**store()** - Reconciliation-aware write routing:
```python
async def store(account_id, memory_type, content, tenant_id=None, **kwargs):
    # 1. Check operation router admission
    # 2. Extract metadata
    # 3. Call evolution.reconcile() to decide action
    # 4. Build MemoryWriteRequest with reconciliation metadata
    # 5. Call store.write() through policy router
    # 6. Return MemoryEntry from STRUCT tier
```

**recall()** - Hybrid retrieval:
```python
async def recall(account_id, query, memory_types=None, limit=10, tenant_id=None):
    # Call retrieval.search() with tenant-scoped filtering
    # Return list of MemoryEntry objects
```

**build_context()** - Orchestrator-facing context assembly:
```python
async def build_context(account_id, query, session_id, tenant_id=None):
    # 1. Call retrieval.search() for relevant memories
    # 2. Call get_session_history() for recent turns
    # 3. Get session payload for summary_anchor
    # 4. Fetch ExplicitPreference records
    # 5. Fetch UserConstraint records
    # 6. Call resolution.resolve() for entity
    # 7. Call context_builder.assemble() with all components
    # 8. Return ContextPack
```

**store_turn()** - Persist conversation turn:
```python
async def store_turn(account_id, session_id, role, content, tenant_id=None, **kwargs):
    # 1. Create ConversationTurn ORM object
    # 2. Add to database
    # 3. If role == "user": call understanding.analyze_turn()
    # 4. Commit
```

**compress_session()** - Generate anchored session summary:
```python
async def compress_session(account_id, session_id):
    # 1. Fetch session history
    # 2. Get existing summary from Redis
    # 3. If exists: call summarizer.merge_summary()
    # 4. If not: call summarizer.generate_initial_summary()
    # 5. Store in Redis session payload
```

**update_entity()** - Update entity in graph + canonical memory:
```python
async def update_entity(account_id, entity_name, facts):
    # 1. Call knowledge_repo.upsert_entity()
    # 2. Call store() with memory_type="entity"
```

**add_relationship()** - Create graph relationship:
```python
async def add_relationship(account_id, source_name, target_name, relation):
    # 1. Resolve source entity
    # 2. Resolve target entity
    # 3. Call knowledge_repo.upsert_edge()
```

**end_session()** - Capture episode and extract to graph:
```python
async def end_session(account_id, session_id, tenant_id=None):
    # 1. Call episodic.capture_episode()
    # 2. Fetch session history
    # 3. Check consent for graph commit
    # 4. Scrub if consent manager present
    # 5. Call extraction.extract_and_store() for graph
```

**forget()** - Right-to-erasure:
```python
async def forget(account_id, memory_id=None, content_filter=None, tenant_id=None):
    # Delete specific memory by ID with tenant check
    # OR delete by content filter with tenant scope
```

### 2.2 ButlerMemoryStore (memory_store.py)

**Purpose:** Multi-tier write dispatcher implementing IMemoryWriteStore.

#### Architecture:

```python
class ButlerMemoryStore(IMemoryWriteStore):
    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        embedder: EmbeddingContract,
        cold_store: IColdStore,           # TurboQuant or FAISS
        graph_repo: KnowledgeRepoContract | None,
        policy: MemoryWritePolicy,
        consent_manager: ConsentManager | None,
    )
```

#### Write Flow:

```python
async def write(request: MemoryWriteRequest, tenant_id: str) -> MemoryWriteResult:
    # 1. Get route from policy.route(request)
    # 2. For each tier in route.tiers:
    #    a. Check PII rules (enforce_pii_rules)
    #    b. Check consent for GRAPH tier
    #    c. Call _write_tier(tier, request, route, tenant_id)
    # 3. Write Hermes session sidecar if policy says so
    # 4. Return MemoryWriteResult with all tier IDs
```

#### Tier Writers:

**_write_hot()** - Redis rolling window:
```python
# Key: {tenant_namespace}:memory:hot:{session_id}
# TTL: 86400 seconds (24 hours)
# Max entries: 50 (ltrim)
# Record: schema_version, entry_id, memory_type, content, importance, source, sensitivity, redacted, ts
```

**_write_warm()** - Qdrant semantic tier:
```python
# Collection: butler_memories
# Vector: from embedder.embed(content)
# Payload: tenant_id, account_id, memory_type, session_id, importance, content, ts, metadata
```

**_write_cold()** - TurboQuant/FAISS archival:
```python
# Thread-hop to sync cold_store.index()
# Payload: tenant_id, account_id, memory_type, session_id, importance, content, metadata, ts
```

**_write_struct()** - PostgreSQL canonical:
```python
# Create MemoryEntry ORM object
# If metadata.supersedes: archive old record first
# If VECTOR_STORE_BACKEND == "postgres": store embedding
# Add to session, flush, return entry.id
```

**_write_graph()** - Neo4j entities/relationships:
```python
# If content has source_name + target_name + relation:
#   - Upsert source entity
#   - Upsert target entity
#   - Upsert edge between them
# If content has name:
#   - Upsert entity
# Return entity ID or edge ID string
```

#### PII Scrubbing:

```python
# Before any tier writes:
# - If consent_manager present and has_pii:
#   - Scrub text content
#   - Scrub dict content recursively
#   - Set request.is_scrubbed = True
# - Log scrubbing events
```

### 2.3 RetrievalFusionEngine (retrieval.py)

**Purpose:** Oracle-Grade hybrid retrieval with multi-signal fusion.

#### Architecture:

```python
class RetrievalFusionEngine:
    def __init__(
        self,
        db: AsyncSession,
        embedder: EmbeddingContract,
        knowledge_repo: KnowledgeRepoContract,
        personalization: PersonalizationEngine | None,  # The Blender
    )
```

#### Search Flow:

```python
async def search(account_id, query, memory_types=None, limit=20, tenant_id=None):
    # 1. Parse account_id and tenant_id as UUIDs (safe fallback on error)
    # 2. Call _get_candidates() for broad retrieval
    # 3. Apply temporal decay and access boosting
    # 4. Sort by boosted scores
    # 5. If personalization available:
    #    - Run 5-stage Blender pipeline
    #    - Map back to ScoredMemory
    # 6. Fallback: semantic reranking without personalization
    #    - Compute cosine similarity
    #    - Combine boosted score (60%) + semantic (40%)
    # 7. Return top-k ScoredMemory objects
```

#### Candidate Retrieval:

```python
async def _get_candidates(account_id, query, limit):
    # Primary scan: PostgreSQL with flexible account_id matching + tenant_id filter
    # WHERE (account_id = uuid OR account_id = string) AND tenant_id = tenant AND status = ACTIVE
    
    # 2-hop graph expansion:
    # a. Find seed entities whose names overlap with query tokens
    # b. 1-hop KnowledgeEdge traversal (source ↔ target)
    # c. Resolve memory IDs via MemoryEntityLink join
    # d. Fetch linked MemoryEntry rows
    
    # Return candidates + graph_memories
```

#### Temporal Decay:

```python
# For each candidate:
# days_old = (now - created_at).days
# decay_factor = 0.98 ^ min(days_old, 60)  # Cap at 60 days
# base_score *= decay_factor

# Access count boosting:
# access_boost = min(access_count * 0.05, 0.3)  # Cap at 0.3
# base_score += access_boost

# Importance weighting:
# importance_boost = importance * 0.2
# base_score += importance_boost
```

#### Personalization Integration (The Blender):

```python
# If personalization engine available:
# 1. Get query embedding
# 2. Map candidates to MLPCandidate format
# 3. Call personalization.rank(query_vector, context, candidates)
# 4. Map back to ScoredMemory with features
# 5. Return ranked results
```

#### Fallback Semantic Reranking:

```python
# Compute cosine similarity:
# similarity = dot(mem_vec, query_vec) / (norm(mem_vec) * norm(query_vec))

# Final score:
# final_score = 0.6 * boosted_score + 0.4 * semantic_similarity

# Signals for debugging:
# {
#   "temporal_decay": boosted_score,
#   "semantic_similarity": semantic_score,
#   "access_count": mem.access_count,
#   "importance": mem.importance,
# }
```

### 2.4 ContextBuilder (context_builder.py)

**Purpose:** Token-budgeted context assembly for LLM prompting.

#### Architecture:

```python
class ContextBuilder:
    def __init__(
        self,
        token_budget: int = 4096,
        history_budget_ratio: float = 0.35,     # 35% for history
        memory_budget_ratio: float = 0.40,      # 40% for memories
        profile_budget_ratio: float = 0.15,     # 15% for profile
        entity_budget_ratio: float = 0.10,      # 10% for entities
        char_to_token_ratio: int = 4,
        tokenizer_encoding_name: str = "o200k_base",
    )
```

#### Dynamic Budget Allocation:

```python
def _compute_dynamic_section_budgets(query_type: str):
    # factual: 50% memories, 25% history
    # conversational: 50% history, 30% memories
    # creative: 55% history, 25% memories
    # general: default ratios
```

#### Assembly Flow:

```python
def assemble(history, memories, preferences, entities, constraints, 
             summary_anchor, dislikes, query_type="general"):
    # 1. Compute dynamic section budgets based on query_type
    # 2. Normalize summary_anchor
    # 3. Prepare constraints
    # 4. Prepare preferences
    # 5. Prepare dislikes
    # 6. Prepare entities
    # 7. Select memories with score thresholds and diversity
    # 8. Select history with intent-aware filtering
    # 9. Return ContextPack
```

#### Memory Selection (Enhanced):

```python
def _select_memories_enhanced(memories, token_budget, query_type):
    # Score threshold based on query_type:
    # - factual: 0.3 (lower threshold)
    # - conversational: 0.5 (higher threshold)
    # - general: 0.4 (default)
    
    # Filter by score threshold
    # Sort by score, then importance
    # Fit within token budget
    # Return selected memories
```

#### History Selection (Enhanced):

```python
def _select_history_enhanced(history, token_budget, query_type):
    # For factual queries:
    #   - Separate tool turns from regular turns
    #   - Select tool turns first, then regular
    # For other queries:
    #   - Most recent turns
    # Fit within token budget
    # Return selected history
```

#### Prompt Formatting:

```python
def format_as_prompt(pack: ContextPack) -> str:
    # Sections in order:
    # 1. PAST CONVERSATION SUMMARY (ANCHOR)
    # 2. USER CONSTRAINTS
    # 3. USER PREFERENCES
    # 4. USER DISLIKES
    # 5. RESOLVED ENTITIES
    # 6. RELEVANT MEMORIES
    # 7. RECENT SESSION HISTORY
    
    # Each section: TITLE:\n- item1\n- item2\n...
```

### 2.5 MemoryEvolutionEngine (evolution_engine.py)

**Purpose:** Fact reconciliation and memory evolution.

#### Architecture:

```python
class MemoryEvolutionEngine:
    def __init__(
        self,
        db: AsyncSession,
        retrieval: IRetrievalEngine,
        ml_runtime: IReasoningRuntime,
        consent_manager: ConsentManager | None,
    )
```

#### Reconciliation Flow:

```python
async def reconcile(account_id, new_fact, context=None):
    # 1. Scrub fact if consent manager present
    # 2. Fetch similar existing memories via retrieval.search()
    # 3. If no similar: return CREATE
    # 4. Apply temporal decay to existing memory scores
    # 5. Sort by decayed scores
    # 6. Build reconciliation prompt with improved engineering
    # 7. Call ML runtime for decision
    # 8. Parse JSON response
    # 9. Validate action and confidence_delta
    # 10. Return ReconciledFact
    
    # Fallback: rule-based reconciliation if ML fails
```

#### System Prompt:

```
You are Butler's Memory Evolution Engine. Your task is to reconcile new facts with existing memories.

PRINCIPLES:
1. Prefer precision: Only merge if the new fact adds specific, non-redundant detail
2. Respect temporality: Newer facts are more likely to be accurate
3. Avoid contradictions: Flag conflicts for human review when uncertain
4. Maintain confidence: Only reduce confidence if there's clear evidence against a fact

ACTION CATEGORIES:
- REINFORCE: New fact confirms existing memory without changes. Increase confidence slightly.
- MERGE: New fact adds complementary detail to existing memory. Combine both.
- SUPERSEDE: New fact is a newer/updated version that replaces old information.
- CONTRADICT: New fact conflicts with existing memory. Flag for resolution.
- CREATE: New fact is unrelated to existing memories. Create new entry.
```

#### Fallback Reconciliation:

```python
def _fallback_reconciliation(new_fact, similar_memories):
    # If no similar: CREATE
    # If top_match.score > 0.9: REINFORCE
    # If top_match.score > 0.7: MERGE
    # Otherwise: CREATE
```

### 2.6 UnderstandingService (understanding_service.py)

**Purpose:** Extract user preferences, dislikes, and constraints from conversation.

#### Architecture:

```python
class UnderstandingService:
    def __init__(
        self,
        db: AsyncSession,
        ml_runtime: IReasoningRuntime,
        knowledge_repo: KnowledgeRepoContract | None,
    )
```

#### Analysis Flow:

```python
async def analyze_turn(account_id, role, content, tenant_id=None):
    # Only process user turns
    # Build extraction prompt
    # Call ML runtime (cloud_fast_general profile)
    # Parse JSON response
    # For each preference: _upsert_preference()
    # For each dislike: _upsert_dislike()
    # For each constraint: _upsert_constraint()
    # Commit
```

#### Extraction Prompt:

```
Analyze the USER MESSAGE for Explicit Preferences, Dislikes, or Constraints.

MESSAGE: "{content}"

Response format (JSON):
{
  "preferences": [
    {"category": "food", "key": "coffee", "value": "black", "confidence": 0.9}
  ],
  "dislikes": [
    {"key": "mushrooms", "reason": "texture", "confidence": 0.8}
  ],
  "constraints": [
    {"type": "communication", "value": "no emojis", "active": true}
  ]
}
Only return items if they are EXPLICIT or strongly implied.
```

#### Preference Upsert:

```python
async def _upsert_preference(account_id, tenant_id, data):
    # Check if exists (tenant_id filtering)
    # If exists: update value and confidence
    # If not: create new ExplicitPreference
    # Sync to Neo4j Graph if knowledge_repo present
```

### 2.7 EpisodicMemoryEngine (episodic_engine.py)

**Purpose:** Condense sessions into goal-oriented episode summaries.

#### Architecture:

```python
class EpisodicMemoryEngine:
    def __init__(
        self,
        db: AsyncSession,
        ml_runtime: IReasoningRuntime,
        memory_recorder: IMemoryRecorder,
        consent_manager: ConsentManager | None,
    )
```

#### Episode Capture:

```python
async def capture_episode(account_id, session_id, tenant_id=None):
    # 1. Fetch full session history via memory_recorder.get_session_history()
    # 2. Build conversation text
    # 3. Scrub with consent manager if present
    # 4. Build summarization prompt
    # 5. Call ML runtime (cloud_fast_general profile)
    # 6. Parse JSON response
    # 7. Create Episode ORM object
    # 8. Add to database and commit
    # 9. Return Episode
```

#### Summarization Prompt:

```
Summarize the following conversation session into a goal-oriented Episode.

CONVERSATION:
{history_text}

Response format (JSON):
{
  "goal": "What was the user trying to achieve?",
  "outcome": "completed | failed | abandoned",
  "major_events": ["list", "of", "key", "actions/turns"],
  "lessons": ["What did we learn about the user or their environment?"]
}
```

### 2.8 Digital Twin (digital_twin.py)

**Purpose:** Complete digital twin profile with temporal reasoning and entity resolution.

#### Architecture:

```python
class DigitalTwinProfile(BaseModel):
    user_id: UUID
    created_at: datetime
    last_updated: datetime
    consent_tier: ConsentTier              # NEVER_TRAIN, PRIVATE_EVAL_ONLY, OPT_IN
    retention_days: int | None
    
    # Memory layers
    episodic: EpisodicLayer                # Episodes
    semantic: SemanticLayer                # Facts
    preferences: PreferenceLayer          # Likes/dislikes
    graph: GraphLayer                      # Entity relationships
    files: FileLayer                      # Document memory
    training: TrainingLayer                # Opt-in anonymized samples
```

#### TwinBuilder:

```python
class TwinBuilder:
    def __init__(self, user_id: UUID)
    def add_interaction(interaction)      # Add to episodic layer
    def add_fact(fact)                     # Add/update semantic fact
    def add_preference(preference)         # Add/update preference
    def add_entity(entity)                 # Add to graph layer
    def add_relationship(edge)            # Add relationship
    def add_file(file)                     # Add file memory
    def build() -> DigitalTwinProfile      # Return complete profile
```

#### TwinQueryEngine:

```python
class TwinQueryEngine:
    def get_recent_episodes(limit=10, hours=None)
    def get_preference(domain, key, default=None)
    def find_entities(name_query)
    def get_relationships(entity_id)
    def get_context_window(max_tokens=4096)
```

#### EntityResolver:

```python
class EntityResolver:
    def resolve(name, entity_type) -> EntityNode
    def add_alias(entity_id, alias)
```

#### TemporalReasoner:

```python
class TemporalReasoner:
    def get_fact_at_time(entity_id, attribute, at_time) -> MemoryFact | None
    def get_preference_trend(domain, key, days=30) -> list[float]
```

#### TrainingDataTransformer:

```python
class TrainingDataTransformer:
    @staticmethod
    def create_sample(profile, input_context, output_response) -> TrainingSample | None
    @staticmethod
    def can_use_for_training(profile) -> bool
    @staticmethod
    def can_use_for_evaluation(profile) -> bool
```

### 2.9 Other Service Components

#### KnowledgeExtractionEngine (graph_extraction.py)
- Extract entities and relationships from text
- Build knowledge graph from episodes

#### EntityResolutionEngine (resolution_engine.py)
- Resolve entity names to canonical entities
- Handle aliases and deduplication

#### AnchoredSummarizer (anchored_summarizer.py)
- Merge session summaries incrementally
- Generate initial summary from full history

#### ConsentManager (consent_manager.py)
- Enforce privacy policies
- Scrub PII from text
- Check consent for graph commits

#### TurboQuant Store (turboquant_store.py)
- TurboQuantColdStore implementation
- get_cold_store() factory (TurboQuant or FAISS fallback)

#### FAISS Cold Store (faiss_cold_store.py)
- FAISS-based cold tier vector store
- IndexFlatIP with L2 normalization
- IVF rebuild recommendation at 50k entries

#### Qdrant Vector Store (qdrant_vector_store.py)
- Qdrant warm tier implementation
- Semantic search with filtering

#### Knowledge Repositories:
- postgres_knowledge_repo.py - PostgreSQL graph storage
- neo4j_knowledge_repo.py - Neo4j graph storage
- knowledge_repo_contract.py - Abstraction

#### Twin Components:
- twin_events.py - Event types for digital twin
- twin_event_store.py - Event persistence
- twin_snapshot_models.py - Snapshot schemas
- twin_snapshot_repo.py - Snapshot storage
- twin_profile_service.py - Profile management
- twin_projection.py - Projection logic
- twin_repository_contracts.py - Repository abstractions
- twin_types.py - Type definitions

---

## 3. Orchestrator Layer Integration

### 3.1 Execution Orchestrator (execution_orchestrator.py)

**Purpose:** Routes requests to execution lanes based on intent classification.

#### Memory Usage:

```python
class ExecutionOrchestrator:
    async def _execute_crew_multi_agent(envelope, intent_result):
        # CrewAI builder integration with MemoryService
        # Lazy load MemoryService from core.deps.get_memory_service()
        # Pass memory_service to CrewAIBuilder
        # Build crew with domain requirements
        # Execute with account_id and session_id context
```

### 3.2 Intake Processor (intake.py)

**Purpose:** Receive envelope, classify intent, enrich context.

#### Memory Usage:

```python
class IntakeProcessor:
    async def process(envelope: ButlerEnvelope) -> IntakeResult:
        # Classify intent (requires_memory flag)
        # Build environment block
        # Select execution mode
        # Return IntakeResult with requires_memory flag
```

### 3.3 Memory Writeback Node (nodes/memory_writeback.py)

**Purpose:** Graph memory writeback phase for observability.

```python
async def memory_writeback_node(state: ButlerGraphState) -> ButlerGraphState:
    # Record memory writeback phase
    # Merge state with memory_writes
```

---

## 4. Agent/Runtime Layer Integration

### 4.1 Butler Unified Agent Loop (butler_runtime/agent/loop.py)

**Purpose:** Fuses Hermes agent-loop patterns with Butler's memory.

#### Architecture:

```python
class ButlerUnifiedAgentLoop:
    def __init__(
        self,
        model_router: ButlerModelRouter,
        tool_executor: ButlerToolExecutor,
        memory_context_builder: ButlerMemoryContextBuilder,
        event_sink: ButlerEventSink | None,
        budget: ExecutionBudget | None,
    )
```

#### Memory Context Builder:

```python
class ButlerMemoryContextBuilder:
    async def build_context(account_id, query, session_id=None):
        # Stub: integrates with MemoryService
        # Returns memory context string
```

#### Execution Context:

```python
class ButlerExecutionContext:
    account_id: str
    session_id: str
    user_message: str
    model: str
    conversation_history: list[dict] | None
    system_message: str | None
    memory_context: str | None              # From MemoryService
    account_tier: str
    channel: str
    assurance_level: str
```

#### Agent Loop:

```python
async def run(ctx: ButlerExecutionContext):
    # Build messages with memory context
    if ctx.memory_context:
        messages = message_builder.build_with_memory(...)
    
    # Main loop:
    # - Get visible tool schemas
    # - Call model router
    # - Execute tool calls
    # - Append tool results
    # - Repeat until no tool calls or budget exhausted
```

### 4.2 Hermes Memory Integration (integrations/hermes/agent/)

#### MemoryManager (memory_manager.py)

**Purpose:** Orchestrates built-in provider + one external plugin.

```python
class MemoryManager:
    def __init__(self):
        self._providers: List[MemoryProvider] = []
        self._has_external: bool = False  # Only one external allowed
    
    def add_provider(provider: MemoryProvider):
        # Built-in always accepted
        # Only one external allowed (reject with warning)
        # Index tool names → provider
    
    def prefetch_all(query, session_id="") -> str:
        # Collect prefetch from all providers
        # Return merged context
    
    def sync_all(user_content, assistant_content, session_id=""):
        # Sync to all providers
```

#### MemoryProvider (memory_provider.py)

**Purpose:** Abstract base for pluggable memory providers.

```python
class MemoryProvider(ABC):
    @abstractmethod
    def name(self) -> str
    
    @abstractmethod
    def is_available(self) -> bool
    
    @abstractmethod
    def initialize(session_id, **kwargs)
    
    def system_prompt_block() -> str
    
    @abstractmethod
    def prefetch(query, session_id="") -> str
    
    def queue_prefetch(query, session_id="") -> None
    
    def sync_turn(user_content, assistant_content, session_id="") -> None
    
    @abstractmethod
    def get_tool_schemas() -> List[Dict]
    
    @abstractmethod
    def handle_tool_call(tool_name, args, **kwargs) -> str
    
    def shutdown()
    
    # Optional hooks:
    def on_turn_start(turn, message, **kwargs)
    def on_session_end(messages)
    def on_pre_compress(messages) -> str
    def on_memory_write(action, target, content)
    def on_delegation(task, result, **kwargs)
```

---

## 5. Dependency Injection (core/deps.py)

**Purpose:** Application-lifetime dependency registry for FastAPI routes.

#### Memory-Related Dependencies:

```python
class DependencyRegistry:
    # Process-wide shared dependencies:
    # - LockManager
    # - StateSyncer
    # - HealthAgent
    # - CircuitBreakerRegistry
    # - Metrics
    
    # Request-scoped (never cached):
    # - AsyncSession (PostgreSQL)
    # - Redis (connection pool)
    
    # Memory service factory:
    # - get_memory_service() - creates MemoryService with all dependencies
```

#### Memory Service Factory:

```python
async def get_memory_service(
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
    # ... other dependencies
) -> MemoryService:
    # Assemble MemoryService with:
    # - db (PostgreSQL)
    # - redis (Redis)
    # - embedder (EmbeddingService)
    # - retrieval (RetrievalFusionEngine)
    # - evolution (MemoryEvolutionEngine)
    # - resolution (EntityResolutionEngine)
    # - understanding (UnderstandingService)
    # - context_builder (ContextBuilder)
    # - knowledge_repo (KnowledgeRepoContract)
    # - extraction (KnowledgeExtractionEngine)
    # - store (ButlerMemoryStore)
    # - summarizer (AnchoredSummarizer)
    # - episodic (EpisodicMemoryEngine)
    # - consent_manager (ConsentManager)
    # - memory_policy (MemoryPolicy)
    # - operation_router (OperationRouter)
```

---

## 6. Complete Data Flow Diagrams

### 6.1 Write Flow

```
User Interaction
    ↓
MemoryService.store()
    ↓
MemoryEvolutionEngine.reconcile()
    ↓
Decision: CREATE | REINFORCE | MERGE | SUPERSEDE | CONTRADICT
    ↓
MemoryWriteRequest (with reconciliation metadata)
    ↓
MemoryWritePolicy.route()
    ↓
WriteRoute: [HOT, WARM, COLD, GRAPH, STRUCT] based on memory_type
    ↓
ButlerMemoryStore.write()
    ↓
For each tier:
    ├─ PII check (ConsentManager)
    ├─ Consent check (GRAPH tier)
    └─ _write_tier()
        ├─ HOT: Redis LPUSH + LTRIM + EXPIRE
        ├─ WARM: Qdrant upsert with embedding
        ├─ COLD: TurboQuant/FAISS index (thread-hop)
        ├─ GRAPH: Neo4j upsert entity/edge
        └─ STRUCT: PostgreSQL MemoryEntry
    ↓
MemoryWriteResult (tier IDs)
    ↓
Hermes sidecar write (if session_message)
    ↓
Return MemoryEntry from STRUCT tier
```

### 6.2 Retrieval Flow

```
Query Request
    ↓
MemoryService.recall() or build_context()
    ↓
RetrievalFusionEngine.search()
    ↓
_get_candidates()
    ├─ Primary scan: PostgreSQL (tenant_id + account_id filter)
    └─ 2-hop graph expansion:
        ├─ Seed entities (name overlap with query)
        ├─ KnowledgeEdge traversal (1-hop)
        ├─ MemoryEntityLink resolution
        └─ Graph memories fetch
    ↓
Temporal decay + access boosting
    ↓
Sort by boosted scores
    ↓
If PersonalizationEngine available:
    ├─ 5-stage Blender pipeline
    ├─ Query embedding
    ├─ Candidate mapping
    ├─ Rank with features
    └─ Map back to ScoredMemory
Else:
    ├─ Query embedding
    ├─ Cosine similarity computation
    └─ Final score: 60% boosted + 40% semantic
    ↓
Return top-k ScoredMemory
```

### 6.3 Context Building Flow

```
ContextBuilder.assemble()
    ↓
Dynamic budget allocation (query_type)
    ↓
Normalize components:
    ├─ summary_anchor (from Redis session payload)
    ├─ preferences (ExplicitPreference records)
    ├─ dislikes (ExplicitDislike records)
    ├─ constraints (UserConstraint records)
    ├─ entities (EntityResolutionEngine.resolve())
    ├─ memories (RetrievalFusionEngine.search())
    └─ history (get_session_history())
    ↓
Enhanced selection:
    ├─ memories: score threshold + diversity
    └─ history: intent-aware (tool turns for factual)
    ↓
Fit within token budgets
    ↓
Return ContextPack
    ↓
format_as_prompt()
    ↓
Prompt string with sections
```

### 6.4 Session End Flow

```
Session ends
    ↓
MemoryService.end_session()
    ↓
EpisodicMemoryEngine.capture_episode()
    ├─ Fetch session history
    ├─ Scrub with ConsentManager
    ├─ ML summarization
    └─ Create Episode record
    ↓
Consent check for graph commit
    ↓
KnowledgeExtractionEngine.extract_and_store()
    ├─ Extract entities
    ├─ Extract relationships
    └─ Upsert to graph repo
```

---

## 7. Storage Backend Details

### 7.1 HOT Tier (Redis)

**Purpose:** Rolling session context for immediate availability.

**Key Pattern:** `{tenant_namespace}:memory:hot:{session_id}`

**Data Structure:** Redis list with JSON records

**TTL:** 86400 seconds (24 hours)

**Max Entries:** 50 (LRU via LTRIM)

**Record Schema:**
```json
{
  "schema_version": "v1",
  "entry_id": "uuid",
  "memory_type": "session_message",
  "session_id": "session_id",
  "account_id": "account_id",
  "content": "text content",
  "importance": 0.5,
  "source": "conversation",
  "sensitivity": "unknown",
  "redacted": false,
  "ts": "2026-04-27T10:00:00Z"
}
```

**Hermes Sidecar:** `hermes:session:messages:{session_id}` (auxiliary copy)

### 7.2 WARM Tier (Qdrant)

**Purpose:** Active semantic retrieval with full-precision vectors.

**Collection:** `butler_memories`

**Vector Dimension:** 1536 (OpenAI embeddings)

**Payload Schema:**
```json
{
  "tenant_id": "uuid",
  "account_id": "uuid",
  "memory_type": "session_message",
  "session_id": "session_id",
  "importance": 0.5,
  "content": "text content",
  "ts": "2026-04-27T10:00:00Z",
  "metadata": {}
}
```

**Indexing:** Payload indexes on tenant_id, account_id, memory_type

### 7.3 COLD Tier (TurboQuant/FAISS)

**Purpose:** Archival long-tail storage for high-volume material.

**TurboQuant:** High-performance vector store with compressed recall

**FAISS Fallback:** IndexFlatIP with L2 normalization

**Factory Pattern:**
```python
def get_cold_store(dim=1536, snapshot_path=None):
    if pyturboquant installed:
        return TurboQuantColdStore(dim, snapshot_path)
    else:
        return FaissColdStore(dim, snapshot_path)
```

**IVF Rebuild:** Recommended at 50k entries for O(log n) ANN

**Payload Schema:** Same as WARM tier

### 7.4 GRAPH Tier (Neo4j)

**Purpose:** Entity relationships and provenance edges.

**Node Types:**
- User
- Person
- Identity (channel, handle)
- Preference
- Dislike
- Routine
- SessionIntent
- Episode
- MemoryFact
- Device
- Document

**Relationship Types:**
- INTERESTED_IN (User → Preference)
- DISLIKES (User → Dislike)
- CLOSE_TO (User → Person)
- USES_DEVICE (User → Device)
- CURRENTLY_FOCUSED_ON (User → SessionIntent)
- DERIVED_FROM (Episode → Document)
- SUPERCEDES (MemoryFact → MemoryFact)
- CONTRADICTS (MemoryFact → MemoryFact)
- OBSERVED_IN (MemoryFact → Episode)
- CONTACTS_VIA (Person → Identity)

**PostgreSQL Fallback:** KnowledgeEntity + KnowledgeEdge tables

### 7.5 STRUCT Tier (PostgreSQL)

**Purpose:** Canonical source of truth for all durable records.

**Tables:**
- memory_entries (canonical memory)
- conversation_turns (session history)
- knowledge_entities (graph nodes)
- knowledge_edges (graph relationships)
- memory_entity_links (memory ↔ entity)
- explicit_preferences (user preferences)
- explicit_dislikes (user dislikes)
- user_constraints (operational constraints)
- memory_episodes (session summaries)
- memory_routines (recurring patterns)
- knowledge_chunks (document chunks)
- chunk_entity_links (chunk ↔ entity)

**Indexes:**
- Composite indexes on (tenant_id, account_id, memory_type, status)
- Composite indexes on (tenant_id, account_id, session_id, created_at)
- Composite indexes on (tenant_id, account_id, created_at)
- Composite indexes on (tenant_id, account_id, valid_from)

**Vector Column:** pgvector for semantic search (when VECTOR_STORE_BACKEND == "postgres")

---

## 8. Multi-Tenant Isolation (Phase 3)

### 8.1 Tenant Namespace

**Purpose:** Isolate memory across tenants at the storage layer.

**Implementation:** `services/tenant/namespace.py`

```python
class TenantNamespace:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.prefix = f"tenant:{tenant_id}"
    
    def session(self, session_id: str) -> str:
        return f"{self.prefix}:session:{session_id}"
    
    def memory(self, key: str) -> str:
        return f"{self.prefix}:memory:{key}"
```

### 8.2 Tenant Filtering

**PostgreSQL:** All queries include `tenant_id = effective_tenant_id`

**Redis:** All keys use `TenantNamespace` prefix

**Qdrant:** Payload filtering on `tenant_id` field

**Neo4j:** Node properties include `tenant_id`

### 8.3 Right-to-Erasure

**forget() method:**
```python
async def forget(account_id, memory_id=None, content_filter=None, tenant_id=None):
    # Delete by ID with tenant check
    # OR delete by content filter with tenant scope
    # Tenant scope prevents cross-tenant data leakage
```

---

## 9. Privacy and Consent

### 9.1 Consent Tiers

```python
class ConsentTier(StrEnum):
    NEVER_TRAIN = "never_train"           # Never use for training
    PRIVATE_EVAL_ONLY = "private_eval_only"  # Private evaluation only
    OPT_IN = "opt_in"                     # Full opt-in consent
```

### 9.2 ConsentManager

**Responsibilities:**
- Check consent for graph commits
- Scrub PII from text
- Get consent policy for account
- Enforce scrub_pii policy

**Methods:**
```python
can_commit_to_graph(account_id: UUID) -> bool
scrub_text(account_id: UUID, text: str) -> str
scrub_episodic_stream(account_id: UUID, text: str) -> str
get_policy(account_id: UUID) -> dict
```

### 9.3 PII Enforcement

**Write Policy:**
- PII-sensitive data NEVER routed to COLD
- If scrub_pii required and data unscrubbed: block WARM/STRUCT/GRAPH writes

**PII Detection:**
- Explicit `has_pii` flag
- OR metadata.sensitivity in {"pii", "high", "sensitive"}
- OR metadata.contains_pii = true

---

## 10. Performance and Scaling

### 10.1 Latency Targets

| Metric | Target |
|--------|--------|
| Retrieval latency P95 | <200ms (excluding LLM) |
| Store latency P95 | <75ms for structured writes |
| Context build latency P95 | <250ms |
| Active profile refresh | <100ms cached / <300ms uncached |

### 10.2 Scaling Strategy

**PostgreSQL:**
- Partitioning by tenant_id
- Composite indexes on (tenant_id, account_id, ...)
- Connection pooling

**Qdrant:**
- Distributed collections
- Payload indexes for filtering
- Shard by tenant_id

**Redis:**
- Cluster mode for hot cache
- Tenant-scoped keys
- TTL-based expiration

**Neo4j:**
- Read scaling with replicas
- Graph indexes on entity properties
- Partition by tenant_id

**TurboQuant/FAISS:**
- Sharded indices per tenant
- IVF for ANN at scale
- Snapshot-based persistence

### 10.3 Cache Strategy

**Cache Families:**
- hot_context_cache: 5 min TTL
- preference_cache: 30 min TTL
- retrieval_result_cache: 5 min TTL
- entity_resolution_cache: 15 min TTL
- active_intent_cache: 15 min TTL

**Invalidation:**
- Versioned keys over wildcard scans
- User-profile version bumps invalidate dependent caches
- Superseded facts invalidate retrieval caches

---

## 11. Observability

### 11.1 Metrics

| Metric | Type | Description |
|--------|------|-------------|
| memory.retrieve.latency | Histogram | Retrieval latency |
| memory.store.latency | Histogram | Write latency |
| memory.fusion.score_mix | Histogram | Score distribution by signal family |
| memory.entity_resolution.conflicts | Counter | Unresolved entity conflicts |
| memory.contradictions.detected | Counter | Contradiction events |
| memory.superseded.total | Counter | Memories superseded |
| memory.profile.refresh.latency | Histogram | User-understanding refresh latency |
| memory.cache.hit_rate | Gauge | Cache performance |

### 11.2 Logged Events

```json
{
  "timestamp": "2026-04-27T10:30:00Z",
  "event": "memory.reconcile",
  "user_id": "user123",
  "memory_id": "mem_abc",
  "action": "supersede",
  "source_type": "chat",
  "confidence": 0.91,
  "derived_from": ["msg_1", "msg_2"]
}
```

### 11.3 OpenTelemetry Tracing

**Digital Twin Components:**
- TwinBuilder.add_interaction
- TwinBuilder.add_fact
- TwinBuilder.add_preference
- TwinBuilder.add_entity
- TwinBuilder.add_relationship
- TwinQueryEngine.get_recent_episodes
- TwinQueryEngine.get_preference
- TwinQueryEngine.find_entities
- TwinQueryEngine.get_relationships
- TwinQueryEngine.get_context_window
- EntityResolver.resolve
- TemporalReasoner.get_fact_at_time

---

## 12. Failure Handling

### 12.1 Failure Modes

| Failure | Behavior | Recovery |
|---------|----------|----------|
| Neo4j unavailable | Graph enrichment reduced | Vector + keyword fallback |
| Qdrant unavailable | Semantic recall reduced | Graph + keyword fallback |
| PostgreSQL unavailable | Structured writes blocked | Retry / queue / degraded read mode |
| Redis unavailable | Cache miss + higher latency | Direct stores + emergency throttling |
| ML unavailable | No fresh embeddings/rerank/extraction | Cached vectors + degraded retrieval |

### 12.2 Circuit Policy

- Per-dependency circuit breakers
- Retrieval degrades gracefully
- Write-time contradiction handling may defer reconciliation if ML unavailable

---

## 13. Service Interdependencies

### 13.1 Memory Service Dependencies

```python
MemoryService depends on:
├── db (PostgreSQL)
├── redis (Redis)
├── embedder (EmbeddingContract from ML Service)
├── retrieval (RetrievalFusionEngine)
│   ├── db
│   ├── embedder
│   ├── knowledge_repo (KnowledgeRepoContract)
│   └── personalization (PersonalizationEngine from ML Service)
├── evolution (MemoryEvolutionEngine)
│   ├── db
│   ├── retrieval (IRetrievalEngine)
│   ├── ml_runtime (IReasoningRuntime from ML Service)
│   └── consent_manager
├── resolution (EntityResolutionEngine)
├── understanding (UnderstandingService)
│   ├── db
│   ├── ml_runtime (IReasoningRuntime)
│   └── knowledge_repo
├── context_builder (ContextBuilder)
├── knowledge_repo (KnowledgeRepoContract)
├── extraction (KnowledgeExtractionEngine)
├── store (ButlerMemoryStore = IMemoryWriteStore)
│   ├── db
│   ├── redis
│   ├── embedder
│   ├── cold_store (IColdStore = TurboQuant/FAISS)
│   ├── graph_repo (KnowledgeRepoContract)
│   ├── policy (MemoryWritePolicy)
│   └── consent_manager
├── summarizer (AnchoredSummarizer)
├── episodic (EpisodicMemoryEngine = IMemoryRecorder)
│   ├── db
│   ├── ml_runtime (IReasoningRuntime)
│   ├── memory_recorder (IMemoryRecorder)
│   └── consent_manager
├── consent_manager (ConsentManager)
├── memory_policy (MemoryPolicy)
└── operation_router (OperationRouter from Orchestrator)
```

### 13.2 ML Service Dependencies on Memory

```python
ML Service provides to Memory:
├── EmbeddingContract (embeddings)
├── IReasoningRuntime (inference for evolution/understanding/episodic)
└── PersonalizationEngine (The Blender for retrieval)
```

### 13.3 Orchestrator Dependencies on Memory

```python
Orchestrator uses Memory for:
├── Context building (build_context)
├── Session history (get_session_history)
├── Memory storage (store, store_turn)
└── Episode capture (end_session)
```

### 13.4 Agent Runtime Dependencies on Memory

```python
ButlerUnifiedAgentLoop uses Memory for:
└── Memory context building (ButlerMemoryContextBuilder)
```

### 13.5 Hermes Integration

```python
Hermes MemoryManager orchestrates:
├── BuiltinMemoryProvider (Hermes local files)
└── ONE external plugin (Honcho, Mem0, Supermemory, etc.)

Butler MemoryService can be used as external plugin via adapter.
```

---

## 14. Implementation Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Vector (Qdrant) and Relational (Postgres) core stores | IMPLEMENTED |
| 2 | Hybrid Retrieval Fusion and Context Builder | IMPLEMENTED |
| 3 | Cross-Encoder Reranker integration (via ML HeavyRanker) | IMPLEMENTED |
| 4 | TurboQuant Cold Store and Long-Term Context archival | IMPLEMENTED |
| 5 | Neo4j Graph Memory and Knowledge Extraction Engine | PARTIAL |
| 6 | Multi-Tenant Isolation (Phase 3) | IMPLEMENTED |
| 7 | Digital Twin with Temporal Reasoning | IMPLEMENTED |
| 8 | FAISS Cold Store Fallback | IMPLEMENTED |
| 9 | Consent Manager and PII Enforcement | IMPLEMENTED |
| 10 | Hermes Memory Integration | PARTIAL |

---

## 15. Key Design Decisions

### 15.1 PostgreSQL as Canonical Source

**Decision:** PostgreSQL STRUCT tier is the canonical source of truth.

**Reasoning:**
- ACID guarantees for consistency
- Proven scalability patterns
- Rich querying capabilities
- Audit trail support
- Right-to-erasure compliance

### 15.2 Multi-Tier Architecture

**Decision:** 5-tier storage (HOT, WARM, COLD, GRAPH, STRUCT).

**Reasoning:**
- HOT: Ultra-low latency for session context
- WARM: Fast semantic retrieval for active data
- COLD: Cost-effective archival for long-tail
- GRAPH: Relationship traversal capabilities
- STRUCT: Canonical durable storage

### 15.3 Soft Invalidation Over Hard Delete

**Decision:** Prefer soft invalidation (supersede, valid_until) over hard delete.

**Reasoning:**
- Preserve temporal history
- Support "what was true then" queries
- Audit trail compliance
- Recovery capability

### 15.4 Retrieval-Time Resolution

**Decision:** Avoid collapsing nuance at write time; resolve at retrieval time.

**Reasoning:**
- Context-dependent relevance
- Temporal decay applied at query time
- Personalization signals integrated at retrieval
- Flexibility for ranking algorithm evolution

### 15.5 Provenance-First

**Decision:** All memory items must preserve source lineage.

**Reasoning:**
- Explainability for AI decisions
- Debugging capability
- Trust and transparency
- Regulatory compliance

### 15.6 Negative Signals as First-Class

**Decision:** Dislikes and rejections are first-class citizens.

**Reasoning:**
- User preference accuracy
- Avoid repeated bad recommendations
- Personalization improvement
- Trust preservation

---

## 16. Testing Strategy

### 16.1 Required Tests

- Graph + vector + keyword retrieval fusion
- Contradiction / supersession behavior
- Temporal recall correctness
- Entity resolution confidence thresholds
- Episodic write + retrieve flow
- Explicit dislike penalty in ranking
- Forgetting and redaction correctness
- Provenance preservation across updates
- Multi-tenant isolation correctness
- PII enforcement and scrubbing

### 16.2 Benchmark Expectations

- Benchmark retrieval with and without graph enrichment
- Benchmark cache hit vs cache miss paths
- Benchmark active-profile and short-term intent refresh
- Benchmark degraded-mode retrieval with one dependency unavailable
- Benchmark multi-tier write latency per tier

---

## 17. Security Considerations

### 17.1 Access Control

- Users can access only their own memory unless delegated policy exists
- Internal services access memory through explicit service identity
- Highly sensitive profile data redacted by default in debug/admin surfaces
- Tenant-scoped filtering at all storage layers

### 17.2 Encryption

- AES-256-GCM for sensitive data at rest
- Envelope encryption for key hierarchy
- Field-level encryption for high-sensitivity memory items

### 17.3 Memory Poisoning Controls

- Provenance tagging on all imported/extracted facts
- Confidence thresholds before promotion into durable profile state
- Contradiction detection before write confirmation
- Quarantine / review path for suspicious or externally injected facts

---

## 18. Future Enhancements

### 18.1 Two-Tower Candidate Retrieval

**Planned:** Dedicated two-tower retrieval models for fast pre-filtering.

**Towers:**
- User ↔ Memory Item (episodic recall)
- User ↔ Interest / Topic (profile-aware recall)
- User ↔ Person / Relationship Context (social grounding)

**Role:** Candidate generation before graph + temporal + rerank refinement.

### 18.2 Advanced Temporal Reasoning

**Planned:** Sophisticated temporal reasoning capabilities.

**Features:**
- "What was true then" queries
- Temporal pattern detection
- Trend analysis over time
- Seasonality recognition

### 18.3 Cross-Session Learning

**Planned:** Learn from patterns across multiple sessions.

**Features:**
- Cross-session routine detection
- Long-term preference evolution
- Multi-session goal tracking
- Habit pattern recognition

---

## Summary

Butler's memory system is a sophisticated, multi-tier architecture that goes far beyond simple vector search. It combines:

- **5 storage tiers** for different access patterns and cost profiles
- **Hybrid retrieval** fusing semantic, graph, keyword, and personalization signals
- **Memory evolution** with reconciliation, supersession, and contradiction handling
- **User understanding** with preference, dislike, and constraint extraction
- **Temporal reasoning** supporting both current and historical queries
- **Multi-tenant isolation** at all storage layers
- **Privacy-first design** with consent management and PII enforcement
- **Provenance tracking** for explainability and audit compliance

The system is designed for production at scale (1M users, 10K RPS, P95 <1.5s) with clear service boundaries, dependency injection for testability, and graceful degradation when dependencies fail.

---

**Document generated by:** Deep analysis of Butler memory architecture
**Analysis depth:** Complete - every layer, service, interface, and data flow
**Files analyzed:** 50+ memory-related files across domain, services, infrastructure, and integration layers
