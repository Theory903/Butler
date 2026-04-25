# butler_runtime Migration Plan (Phase 14)

## Objective
Migrate from old butler_runtime package to new domain/runtime/ module.

## Current State
- Old package: `butler_runtime/` (deprecated, mixed concerns)
- New module: `domain/runtime/` (canonical runtime contracts)

## Migration Steps

### Step 1: Update imports
- Replace `from butler_runtime import RuntimeContext` with `from domain.runtime import RuntimeContext`
- Replace `from butler_runtime import ToolResultEnvelope` with `from domain.runtime import ToolResultEnvelope`
- Replace `from butler_runtime import ResponseValidator` with `from domain.runtime import ResponseValidator`
- Replace `from butler_runtime import FinalResponseComposer` with `from domain.runtime import FinalResponseComposer`

### Step 2: Update type references
- Replace `butler_runtime.RuntimeContext` with `domain.runtime.RuntimeContext`
- Replace `butler_runtime.ToolResultEnvelope` with `domain.runtime.ToolResultEnvelope`

### Step 3: Remove old package
- Delete `butler_runtime/` directory
- Update requirements.txt to remove butler_runtime dependency

### Step 4: Update tests
- Update test imports
- Update type annotations

## Validation
- All butler_runtime imports removed
- All imports use domain.runtime
- Tests pass
