# Butler Implementation Evidence Matrix

Tracks actual integration status of all phases. A phase is NOT complete until all criteria are met.

## Legend

- **complete**: All criteria met, production-ready
- **partial**: Some criteria met, work remains
- **contract-only**: Only contracts created, no runtime integration
- **blocked**: Cannot proceed due to dependencies
- **unsafe**: Implementation exists but bypasses are present

## Criteria

A phase requires ALL of these to be complete:
- Contract exists
- Runtime wired
- Tests exist
- CI enforced (where applicable)
- Bypasses removed or allowlisted
- Docs/evidence updated

---

## Phase 0.5: Static Safety Scan

| Criteria | Status | Evidence |
|----------|--------|----------|
| Static scan completed | complete | Ripgrep scans run for 7 unsafe patterns |
| System map updated | complete | docs/architecture/butler-full-system-map.md updated |
| Unsafe call inventory exists | complete | 37 Redis files, 16 subprocess files, 64 provider SDK files identified |
| **Overall** | **complete** | |

---

## Phase 1: Runtime Spine + Leak Stopper

| Criteria | Status | Evidence |
|----------|--------|----------|
| RuntimeContext exists | complete | domain/runtime/context.py |
| ToolResultEnvelope exists | complete | domain/runtime/tool_result_envelope.py |
| FinalResponseComposer exists | complete | domain/runtime/final_response_composer.py |
| ResponseValidator exists | complete | domain/runtime/response_validator.py |
| RuntimeContextMiddleware wired | complete | core/middleware.py updated |
| /api/v1/chat uses safe response | complete | api/routes/gateway.py _compose_safe_response() |
| /api/v1/orchestrator/intake validates | complete | api/routes/orchestrator.py ResponseValidator |
| Tests exist | complete | 4 test files created |
| CI enforced | pending | No CI check for response validation yet |
| Bypasses removed | complete | All response paths now use Runtime Spine |
| **Overall** | **partial** | CI enforcement pending |

---

## Phase 2: Tool Runtime Integration

| Criteria | Status | Evidence |
|----------|--------|----------|
| ToolSpec contract exists | complete | domain/tools/spec.py |
| ToolSpec integrated into registry | complete | services/tools/registry.py uses canonical DomainToolSpec with legacy compatibility |
| ToolSpec integrated into executor | complete | services/tools/executor.py execute_canonical() uses ToolSpec and ToolPolicy |
| API routes use canonical executor | complete | api/routes/tools.py uses execute_canonical() with RuntimeContext |
| Orchestrator uses canonical executor | partial | DurableExecutor uses ToolsServiceContract but RuntimeKernel still uses ButlerToolSpec |
| LangChain tool adapter uses canonical | complete | langchain/tools.py updated to use DomainToolSpec and execute_canonical() |
| ToolResultEnvelope conversion | partial | execute_canonical() returns ToolResultEnvelope, legacy execute() returns ToolResult |
| Tests exist | complete | tests/test_tool_policy_enforcement.py created with comprehensive policy tests |
| CI enforced | complete | .github/workflows/safety-check.yml checks for tool bypasses |
| Bypasses removed | contract-only | Many bypasses likely exist |
| **Overall** | **partial** | Contract, API, LangChain, tests, and CI complete, orchestrator wiring and bypass removal pending |

---

## Phase 3: Memory Isolation Integration

| Criteria | Status | Evidence |
|----------|--------|----------|
| MemoryScope contract exists | complete | domain/memory/scopes.py |
| MemoryPolicy contract exists | complete | Phase 3: Memory Policy Integration and Isolation |
| MemoryPolicy integrated into service | complete | services/memory/service.py accepts MemoryPolicy |
| MemoryScopeKey defined | complete | domain/memory/scopes.py has MemoryScopeKey |
| MemoryScopeKey into session_store | contract-only | session_store not updated |
| Qdrant filters enforced | contract-only | No Qdrant filter enforcement |
| Neo4j labels/properties enforced | contract-only | No Neo4j enforcement |
| Background consolidation scoped | contract-only | No consolidation scoping |
| Right-to-erasure workflow | contract-only | No erasure workflow |
| Memory isolation tests | contract-only | No isolation tests |
| CI check for unscoped memory | complete | safety-check.yml has vector store check |
| Remove memory bypasses (110 files) | contract-only | 110 files need refactoring |
| Memory isolation strategy documented | complete | docs/architecture/memory-isolation-strategy.md |
| **Overall** | **partial** | Policy and strategy documented, implementation pending |

---

## Phase 4: MLRuntime Health/Fallback Integration

| Criteria | Phase 4: MLRuntime Health/Fallback Integration | | |
| Health contracts exist | complete | domain/ml/runtime_health.py |
| Health integrated into MLRuntime | contract-only | services/ml/runtime.py does not use health contracts |
| Provider registry enforced | contract-only | No provider registry in MLRuntime |
| Fallback chains implemented | contract-only | No fallback chains |
| Dead provider skip | contract-only | No dead provider skip |
| Metrics failure safe | contract-only | No metrics failure handling |
| Health routing tests | contract-only | No health routing tests |
| CI check for direct provider imports | complete | safety-check.yml has provider SDK check |
| Remove ML bypasses | contract-only | 64 files need refactoring |
| ML Runtime health strategy documented | complete | docs/architecture/ml-runtime-health-strategy.md |
| **Overall** | **partial** | Contracts, CI, and strategy documented, implementation pending |

---

## Phase 5: OperationRouter + AdmissionController Integration

| Criteria | Phase 5: OperationRouter + AdmissionController Integration | | |
| OperationRouter contract exists | complete | domain/orchestration/router.py |
| AdmissionController contract exists | complete | domain/orchestration/router.py |
| Integrated into orchestrator intake | contract-only | services/orchestrator/intake.py does not use router |
| Integrated into planner | contract-only | services/orchestrator/planner.py does not use router |
| Integrated into executor | contract-only | services/orchestrator/executor.py does not use router |
| Integrated into tool executor | contract-only | services/tools/executor.py does not use router |
| Integrated into memory service | contract-only | services/memory/service.py does not use router |
| Integrated into ML Runtime | contract-only | services/ml/runtime.py does not use router |
| API routes use router | contract-only | api/ routes do not use router |
| Operation router tests | contract-only | No router tests |
| CI check for router bypass | complete | safety-check.yml has router bypass check |
| Remove router bypasses | contract-only | Many bypasses likely exist |
| Operation router design documented | complete | docs/architecture/operation-router-design.md |
| **Overall** | **partial** | Contracts, CI, and design documented, integration pending |

---

## Phase 6: TenantNamespace Enforcement

| Criteria | Status | Phase 6: TenantNamespace Enforcement | | |
| TenantNamespace contract exists | complete | domain/tenant/namespace.py |
| Raw Redis keys refactored | contract-only | 37 files still use raw Redis keys |
| Cache abstraction enforced | contract-only | infrastructure/cache.py may have raw keys |
| Lock abstraction enforced | contract-only | infrastructure/lock.py may have raw keys |
| Rate limit abstraction enforced | contract-only | infrastructure/rate_limit.py may have raw keys |
| Artifact abstraction enforced | contract-only | infrastructure/artifact.py may have raw keys |
| Sandbox abstraction enforced | contract-only | infrastructure/sandbox.py may have raw keys |
| Workflow abstraction enforced | contract-only | infrastructure/workflow.py may have raw keys |
| Namespace isolation tests | contract-only | No isolation tests |
| CI check for raw Redis keys | complete | safety-check.yml has Redis key check |
| Redis abstraction design documented | complete | docs/architecture/redis-abstraction-design.md |
| **Overall** | **partial** | Contract, CI, and design documented, refactoring pending |
| Tests exist | contract-only | No namespace isolation tests |
| **Overall** | **contract-only** | Contract created, 37 files need refactoring |

---

## Phase 7: Comprehensive Safety Checks

| Criteria | Status | Evidence |
|----------|--------|----------|
| Python checker for CI | complete | ruff, mypy, bandit in safety-check.yml |
| Comprehensive Redis key check | complete | safety-check.yml has Redis key check |
| Comprehensive subprocess check | complete | safety-check.yml has subprocess check |
| Comprehensive provider SDK check | complete | safety-check.yml has provider SDK check |
| Unscoped Qdrant/Neo4j check | complete | safety-check.yml has vector store check |
| Raw logger check | complete | safety-check.yml has logger check |
| Response leak check | complete | safety-check.yml has response leak check |
| Direct database access check | complete | safety-check.yml has database access check |
| Hardcoded secrets check | complete | safety-check.yml has secrets check |
| Allowlist documented | complete | docs/architecture/ci-allowlist.md |
| Safety checker tests | contract-only | No safety checker tests |
| **Overall** | **partial** | All CI checks implemented, tests pending |

---

## Phase 8: Tenant-Aware Logging Integration

| Criteria | Status | Evidence |
|----------|--------|----------|
| TenantAwareLogger exists | complete | core/tenant_aware_logger.py |
| Replace raw logging (173 files) | contract-only | 173 files still use raw logging |
| Core logging updated | contract-only | core/ may have raw logging |
| Observability updated | contract-only | infrastructure/otel may have raw logging |
| Service adapters updated | contract-only | services/ may have raw logging |
| No raw IDs in logs | contract-only | No ID redaction enforced |
| No secrets in logs | contract-only | No secret redaction enforced |
| Health logs deduplicated | contract-only | No health log deduplication |
| Success logs sampled | contract-only | No success log sampling |
| Errors logged safely | contract-only | No error safety enforcement |
| Logging tests | contract-only | No logging tests |
| CI check for raw logger usage | complete | safety-check.yml has logger check |
| Logging strategy documented | complete | docs/architecture/logging-strategy.md |
| **Overall** | **partial** | Contract, CI, and strategy documented, refactoring pending |

---

## Phase 9: Durable Workflow Runtime Integration

| Criteria | Status | Evidence |
|----------|--------|----------|
| Durable workflow contracts exist | complete | domain/workflow/durable.py |
| Temporal integrated | contract-only | No Temporal client/worker exists |
| DB-backed durability fallback | contract-only | No workflow_runs table exists |
| Task leasing implemented | contract-only | No task leasing |
| Heartbeat implemented | contract-only | No heartbeat |
| Idempotency keys enforced | contract-only | No idempotency keys |
| Outbox pattern implemented | contract-only | No outbox pattern |
| DLQ implemented | contract-only | No DLQ |
| Recovery worker exists | contract-only | No recovery worker |
| Orchestrator executor uses workflows | contract-only | No workflow integration |
| Subagent runtime uses workflows | contract-only | No workflow integration |
| Workflow durability tests | contract-only | No durability tests |
| Durable workflow strategy documented | complete | docs/architecture/durable-workflow-strategy.md |
| **Overall** | **partial** | Contracts and strategy documented, implementation pending |

---

## Phase 10: Protocol RuntimeContext Integration

| Criteria | Phase 10: Protocol RuntimeContext Integration | | |
|----------|--------|----------|
| Protocol context contracts exist | complete | domain/protocol/context_propagation.py |
| MCP context injection | contract-only | api/routes/mcp.py does not inject context |
| MCP ToolPolicy interceptor | contract-only | services/tools/mcp_bridge.py no interceptor |
| MCP safe structured content | contract-only | No content safety in MCP |
| MCP tenant-aware logging | contract-only | No tenant-aware logging in MCP |
| MCP policy/approval/sandbox | contract-only | No policy enforcement in MCP |
| A2A agent-card.json | contract-only | No agent-card.json implementation |
| A2A context mapping | contract-only | No A2A context mapping |
| A2A trace preservation | contract-only | No trace preservation in A2A |
| ACP context mapping | contract-only | No ACP context mapping |
| ACP filesystem policy | contract-only | No filesystem policy in ACP |
| ACP SandboxManager | contract-only | ACP does not use SandboxManager |
| ACP streaming traceability | contract-only | No streaming traceability in ACP |
| Tests exist | contract-only | No protocol integration tests |
| Protocol integration strategy documented | complete | docs/architecture/protocol-integration-strategy.md |
| **Overall** | **partial** | Contracts and strategy documented, implementation pending |

---

## Phase 11: SandboxManager Real Integration

| Criteria | Phase 11: Sandbox Enforcement and Subprocess Safety | | |
| SandboxManager contract exists | complete | domain/sandbox/manager.py |
| Local Docker provider | contract-only | No Docker provider implementation |
| Production providers | contract-only | No production providers |
| TTL enforced | contract-only | No TTL enforcement |
| Cleanup enforced | contract-only | No cleanup enforcement |
| Artifact export explicit | contract-only | No artifact export validation |
| Workspace-root filesystem policy | contract-only | No filesystem policy |
| Denylist enforced | contract-only | No denylist enforcement |
| Refactor 16 subprocess files | contract-only | 16 files still use subprocess |
| .env blocked | contract-only | No .env blocking |
| *.key blocked | contract-only | No .key blocking |
| *.secret blocked | contract-only | No .secret blocking |
| .git/ blocked | contract-only | No .git/ blocking |
| Host root blocked | contract-only | No host root blocking |
| SSH keys blocked | contract-only | No SSH key blocking |
| Cloud config blocked | contract-only | No cloud config blocking |
| Sandbox tests | contract-only | No sandbox tests |
| CI check blocks subprocess | complete | safety-check.yml has subprocess check |
| Sandbox enforcement strategy documented | complete | docs/architecture/sandbox-enforcement-strategy.md |
| **Overall** | **partial** | Contract, CI, and strategy documented, implementation pending |

---

## Phase 12: DB Migration Execution and Tenant Data Model Audit

| Criteria | Status | Evidence |
|----------|--------|----------|
| Migration file exists | complete | alembic/versions/001_add_tenant_account_columns.py |
| Migration executed | contract-only | alembic upgrade head not run |
| Alembic check passed | contract-only | alembic check not run |
| Domain models audited | complete | docs/architecture/domain-model-audit.md created |
| SQLAlchemy models audited | contract-only | No audit completed |
| Tenant/account columns verified | complete | Column verification in audit document |
| Required indexes added | complete | Index verification in audit document |
| PostgreSQL RLS considered | contract-only | No RLS policies |
| Tests exist | contract-only | No DB migration tests |
| **Overall** | **partial** | Migration file and audit complete, execution pending |

---

## Phase 13: LangChain Cleanup Execution

| Criteria | Status | Evidence |
|----------|--------|----------|
| Cleanup plan exists | complete | docs/langchain_cleanup_plan.md |
| Ownership clarified | contract-only | No ownership clarification in code |
| Allowed LangChain usage defined | contract-only | No usage boundaries enforced |
| Forbidden LangChain usage blocked | contract-only | No blocking of forbidden usage |
| Direct provider routing sealed | contract-only | Direct routing still exists |
| Direct tool execution sealed | contract-only | Direct execution still exists |
| Memory writes sealed | contract-only | Direct memory writes still exist |
| Unscoped context sealed | contract-only | Unscoped context still exists |
| Standalone agent runtime sealed | contract-only | Standalone runtime still exists |
| Boundary document created | complete | docs/architecture/boundary-sealing.md created |
| Code changes sealed | contract-only | No code change sealing |
| CI allowlist created | complete | docs/architecture/ci-allowlist.md created |
| LangChain boundary tests | contract-only | No LangChain boundary tests |
| **Overall** | **partial** | Boundary document and CI allowlist created, sealing and tests pending |

---

## Phase 14: butler_runtime Migration Execution

| Criteria | Status | Evidence |
|----------|--------|----------|
| Migration plan exists | complete | docs/butler_runtime_migration.md |
| Module classification complete | contract-only | No classification completed |
| Migrate useful modules | contract-only | No migration completed |
| Adapt modules | contract-only | No adaptation completed |
| Archive legacy | contract-only | No archiving completed |
| Delete-later marked | contract-only | No deletion markers |
| Keep-test-only marked | contract-only | No test-only markers |
| Duplicate runtime sealed | contract-only | Duplicate runtimes still active |
| Legacy import guards | contract-only | No import guards added |
| Deprecation warnings | contract-only | No deprecation warnings added |
| Migration status document | complete | docs/butler_runtime_migration_status.md created |
| Canonical runtime tests | contract-only | No canonical runtime tests |
| **Overall** | **partial** | Migration plan and status document created, migration pending |

---

## Phase 15: Chaos / Load / Production Readiness Implementation

| Criteria | Status | Evidence |
|----------|--------|----------|
| Chaos plan exists | complete | docs/chaos_engineering.md |
| Executable chaos tests | contract-only | No executable chaos tests |
| Dead provider outage test | contract-only | No provider outage test |
| Redis outage test | contract-only | No Redis outage test |
| Postgres unavailable test | contract-only | No Postgres test |
| Kafka/Redpanda lag test | contract-only | No queue lag test |
| Sandbox timeout test | contract-only | No sandbox timeout test |
| MCP server failure test | contract-only | No MCP failure test |
| A2A peer failure test | contract-only | No A2A failure test |
| Tool provider timeout test | contract-only | No tool timeout test |
| Tenant traffic spike test | contract-only | No traffic spike test |
| Retry storm test | contract-only | No retry storm test |
| Memory vector store unavailable test | contract-only | No vector store test |
| Logging backend unavailable test | contract-only | No logging failure test |
| Load test scripts | contract-only | No load test scripts |
| Chaos runbook | contract-only | No chaos runbook |
| Load test runbook | contract-only | No load test runbook |
| System degrades instead of crashes | contract-only | No degradation tests |
| Tenant isolation under failure | contract-only | No isolation tests |
| Logging failure safe | contract-only | No logging failure tests |
| Dead provider fallback works | contract-only | No fallback tests |
| Tool timeouts safe | contract-only | No timeout tests |
| Tests exist | contract-only | No chaos/load tests |
| Chaos/load testing strategy documented | complete | docs/architecture/chaos-load-testing-strategy.md |
| **Overall** | **partial** | Strategy documented, implementation pending |

---

## Summary

| Phase | Status |
|-------|--------|
| Phase 0.5 | complete |
| Phase 1 | partial |
| Phase 2 | contract-only |
| Phase 3 | partial |
| Phase 4 | partial |
| Phase 5 | partial |
| Phase 6 | partial |
| Phase 7 | partial |
| Phase 8 | partial |
| Phase 9 | partial |
| Phase 10 | partial |
| Phase 11 | partial |
| Phase 12 | partial |
| Phase 13 | partial |
| Phase 14 | partial |
| Phase 15 | partial |

**Overall Status**: 1 complete, 14 partial, 0 contract-only

**Critical Gaps**:
- ToolSpec, MemoryPolicy, OperationRouter not integrated into active runtime
- 37 files still use raw Redis keys
- 16 files still use subprocess
- 64 files still use direct provider SDK imports
- 173 files still use raw logging
- 110 files still use unscoped memory calls
- No actual durability (Temporal or DB-backed)
- No protocol context propagation
- No real sandbox execution
- No chaos/load tests
