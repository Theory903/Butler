# Digital Twin Memory System
> **Version:** 2.0 (Oracle-Grade)
> **Updated:** 2026-04-20
> **Status:** Production Ready
> **Sources:** Supermemory, Open Notebook, LLM Graph Builder, Natively

---

## Overview

Butler's Digital Twin Memory is a sovereign, graph-backed memory system that maintains a persistent, evolving model of the user, their environment, preferences, and history. This is not chat history - this is a structured knowledge graph that grows with every interaction.

The user owns their digital twin; Butler manages it on their behalf with full transparency and control.

---

## Memory Layers

### Episodic Memory
Stores chronological interaction history with full context preservation:
- **Sliding-window RAG** with 50-token overlap for continuous recall
- **Epoch summarization**: Automatic compression of historical context every 100 interactions
- **Temporal indexing**: Precise timestamping with timezone awareness
- **Smart scope detection**: Automatically distinguishes current session context from historical memory
- **Memory scrubbing**: Secure, irreversible deletion on explicit user request or session exit

### Semantic Facts
Structured factual knowledge extracted from interactions:
- Entity resolution with deduplication
- Confidence scoring for extracted facts
- Source attribution tracking
- Automatic fact conflict resolution
- Decay curves for time-sensitive information

### Preferences
Hierarchical preference model:
- Explicit user stated preferences
- Implicit preference inference from behavior
- Preference strength scoring
- Context-dependent preference activation
- Preference override tracking

### Graph Relationships
Persistent memory graph connecting all entities:
- Nodes: People, places, things, concepts, events
- Edges: Relationships, actions, associations
- Weighted by confidence and recency
- Bidirectional traversal support
- Incremental graph updates

### Files & Uploads
Document-to-memory extraction pipeline:
- Full text indexing with vector embeddings
- Structured entity extraction from unstructured documents
- Source provenance tracking
- Access control inheritance
- Automatic summarization for large documents

---

## Digital Twin Profile

### Construction
The digital twin is built incrementally from all interactions:
1.  **Entity extraction** from every message and response
2.  **Relationship inference** between new and existing entities
3.  **Preference signal detection** from user behavior
4.  **Graph integration** with existing knowledge
5.  **Consistency validation** before commit

### Query Engine
Multi-modal memory retrieval system:
- **BM25 keyword search** for exact matches
- **Vector semantic search** for conceptual similarity
- **Graph traversal** for relational queries
- **Hybrid ranking** combining all three signals
- **Recency weighting** with configurable decay curves

### Temporal Reasoning
Native support for time-based queries:
- "What did we talk about last week?"
- "When did you first learn about X?"
- "How has my preference for Y changed over time?"
- Automatic timeline construction for entities

### Entity Resolution
Advanced deduplication system:
- Fuzzy matching for entity names
- Context-aware disambiguation
- Merge history tracking
- Conflict resolution workflows
- User override support

---

## Storage Architecture

### Local Storage Layer
- **SQLite** as primary persistent store
- **sqlite-vec** for vector embeddings storage and search
- Single file database per user for full portability
- ACID compliance with WAL mode enabled
- Zero external dependencies for core operation

### MCP Memory Server
Standardized Model Context Protocol server interface:
- Read-only memory access for tools and plugins
- Fine-grained capability-based access control
- Audit logging for all memory access
- Query cost attribution
- Rate limiting per consumer

---

## Training Data Pipeline

### Consent Model
Three-tier consent system for memory usage:

| Tier | Description | Usage Allowed |
|------|-------------|---------------|
| **never-train** | Explicitly excluded | No training, no evaluation, no logging |
| **private-eval** | Internal quality only | Used only for local model improvement, never leaves device |
| **opt-in** | Full training | User explicitly opted in to contribute anonymized data |

### Anonymization Pipeline
For opt-in data:
1.  PII removal (names, emails, phone numbers, locations)
2.  Entity generalization
3.  Context stripping
4.  Differential privacy noise injection
5.  K-anonymity verification before export

### Opt-in Flow
1.  Transparent explanation of what data is used
2.  Clear benefits to the user
3.  One-click opt-out at any time
4.  Full data export capability
5.  Permanent deletion on request

---

## Open Notebook Integration

### Notebook-as-Memory Workspace
Interactive memory workspace:
- User can view, edit, and annotate memory entries
- **Source / note / notebook triad** structure
- Graph visualization of relationships
- Manual fact correction interface
- Memory curation tools

### Knowledge Workflows
Graph-backed knowledge operations:
- Automatic connection of related concepts
- Suggested follow-up questions
- Knowledge gap detection
- Learning progress tracking
- Contextual reminder system

---

## LLM Graph Builder

### Graph Construction Pipeline
From every LLM output:
1.  Entity extraction pass
2.  Relationship identification
3.  Confidence scoring
4.  Graph integration
5.  Consistency validation

### Entity / Relationship Extraction
Zero-shot extraction with fine-tuned prompts:
- Named entity recognition
- Action verb detection
- Attribute extraction
- Temporal association
- Causal relationship identification

---

## Multi-Tenant Isolation

### Security Boundaries
- Complete database isolation per user
- No cross-user memory access
- Encryption at rest with user-specific keys
- Memory never leaves device without explicit consent
- Full audit trail for all access

### Memory Sovereignty
Butler owns the memory schema, not any third party:
- Open standard format
- Full user export capability
- No vendor lock-in
- User can delete all data at any time
- No hidden telemetry or data exfiltration

---

## Memory Recall UX

### Transparent Recall
- User always sees what memory was used
- Source citations for all recalled information
- Confidence indicators
- "Show me what you remember about X" command
- Explicit correction interface

---

## Operational Characteristics

| Metric | Target |
|--------|--------|
| Recall latency | < 100ms P95 |
| Graph update latency | < 500ms |
| Storage overhead | < 10KB per interaction |
| Maximum memory size | Unlimited |
| Vector dimension | 1536 |

---

## Anti-Patterns

❌ **Never** use memory for training without explicit consent
❌ **Never** leak memory contents to external tools
❌ **Never** assume facts without confidence scoring
❌ **Never** overwrite user corrections
❌ **Never** retain memory after explicit deletion request

✅ **Always** attribute memory sources
✅ **Always** respect consent tiers
✅ **Always** allow user inspection
✅ **Always** support full deletion
✅ **Always** maintain temporal accuracy

---

## Reference

- `docs/03-reference/system/notebook-graph-memory.md` — Notebook + graph integration
- `docs/02-services/memory.md` — Memory service specification
- `docs/04-operations/security/data-classification.md` — Data tier definitions
