# Notebook Graph Memory System

> **Version:** 2.0 (Oracle-Grade)
> **Updated:** 2026-04-20
> **Status:** Production Ready
> **Component:** Butler Memory Service Extension

---

## Overview

Notebook Graph Memory is Butler's hybrid memory system that combines:
- Human-style notebook workspace patterns
- LLM-native graph construction
- LangGraph orchestration workflows
- Tenant-isolated memory domains

This system provides persistent, explorable, and reasoning-capable memory that bridges raw document ingestion and structured knowledge graphs.

---

## Notebook Architecture

### Source Management

Sources are immutable raw inputs to the memory system:

```
Source → [Ingestion Pipeline] → Canonical Representation
```

**Source Properties:**
- Immutable once ingested (content hash referenced)
- Origin tracking (URL, file, tool output, conversation)
- Provenance chain preserved through all derivatives
- Tenant-scoped at ingestion time
- Versioned with full history

**Supported Source Types:**
1.  Documents (PDF, Markdown, HTML, plain text)
2.  Tool execution outputs
3.  Conversation transcripts
4.  API responses
5.  User notes and annotations
6.  Graph query results

### Note Creation

Notes are LLM-generated structured observations extracted from sources:

```
Source + Context → LLM Reasoning → Note + Entity References
```

**Note Structure:**
```typescript
interface Note {
  id: string
  source_id: string
  tenant_id: string
  content: string
  confidence: number
  entities: EntityReference[]
  relationships: RelationshipReference[]
  citations: Citation[]
  created_at: timestamp
  author: "user" | "llm" | "tool"
}
```

**Note Creation Rules:**
- One note per atomic observation
- Maximum 200 words per note
- Every claim must cite source location
- Confidence score 0.0-1.0
- Auto-linked to existing entities

### Notebook Organization

Notebooks are user-facing workspaces that aggregate notes and sources:

```
Notebook = Collection<Note> + Collection<Source> + Graph View
```

**Notebook Capabilities:**
- User-curated collections
- Auto-suggested related notes
- Timeline view of observations
- Graph visualization of contained entities
- Export to structured formats
- Shareable with permission boundaries

---

## Graph Integration

### Entity Extraction

Entities are automatically extracted from notes during creation:

```
Note Content → LLM Entity Recognizer → Normalized Entity
```

**Entity Extraction Pipeline:**
1.  Named entity recognition (NER)
2.  Entity normalization and deduplication
3.  Type classification (person, place, thing, concept)
4.  Canonical ID assignment
5.  Cross-reference with existing graph

**Entity Properties:**
```typescript
interface Entity {
  id: string
  tenant_id: string
  name: string
  type: string
  aliases: string[]
  description: string
  confidence: number
  source_count: number
  last_seen: timestamp
}
```

### Relationship Mapping

Relationships are extracted between entities using structured LLM outputs:

```
Note + Entities → LLM Relationship Extractor → Directed Edge
```

**Relationship Types:**
- `REFERS_TO` - General reference
- `PART_OF` - Composition
- `USED_FOR` - Purpose
- `LOCATED_AT` - Spatial
- `OCCURRED_AT` - Temporal
- `CREATED_BY` - Attribution
- `DEPENDS_ON` - Dependency
- `CONTRADICTS` - Conflict marker

**Graph Storage:**
- Neo4j for persistent graph storage
- RedisGraph for in-memory query acceleration
- Tenant-isolated graph namespaces
- Time-based versioning of all edges

### Graph Visualization

Interactive graph visualization flows:

1.  **Initial View**: Notebook entities as nodes, relationships as edges
2.  **Expansion**: Click node to show adjacent entities
3.  **Filtering**: By entity type, confidence, time range
4.  **Drill-down**: Click edge to view supporting note
5.  **Export**: SVG, PNG, or interactive JSON format

---

## Workflow Engine

### LangGraph Patterns

Notebook memory integrates natively with LangGraph orchestration:

```
┌─────────────────────────────────────────────────────────┐
│                  LangGraph Execution                    │
├─────────────────────────────────────────────────────────┤
│  1. Retrieve relevant notes from notebook              │
│  2. Expand entity graph neighborhood                   │
│  3. Inject context into LLM prompt                     │
│  4. Execute reasoning step                             │
│  5. Write new note with reasoning output               │
│  6. Update graph with new entities/relationships       │
│  7. Repeat until completion condition                  │
└─────────────────────────────────────────────────────────┘
```

**Graph-Aware Node Types:**
- `NotebookRetriever` - Semantic + graph hybrid retrieval
- `EntityExpander` - Graph neighborhood expansion
- `NoteWriter` - Persist reasoning outputs
- `GraphUpdater` - Extract and write new relationships

### Reasoning Loops

Self-improving memory reasoning loops:

```
Query → Retrieve → Reason → Write Note → Update Graph → Refine Query
```

**Loop Controls:**
- Maximum iteration count (default: 5)
- Confidence threshold for termination
- User interruption points
- Progress tracking in notebook
- Full audit trail of all reasoning steps

### Source Citation

Every output from the memory system includes full provenance:

```
Response Text
├─ Claim 1 → Cited Note #42 → Source #17, Page 3
├─ Claim 2 → Cited Note #18 → Source #9, Paragraph 7
└─ Claim 3 → Cited Note #61 → Tool Output #234
```

**Citation Requirements:**
- Every factual claim must have at least one citation
- Citations include exact location in source
- Confidence score per citation
- User can click through to original source
- Contradictory citations are flagged explicitly

---

## Butler Integration

### Memory Service Integration

Notebook Graph Memory extends the core Butler Memory service:

```
Butler Memory Service
├─ Episodic Memory
├─ Semantic Memory
└─ Notebook Graph Memory ← This component
```

**Integration Points:**
- Memory search returns notebook notes alongside other memory types
- Orchestrator can create notebooks during task execution
- Tools automatically write outputs to active notebook
- User conversations are auto-saved to default notebook

### Tool Policy Enforcement

All graph operations respect Butler's tool security policies:

- Entity extraction runs in isolated sandbox
- No cross-tenant graph traversal
- Graph queries are rate limited per tenant
- Sensitive entities are redacted based on user permissions
- All graph modifications are audited

### Tenant Scoping

Complete tenant isolation at every layer:

| Layer | Isolation Mechanism |
|-------|---------------------|
| Sources | Tenant ID foreign key |
| Notes | Tenant ID foreign key |
| Entities | Tenant ID foreign key |
| Graph | Separate graph namespace |
| Indexes | Tenant-separated vector indexes |
| Storage | Encryption per tenant key |

---

## Operational Characteristics

| Metric | Target |
|--------|--------|
| Entity extraction latency | < 500ms |
| Graph query latency | < 100ms |
| Note creation throughput | 100/sec per tenant |
| Maximum entities per tenant | 1,000,000 |
| Maximum notes per tenant | 10,000,000 |
| Graph traversal depth | 5 hops default |

---

## Implementation Status

✅ **Complete:**
- Source ingestion pipeline
- Note creation interface
- Entity extraction service
- Basic graph storage
- LangGraph integration nodes

🔄 **In Progress:**
- Graph visualization UI
- Advanced relationship extraction
- Reasoning loop orchestration
- Conflict detection

⏳ **Planned:**
- Entity deduplication ML model
- Graph-based recommendation engine
- Cross-notebook entity linking

---

## References

1.  Open Notebook Patterns - https://github.com/antigravity-ai/open-notebook
2.  LangGraph Documentation - https://langchain-ai.github.io/langgraph/
3.  LLM Graph Builder - https://github.com/llm-tools/graph-builder
4.  Butler Memory Service Specification - docs/03-reference/services/memory.md
