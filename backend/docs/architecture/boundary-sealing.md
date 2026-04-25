# Boundary Sealing Policy

This document defines the boundary sealing policy for Butler, ensuring that all system components interact through canonical interfaces and that direct bypasses are prevented.

## System Boundaries

### 1. Tool Execution Boundary

**Canonical Path:** `ToolExecutor.execute_canonical()`

**Sealed Bypasses:**
- Direct calls to `ButlerToolDispatch.handle_function_call()`
- Direct calls to `Hermes.handle_function_call()`
- Direct tool execution without policy evaluation
- Direct tool execution without audit logging

**Allowed Exceptions:**
- `services/tools/executor.py` - ToolExecutor implementation
- `domain/tools/hermeses_compiler.py` - Hermes compiler

### 2. ML Runtime Boundary

**Canonical Path:** `MLRuntime` through provider registry

**Sealed Bypasses:**
- Direct imports of `openai` outside `services/ml/` and `integrations/`
- Direct imports of `anthropic` outside `services/ml/` and `integrations/`
- Direct provider SDK calls without health checking
- Direct provider SDK calls without fallback chains

**Allowed Exceptions:**
- `services/ml/` - ML Runtime service
- `integrations/` - External integrations
- `tests/` - Test files

### 3. Memory Access Boundary

**Canonical Path:** `MemoryService` with `MemoryPolicy` and `MemoryScopeKey`

**Sealed Bypasses:**
- Direct memory operations without `tenant_id`/`account_id`
- Direct Qdrant queries without tenant filters
- Direct Neo4j queries without tenant labels/properties
- Memory writes without policy evaluation

**Allowed Exceptions:**
- `infrastructure/qdrant/` - Qdrant abstraction layer
- `infrastructure/neo4j/` - Neo4j abstraction layer

### 4. Router Boundary

**Canonical Path:** `OperationRouter` for all operations

**Sealed Bypasses:**
- Direct service calls without router admission control
- Direct tool execution without router routing
- Direct memory service calls without router routing

**Allowed Exceptions:**
- `domain/orchestration/router.py` - Router implementation
- `services/orchestrator/` - Orchestrator integration

### 5. Logging Boundary

**Canonical Path:** `TenantAwareLogger` from `core/tenant_aware_logger.py`

**Sealed Bypasses:**
- Direct `logging` module usage
- Direct `loguru` or other logger usage
- Raw IDs in logs (use hashed/tokens)
- Secrets in logs (use redaction)

**Allowed Exceptions:**
- `core/tenant_aware_logger.py` - Tenant-aware logger implementation
- `tests/` - Test files

### 6. Subprocess Boundary

**Canonical Path:** Workspace service sandbox execution

**Sealed Bypasses:**
- Direct `subprocess` calls outside `services/workspace/`
- Direct `subprocess` calls outside `integrations/`
- Arbitrary command execution without sandbox

**Allowed Exceptions:**
- `services/workspace/` - Workspace service
- `integrations/` - External integrations
- `tests/` - Test files

### 7. Redis Key Boundary

**Canonical Path:** `TenantNamespace` for key construction

**Sealed Bypasses:**
- Raw Redis key construction without tenant namespace
- Direct Redis operations without namespacing

**Allowed Exceptions:**
- `infrastructure/redis/` - Redis abstraction layer
- `core/redis/` - Core Redis utilities

### 8. LangChain Boundary

**Canonical Path:** Use Butler's canonical runtime (orchestrator/executor) for agent operations

**Sealed Bypasses:**
- Direct LangChain agent execution outside `langchain/` directory
- Direct LangChain tool calls bypassing ToolExecutor
- Direct LangChain memory operations bypassing MemoryService
- Direct LangChain provider SDK imports outside `langchain/providers/`

**Allowed Exceptions:**
- `langchain/` directory - Legacy LangChain integration (marked for migration)
- `domain/tools/adapters/langchain_adapter.py` - LangChain to Butler tool adapter
- `services/tools/langchain_adapter.py` - LangChain tool adapter service
- `tests/langchain/` - LangChain integration tests

**Migration Path:**
- Phase 14: Classify LangChain modules for migration/deprecation
- Phase 14: Migrate useful patterns to canonical runtime
- Phase 14: Archive or delete unused legacy code

## Sealing Process

### Step 1: Identify Bypasses
Use CI safety checks to identify all bypasses in the codebase.

### Step 2: Document Exception
If a bypass is legitimate, document it in `docs/architecture/ci-allowlist.md`.

### Step 3: Refactor to Canonical Path
If a bypass is not legitimate, refactor to use the canonical interface.

### Step 4: Add Import Guards
Add import guards or deprecation warnings for legacy code paths.

### Step 5: Update Tests
Ensure tests verify that canonical paths are used.

## Enforcement

### CI Enforcement
- All bypasses are caught by CI safety checks
- CI checks run on every pull request
- CI allowlist documents all legitimate exceptions

### Code Review Enforcement
- Code reviewers must verify that canonical paths are used
- Code reviewers must check for bypasses not caught by CI

### Runtime Enforcement
- Where possible, add runtime checks to prevent bypasses
- Use dependency injection to force canonical paths

## Audit Schedule

Quarterly audit of:
1. CI allowlist for obsolete exceptions
2. Legacy import guards for removal
3. Boundary sealing completeness
4. New bypass patterns not caught by CI

## Migration Strategy

For existing bypasses:

1. **Phase 1:** CI checks identify bypasses
2. **Phase 2:** Document legitimate exceptions in allowlist
3. **Phase 3:** Refactor illegitimate bypasses to canonical paths
4. **Phase 4:** Add deprecation warnings to legacy code
5. **Phase 5:** Remove legacy code paths after deprecation period

## Success Criteria

- All CI checks pass with no false positives
- CI allowlist is minimal and well-documented
- All new code uses canonical paths by default
- Legacy code is either refactored or documented
- System is production-safe with enforced boundaries
