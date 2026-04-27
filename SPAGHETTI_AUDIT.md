# Butler Runtime Spaghetti Audit

## 1. Executive Verdict

**RELEASE BLOCKER**

The Butler runtime exhibits significant architectural spaghetti with multiple overlapping execution paths, duplicate processing, and unclear boundaries. The current state is not production-ready for the LangGraph agentic mode.

## 2. Request Path Trace

Request: "what is the time"

1. **required** - `/api/v1/chat` (gateway.py:307) - Rate limit, idempotency, envelope building
2. **required** - Forward to `/api/v1/orchestrator/intake` (gateway.py:359)
3. **required** - `orchestrator_intake()` (orchestrator.py:54) - Calls svc.intake(envelope)
4. **suspicious** - `svc.intake()` (service.py:397) - **DUPLICATE** intake.process() call #1 (line 416)
5. **suspicious** - `_create_plan()` (service.py:418) - Plan creation
6. **suspicious** - **BYPASS** graph for agentic mode (service.py:438-444) - "avoid circular dependency"
7. **suspicious** - Return `_intake_core()` (service.py:444) - **SECOND** intake.process() call #2 (line 559)
8. **required** - `_check_safety()` (service.py:536)
9. **required** - `_redact_input()` (service.py:549)
10. **required** - Session store append (service.py:557)
11. **duplicate** - `intake.process()` called AGAIN (service.py:559) - **THIRD** call total
12. **required** - `_build_blended_candidates()` (service.py:577)
13. **required** - `_create_workflow()` (service.py:581) - DB workflow insert
14. **required** - `_create_plan()` (service.py:588) - Plan creation (2nd time)
15. **required** - Task creation and DB insert (service.py:605-612)
16. **required** - `_build_messages()` (service.py:614)
17. **required** - ExecutionContext creation (service.py:620)
18. **required** - `_executor._kernel.execute_result()` (service.py:637) - RuntimeKernel
19. **suspicious** - Backend selection via BUTLER_AGENT_RUNTIME feature flag (backends.py:22)
20. **required** - LangGraph agent creation (agent.py) if langgraph
21. **required** - Tool compilation (tools.py)
22. **required** - Tool binding to LLM (models.py)
23. **required** - LLM invocation (runtime.py)
24. **required** - Tool call conversion (models.py) - Fixed in Phase 1
25. **required** - Tool execution (agent.py tools_node)
26. **required** - Response generation
27. **required** - Memory/session persistence

## 3. Redundant / Unnecessary Flow Table

| Area | File / Function | Problem | Evidence | Classification | Fix |
|---|---|---|---|---|---|
| Intake processing | service.py:416, 559 | intake.process() called TWICE per request | Lines 416 and 559 both call await self._intake.process() | DUPLICATE | Remove first call, keep only in _intake_core |
| Graph bypass | service.py:438-444 | Explicit graph bypass for agentic mode | "Bypass graph entirely for agentic mode - use direct _intake_core" | DUPLICATE | Remove bypass, integrate graph path properly |
| Dual backends | backends.py:22, 599 | Feature flag controls backend selection | BUTLER_AGENT_RUNTIME env var selects Hermes vs LangGraph | DUPLICATE | Choose one backend, remove feature flag |
| Graph compilation | service.py:455-460 | Graph compiled but bypassed | Graph compiled on first use but bypassed for agentic | DUPLICATE | Either use graph or remove compilation |
| Plan creation | service.py:418, 588 | Plan created TWICE | _create_plan() called in intake() and _intake_core() | DUPLICATE | Consolidate to single plan creation |
| Tool registries | Multiple files | 4+ registries describe tools differently | Hermes tier map, direct_implementations, ButlerToolSpec, LangGraph wrappers | REGISTRY DRIFT | Consolidate to single canonical registry |
| Session hydration | service.py:552-557 | Session store created in _intake_core | ButlerSessionStore created per request | SUSPICIOUS | Cache or reuse session store |
| Environment snapshot | intake.py:95 | Optional environment service with fallback | _build_environment_block() with try/except | SILENT FALLBACK | Make explicit or remove |

## 4. Tool Registry Drift Report

| Tool | Exposed? | Direct Impl? | DB Definition? | Risk Tier | Approval | Problem | Fix |
|---|:---:|---:|---:|---|---|---|---|
| get_time | YES (tier map) | YES (direct_implementations) | UNKNOWN | L0 (tier map) | NONE (tier map) | Schema mismatch - tier map has no input_schema | Add input_schema to tier map |
| web_search | YES | YES (butler_web_tools) | UNKNOWN | L1 (tier map) | NONE | Schema mismatch - tier map has no input_schema | Add input_schema to tier map |
| memory_recall | YES (tier map) | NO | UNKNOWN | L0 (tier map) | NONE | Ghost exposure - no direct implementation | Either add implementation or remove from tier map |
| session_search | YES (tier map) | NO | UNKNOWN | L0 (tier map) | NONE | Ghost exposure - no direct implementation | Either add implementation or remove from tier map |
| list_files | YES (tier map) | NO | UNKNOWN | L0 (tier map) | NONE | Ghost exposure - no direct implementation | Either add implementation or remove from tier map |
| read_file | YES (tier map) | NO | UNKNOWN | L0 (tier map) | NONE | Ghost exposure - no direct implementation | Either add implementation or remove from tier map |
| clarify | YES (tier map) | NO | UNKNOWN | L0 (tier map) | NONE | Ghost exposure - no direct implementation | Either add implementation or remove from tier map |
| fuzzy_match | YES (tier map) | NO | UNKNOWN | L0 (tier map) | NONE | Ghost exposure - no direct implementation | Either add implementation or remove from tier map |
| url_safety_check | YES (tier map) | NO | UNKNOWN | L0 (tier map) | NONE | Ghost exposure - no direct implementation | Either add implementation or remove from tier map |
| osv_check | YES (tier map) | NO | UNKNOWN | L0 (tier map) | NONE | Ghost exposure - no direct implementation | Either add implementation or remove from tier map |

**Critical Finding:** 8 tools are exposed as L0/L1 (no approval required) but have NO direct implementation. This violates the invariant "No L0/L1 tool may be exposed unless direct execution exists."

## 5. Duplicate Execution Report

### Duplicate intake.process() Calls
- **Location:** service.py lines 416 and 559
- **Impact:** Every agentic request processes intake TWICE
- **Expected:** No, this is a bug
- **Fix:** Remove the first call (line 416), keep only in _intake_core

### Duplicate Plan Creation
- **Location:** service.py lines 418 and 588
- **Impact:** Plan created twice per request
- **Expected:** No, this is a bug
- **Fix:** Consolidate to single plan creation in _intake_core

### Dual Backend Paths
- **Location:** backends.py line 22 (BUTLER_AGENT_RUNTIME feature flag)
- **Impact:** Two complete execution paths maintained (Hermes vs LangGraph)
- **Expected:** No, should be one authoritative path
- **Fix:** Choose LangGraph, deprecate Hermes backend

### Graph Compilation vs Bypass
- **Location:** service.py lines 455-479
- **Impact:** Graph compiled but bypassed for agentic mode
- **Expected:** No, either use graph or don't compile it
- **Fix:** Remove bypass logic or remove graph compilation

### Session Store Creation
- **Location:** service.py line 552
- **Impact:** Session store created per request without caching
- **Expected:** Possibly, but should be verified
- **Fix:** Add session store caching or validate this is intentional

## 6. Fallback Audit

| Fallback | Trigger | Safe? | Silent? | Hides Bug? | Should Keep? | Fix |
|---|---|---:|---:|---:|---:|---|
| Hermes registry import | ImportError | YES | YES | NO | NO | Fail closed - Hermes is optional, should gate features |
| Graph bypass for agentic | Circular dependency comment | UNKNOWN | NO | YES | NO | Fix circular dependency properly |
| intake.process() catch | Exception in intake | UNKNOWN | YES | YES | NO | Remove duplicate call instead of catching |
| DeterministicModeRouter | Always returns "agentic" | YES | NO | NO | NO | Remove, hardcode or make real router |
| Environment snapshot | Exception in _build_environment_block | YES | YES | NO | YES | Keep but add explicit logging |
| Session store None check | store is None | YES | YES | NO | YES | Keep but document why None is valid |
| Provider fallback | Provider exhaustion | YES | YES | NO | YES | Keep but add bounded retry policy |
| Memory checkpoint fallback | Postgres unavailable | YES | YES | NO | YES | Keep but add alerting |
| Graph compilation | langgraph_available() false | YES | YES | NO | NO | Fail closed or gate features |

## 7. Boundary Violations

### API Layer
- **Violation:** gateway.py imports from services.orchestrator (line 359)
- **Impact:** API layer tightly coupled to orchestrator internals
- **Fix:** Use contract interface (OrchestratorServiceContract) instead

### Orchestrator Layer
- **Violation:** service.py imports from services.orchestrator.graph (line 403)
- **Impact:** Orchestrator service directly depends on LangGraph implementation
- **Fix:** Move graph compilation to separate adapter layer

### Planner Layer
- **Violation:** planner.py imports from domain.orchestration.router (line 17)
- **Impact:** Planner depends on operation router (different abstraction)
- **Fix:** Remove dependency, planner should only depend on contracts

### Runtime Kernel
- **Violation:** executor.py imports from services.orchestrator.backends (line 5)
- **Impact:** Runtime kernel depends on backend implementations
- **Fix:** Kernel should only depend on ExecutionContext contract

### Agent/LangGraph Layer
- **Violation:** agent.py imports from domain.tools.hermes_compiler (line 18)
- **Impact:** LangGraph agent depends on Hermes-specific compiler
- **Fix:** Use ButlerToolSpec contract instead of Hermes-specific type

### Tool Layer
- **Violation:** tools.py imports from domain.tools.hermes_compiler (line 13)
- **Impact:** Tool factory depends on Hermes compiler
- **Fix:** Use canonical ToolSpec contract

### Memory Layer
- **Violation:** service.py imports from services.memory.session_store (line 35)
- **Impact:** Orchestrator directly depends on memory implementation
- **Fix:** Use MemoryServiceContract interface

### MLRuntime Layer
- **Violation:** models.py imports from langchain_core (line 18)
- **Impact:** Butler runtime depends on LangChain internals
- **Fix:** Wrap LangChain in adapter, use Butler contracts

### Persistence Layer
- **Violation:** service.py directly uses SQLAlchemy session (line 347)
- **Impact:** Business logic coupled to persistence details
- **Fix:** Use repository pattern or unit of work

## 8. Dead / Speculative Code

| File / Class / Function | Status | Classification | Action |
|---|---|---|---|---|
| services/orchestrator/graph.py | Partially implemented | SPECULATIVE | Gate behind feature flag, complete or remove |
| services/orchestrator/nodes/ | Partially implemented | SPECULATIVE | Gate behind feature flag, complete or remove |
| ButlerDeterministicExecutor (backends.py:45) | Used but overlapping | DUPLICATE | Consolidate with LangGraph tool node |
| DeterministicModeRouter (intake.py:61) | Always returns "agentic" | DEAD | Remove, hardcode or implement real router |
| HermesAgentBackend (backends.py:145) | Feature-flagged | DEPRECATED | Deprecate once LangGraph is stable |
| services/orchestrator/langgraph_runtime.py | Commented out (line 41) | DEAD | Remove after confirming unused |
| services/orchestrator/blender.py | Unclear usage | UNCLEAR | Audit usage, keep if used else remove |
| services/orchestrator/intake.py | Used but duplicate calls | DUPLICATE | Refactor to single call path |
| services/orchestrator/planner.py | Used but dual plan creation | DUPLICATE | Consolidate to single plan creation |

## 9. Required Invariants

1. **No L0/L1 tool can be exposed unless direct implementation exists.**
   - Current violation: 8 tools exposed without implementation
   - Fix: Add implementations or remove from tier map

2. **No L2/L3 tool can execute without approval/sandbox policy.**
   - Status: Appears enforced in executor
   - Test: Add regression test for policy enforcement

3. **A single chat request creates at most one workflow unless explicitly configured otherwise.**
   - Current violation: intake() and _intake_core() both create workflows
   - Fix: Consolidate to single workflow creation

4. **A single user turn is written once to session history with idempotency.**
   - Status: Appears correct in service.py line 557
   - Test: Add idempotency test

5. **Tool schema, risk tier, and approval mode must match the canonical registry.**
   - Current violation: Tier map lacks schemas, drift between registries
   - Fix: Consolidate to single canonical registry

6. **Provider fallback must be bounded and cannot retry dead local providers repeatedly inside one request.**
   - Status: Needs verification in runtime.py
   - Test: Add bounded retry test

7. **Compatibility layers cannot be authoritative unless explicitly configured.**
   - Current violation: Hermes tier map is authoritative
   - Fix: Make ButlerToolSpec canonical, Hermes as adapter

8. **Planner fallback must preserve safe behavior and must not hide model-runtime outages.**
   - Status: DeterministicModeRouter always returns "agentic"
   - Fix: Remove fallback or make it meaningful

9. **Environment snapshot failure must degrade without failing the request.**
   - Status: Has try/except in intake.py
   - Test: Add degradation test

10. **Metrics failure must never fail user execution, but must emit bounded error telemetry.**
   - Status: Needs verification
   - Test: Add metrics failure test

## 10. Refactor Plan

### Phase 1: Stop Runtime Crashes (CRITICAL)
**Goal:** Fix immediate crashes and duplicate execution

1. Remove duplicate intake.process() call in service.py line 416
2. Remove duplicate plan creation in service.py line 418
3. Fix circular dependency causing graph bypass
4. Add input_schema to get_time and web_search in tier map
5. Remove or add direct implementations for 8 ghost tools

**Risk:** Low - removing duplicate calls
**Files:** service.py, hermes_compiler.py

### Phase 2: Stop Ghost Tool Exposure (HIGH)
**Goal:** Ensure every exposed tool has executable binding

1. Consolidate tool registries to single canonical source
2. Make ButlerToolSpec the canonical registry
3. Hermes tier map becomes read-only adapter
4. Validate direct_implementations matches tool_specs at startup
5. Add startup invariant check: "All L0/L1 tools must have direct implementations"

**Risk:** Medium - registry consolidation
**Files:** hermes_compiler.py, tools.py, core/deps.py

### Phase 3: Collapse Duplicate Registries (HIGH)
**Goal:** One source of truth for tool definitions, risk, approval, runtime bindings

1. Create ToolRegistry as single canonical source
2. Migrate tier map data to ToolRegistry
3. Deprecate Hermes tier map
4. Remove direct_implementations dict, use ToolRegistry
5. Add ToolRegistry.get_executable_binding(tool_name) method

**Risk:** High - major refactoring
**Files:** domain/tools/tool_registry.py (new), hermes_compiler.py (deprecate), tools.py, core/deps.py

### Phase 4: Simplify Orchestrator Flow (HIGH)
**Goal:** Remove duplicate planner/runtime/graph paths

1. Choose LangGraph as single backend, deprecate Hermes
2. Remove BUTLER_AGENT_RUNTIME feature flag
3. Remove graph bypass logic in service.py
4. Either use graph fully or remove graph compilation
5. Consolidate intake() and _intake_core() into single path

**Risk:** High - architectural change
**Files:** service.py, backends.py (remove Hermes), graph.py (complete or remove)

### Phase 5: Hardening Tests (MEDIUM)
**Goal:** Add regression tests and release-gate checks

1. Add test for no duplicate intake.process() calls
2. Add test for single workflow per request
3. Add test for L0/L1 tool invariant
4. Add test for bounded provider fallback
5. Add test for metrics failure degradation
6. Add test for tool registry consistency

**Risk:** Low - test additions
**Files:** backend/tests/ (new tests)

## 11. Exact Code Changes

### Change 1: Remove duplicate intake.process() call
**File:** backend/services/orchestrator/service.py
**Function:** intake() (line 397)
**Change:** Remove lines 416-422 (first intake.process() call)
**Reason:** intake.process() is called again in _intake_core() line 559
**Risk:** Low - removing duplicate call
**Test:** Add test verifying intake.process() called exactly once per request

```python
# DELETE these lines (416-422):
intake_result = await self._intake.process(envelope)

plan = await self._create_plan(
    envelope=envelope,
    intake_result=intake_result,
    candidates=[],
)
```

### Change 2: Remove duplicate plan creation
**File:** backend/services/orchestrator/service.py
**Function:** intake() (line 397)
**Change:** Remove lines 418-422 (first _create_plan() call)
**Reason:** Plan created again in _intake_core() line 588
**Risk:** Low - removing duplicate call
**Test:** Add test verifying plan created exactly once per request

### Change 3: Add input_schema to get_time in tier map
**File:** backend/domain/tools/hermes_compiler.py
**Function:** _HERMES_TOOL_TIER_MAP (line 137)
**Change:** Add input_schema to get_time entry
**Reason:** Schema fallback now uses tier_config.get("input_schema", {})
**Risk:** Low - adding schema
**Test:** Add test for get_time schema validation

```python
"get_time": {
    "tier": RiskTier.L0,
    "owner": "tools",
    "sandbox": "none",
    "side_effects": [],
    "description": "Get the current date and time.",
    "input_schema": {
        "type": "object",
        "properties": {
            "timezone": {"type": "string"},
            "input": {"type": "string"}
        }
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "timezone": {"type": "string"},
            "iso": {"type": "string"},
            "date": {"type": "string"},
            "time": {"type": "string"},
            "weekday": {"type": "string"}
        }
    }
},
```

### Change 4: Remove graph bypass logic
**File:** backend/services/orchestrator/service.py
**Function:** intake() (line 397)
**Change:** Remove lines 430-451 (bypass check and return)
**Reason:** Bypass causes duplicate execution and unclear flow
**Risk:** Medium - may break agentic mode temporarily
**Test:** Add test for graph execution path

```python
# DELETE these lines (430-451):
# Bypass graph entirely for agentic mode - use direct _intake_core
try:
    logger.info(
        "orchestrator_checking_execution_mode",
        session_id=envelope.session_id,
        execution_mode=plan.execution_mode.value,
        is_agentic=plan.execution_mode == ExecutionMode.AGENTIC,
    )
    if plan.execution_mode == ExecutionMode.AGENTIC:
        logger.info(
            "orchestrator_bypassing_graph_for_agentic",
            session_id=envelope.session_id,
            execution_mode="agentic",
        )
        return await self._intake_core(envelope)
except Exception as exc:
    logger.exception(
        "orchestrator_bypass_check_failed",
        session_id=envelope.session_id,
        error=str(exc),
    )
    # Continue to graph execution as fallback
```

### Change 5: Add startup invariant check for L0/L1 tools
**File:** backend/core/deps.py
**Function:** get_orchestrator_service() or new startup check
**Change:** Add validation that all L0/L1 tools have direct implementations
**Reason:** Prevents ghost tool exposure
**Risk:** Low - validation only
**Test:** Add test for invariant check

```python
# Add in get_orchestrator_service() or new function:
def _validate_l0_l1_tools_have_implementations(
    tool_specs: list[ButlerToolSpec],
    direct_implementations: dict[str, Any],
) -> None:
    """Validate that all L0/L1 tools have direct implementations."""
    for spec in tool_specs:
        if spec.risk_tier in (RiskTier.L0, RiskTier.L1):
            if spec.name not in direct_implementations:
                raise RuntimeError(
                    f"L0/L1 tool '{spec.name}' is exposed but has no direct implementation. "
                    f"Either add implementation or remove from tier map."
                )
```

## 12. Final Recommendation

### Minimal Safe Patch (Do First)

**File:** backend/services/orchestrator/service.py

**Changes:**
1. Remove duplicate intake.process() call (line 416)
2. Remove duplicate plan creation (line 418)
3. Add input_schema to get_time in tier map
4. Add startup invariant check for L0/L1 tools

**Risk:** Low
**Impact:** Stops duplicate execution, prevents ghost tool exposure
**Time:** 1-2 hours

### Ideal Architecture Cleanup

1. **Consolidate tool registries** - Make ButlerToolSpec canonical, Hermes as adapter
2. **Choose single backend** - Deprecate Hermes, standardize on LangGraph
3. **Remove graph bypass** - Fix circular dependency properly
4. **Consolidate intake paths** - Single intake() method without _intake_core() split
5. **Add invariant tests** - Release-gate checks for tool exposure, single workflow, etc.

**Risk:** High (architectural changes)
**Impact:** Clean, maintainable, observable runtime
**Time:** 2-3 weeks

### Next File to Inspect

**backend/services/orchestrator/nodes/** - Investigate whether the graph nodes are actually used or if this is dead code from the bypass logic. The graph is compiled but bypassed for agentic mode, suggesting these nodes may be speculative or incomplete.
