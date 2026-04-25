# butler_runtime Migration Status

This document tracks the migration status from legacy `butler_runtime` to the canonical Butler Tool Runtime.

## Migration Overview

**Source:** `butler_runtime/` (legacy runtime)
**Target:** Canonical runtime integrated into `services/tools/`, `domain/tools/`, `services/ml/`

**Migration Strategy:** Incremental migration with import guards and deprecation warnings

## Module Classification

### Category A: Migrate to Canonical Runtime (Priority 1)

Modules that provide core runtime functionality and should be migrated first.

| Module | Target Location | Status | Notes |
|--------|----------------|--------|-------|
| `butler_runtime/agent.py` | `services/orchestrator/` | Not started | Agent orchestration logic |
| `butler_runtime/executor.py` | `services/tools/executor.py` | Complete | Already canonical |
| `butler_runtime/tools/` | `domain/tools/` | Partial | Tool specs migrated, adapters pending |

### Category B: Adapt and Integrate (Priority 2)

Modules that provide useful functionality but need adaptation.

| Module | Target Location | Status | Notes |
|--------|----------------|--------|-------|
| `butler_runtime/context.py` | `domain/runtime/context.py` | Contract-only | RuntimeContext exists, integration pending |
| `butler_runtime/memory.py` | `services/memory/` | Contract-only | Memory service exists, integration pending |
| `butler_runtime/ml.py` | `services/ml/runtime.py` | Contract-only | ML runtime exists, integration pending |

### Category C: Archive as Legacy (Priority 3)

Modules that are obsolete or replaced by new patterns.

| Module | Action | Status | Notes |
|--------|--------|--------|-------|
| `butler_runtime/legacy/` | Archive | Not started | Legacy compatibility layer |
| `butler_runtime/deprecated/` | Delete | Not started | Deprecated functionality |

### Category D: Test-Only (Priority 4)

Modules that are only used in tests.

| Module | Action | Status | Notes |
|--------|--------|--------|-------|
| `butler_runtime/test_utils/` | Keep test-only | Not started | Test utilities |
| `butler_runtime/fixtures/` | Keep test-only | Not started | Test fixtures |

## Migration Steps

### Step 1: Import Guards
Add import guards to prevent new imports of legacy modules.

```python
# butler_runtime/__init__.py
import warnings
warnings.warn(
    "butler_runtime is deprecated. Use canonical runtime from services/tools/ instead.",
    DeprecationWarning,
    stacklevel=2
)
```

### Step 2: Deprecation Warnings
Add deprecation warnings to legacy module functions.

### Step 3: Migrate Category A Modules
Migrate core runtime modules to canonical locations.

### Step 4: Adapt Category B Modules
Adapt useful modules to integrate with canonical runtime.

### Step 5: Archive Category C Modules
Archive obsolete modules to `archive/legacy/`.

### Step 6: Mark Category D Modules
Mark test-only modules with `# test-only` comments.

### Step 7: Update Imports
Update all imports to use canonical locations.

### Step 8: Remove Legacy
Remove `butler_runtime/` after deprecation period.

## Current Status

- **Migration Plan:** Complete (`docs/butler_runtime_migration.md`)
- **Module Classification:** Not started
- **Import Guards:** Not started
- **Deprecation Warnings:** Not started
- **Category A Migration:** Partial (executor complete)
- **Category B Adaptation:** Contract-only
- **Category C Archive:** Not started
- **Category D Marking:** Not started
- **Import Updates:** Not started
- **Legacy Removal:** Not started

## Next Steps

1. Complete module classification
2. Add import guards to `butler_runtime/__init__.py`
3. Migrate remaining Category A modules
4. Adapt Category B modules
5. Archive Category C modules
6. Mark Category D modules
7. Update all imports
8. Remove legacy after deprecation period

## Success Criteria

- No new imports of `butler_runtime`
- All runtime functionality available in canonical locations
- Legacy modules either migrated, archived, or marked test-only
- All tests pass with canonical runtime
- Legacy runtime removed after deprecation period
