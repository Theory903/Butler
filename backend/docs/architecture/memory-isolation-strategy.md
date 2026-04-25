# Memory Isolation Strategy

This document defines the memory isolation strategy for Butler, ensuring that tenant and account data is properly scoped and isolated across all memory operations.

## Overview

**Goal:** Ensure complete tenant and account isolation for all memory operations
**Scope:** Memory service, Qdrant vector store, Neo4j graph database
**Status:** Contract-only - implementation pending

## Memory Scoping Model

### Tenant Scope
- **Purpose:** Multi-tenant SaaS isolation
- **Enforcement:** All memory operations require tenant_id
- **Database:** tenant_id column on all memory tables
- **Vector Store:** Qdrant filters by tenant_id
- **Graph Database:** Neo4j labels/properties for tenant_id

### Account Scope
- **Purpose:** Account-level data isolation within tenant
- **Enforcement:** All memory operations require account_id
- **Database:** account_id column on all memory tables
- **Vector Store:** Qdrant filters by account_id
- **Graph Database:** Neo4j labels/properties for account_id

### Session Scope
- **Purpose:** Session-level data isolation
- **Enforcement:** Memory operations scoped to session_id
- **Database:** session_id column on relevant tables
- **Vector Store:** Qdrant filters by session_id
- **Graph Database:** Neo4j relationships for session_id

## MemoryScopeKey

The `MemoryScopeKey` dataclass defines the scoping context for memory operations:

```python
@dataclass(frozen=True)
class MemoryScopeKey:
    tenant_id: UUID
    account_id: UUID
    session_id: str | None = None
    memory_type: str | None = None
```

### Usage
- All memory service methods accept MemoryScopeKey
- MemoryScopeKey is used to construct Qdrant filters
- MemoryScopeKey is used to construct Neo4j queries
- MemoryScopeKey is validated before all memory operations

## Qdrant Isolation

### Filter Construction
All Qdrant queries must include tenant_id and account_id filters:

```python
filter = Filter(
    must=[
        FieldCondition(key="tenant_id", match=MatchValue(value=str(scope_key.tenant_id))),
        FieldCondition(key="account_id", match=MatchValue(value=str(scope_key.account_id))),
    ]
)
```

### Collection Scoping
- Single collection per tenant (recommended)
- Or single collection with tenant_id/account_id filters
- Collection access controlled by tenant_id

### Point Scoping
- Each point includes tenant_id and account_id
- Points cannot be accessed without proper scoping
- Cross-tenant queries are blocked

## Neo4j Isolation

### Label Scoping
- Nodes include tenant_id and account_id properties
- Queries filter by tenant_id and account_id
- Cross-tenant queries are blocked

### Relationship Scoping
- Relationships include tenant_id and account_id properties
- Relationship queries filter by scope
- Cross-tenant relationships are blocked

### Cypher Query Patterns
All Cypher queries must include scope filters:

```cypher
MATCH (n:MemoryEntry)
WHERE n.tenant_id = $tenant_id AND n.account_id = $account_id
RETURN n
```

## Memory Service Integration

### MemoryService Methods
All MemoryService methods accept MemoryScopeKey:

```python
async def store_memory(
    self,
    scope_key: MemoryScopeKey,
    content: dict,
    memory_type: str,
) -> MemoryEntry:
    # Validate scope_key
    # Store with tenant_id and account_id
    # Return scoped memory entry
```

### MemoryPolicy Integration
MemoryPolicy defines retention and access rules per scope:

```python
@dataclass(frozen=True)
class MemoryPolicy:
    retention: RetentionPolicy
    max_size_mb: int
    allowed_access: frozenset[AccessLevel]
    pii_allowed: bool
    requires_encryption: bool
    right_to_erasure: bool
```

### Right-to-Erasure
- Erasure requests must include tenant_id and account_id
- All data for the scope is deleted
- Vector store points are deleted
- Graph database nodes are deleted

## Background Consolidation

### Consolidation Scoping
- Background consolidation is scoped to tenant_id and account_id
- Consolidation never crosses tenant boundaries
- Consolidation respects MemoryPolicy retention rules

### Consolidation Workflow
1. Query memory entries for scope (tenant_id, account_id)
2. Apply consolidation algorithm scoped to scope
3. Store consolidated results with same scope
4. Delete original entries (if policy allows)

## Implementation Status

### Completed
- MemoryPolicy dataclass defined
- MemoryScopeKey dataclass defined
- MemoryService accepts MemoryScopeKey (partial)
- CI check for unscoped memory operations

### Pending
- MemoryScopeKey integration into session_store
- Qdrant filter enforcement
- Neo4j label/property enforcement
- Background consolidation scoping
- Right-to-erasure workflow
- Memory isolation tests
- Remove memory bypasses (110 files)

## Migration Strategy

### Phase 1: Add Scoping to New Code
- All new memory code must use MemoryScopeKey
- All new memory code must include tenant_id/account_id filters

### Phase 2: Refactor Existing Code
- Update 110 files to use MemoryScopeKey
- Update Qdrant queries to include filters
- Update Neo4j queries to include filters

### Phase 3: Remove Bypasses
- Remove direct Qdrant client usage
- Remove direct Neo4j client usage
- Ensure all memory operations go through MemoryService

## Testing Strategy

### Unit Tests
- Test MemoryScopeKey validation
- Test Qdrant filter construction
- Test Neo4j query construction
- Test MemoryPolicy enforcement

### Integration Tests
- Test memory isolation between tenants
- Test memory isolation between accounts
- Test right-to-erasure workflow
- Test background consolidation scoping

### Security Tests
- Test cross-tenant query blocking
- Test cross-account query blocking
- Test unauthorized access blocking

## Failure Modes

### Missing Scope
- Memory operations fail without MemoryScopeKey
- Clear error message about required scoping

### Invalid Scope
- Memory operations fail with invalid tenant_id/account_id
- Clear error message about invalid scope

### Cross-Tenant Access
- Cross-tenant queries are blocked
- Security event logged
- Admin notified

## Monitoring

### Metrics
- Memory operations per tenant
- Memory operations per account
- Failed scope validations
- Cross-tenant access attempts

### Logging
- All memory operations log tenant_id and account_id
- All scope validations log results
- All cross-tenant attempts are logged as security events

## Compliance

### GDPR
- Right-to-erasure implemented
- Data retention policies enforced
- Data access logging

### SOC 2
- Tenant isolation verified
- Access controls enforced
- Audit trails maintained
