# CI Safety Check Allowlist

This document documents the allowlist for CI safety checks. These are the patterns that are explicitly allowed to bypass certain safety checks, along with the rationale for each exception.

## Redis Key Allowlist

### Allowed Locations
- `infrastructure/redis/` - Redis abstraction layer
- `core/redis/` - Core Redis utilities

### Rationale
The Redis abstraction layer and core utilities are the designated locations for raw Redis operations. All other code must use these abstractions to ensure proper namespacing and tenant isolation.

## Subprocess Allowlist

### Allowed Locations
- `services/workspace/` - Workspace service (sandbox execution)
- `integrations/` - External integrations

### Rationale
The workspace service requires subprocess execution for sandbox operations. External integrations may need subprocess calls for third-party tool integration. All other subprocess usage is blocked to prevent arbitrary code execution.

## Provider SDK Allowlist

### Allowed Locations
- `services/ml/` - ML Runtime service
- `integrations/` - External integrations

### Rationale
The ML Runtime service is the designated location for direct provider SDK usage (OpenAI, Anthropic, etc.). All other code must use the ML Runtime abstraction to ensure proper routing, fallback, and health checking.

## Qdrant/Neo4j Allowlist

### Allowed Locations
- `infrastructure/qdrant/` - Qdrant abstraction layer
- `infrastructure/neo4j/` - Neo4j abstraction layer

### Rationale
The infrastructure layers are the designated locations for direct vector store and graph database operations. All other code must use these abstractions to ensure proper tenant scoping and filtering.

## Raw Logger Allowlist

### Allowed Locations
- `core/tenant_aware_logger.py` - Tenant-aware logger implementation
- `tests/` - Test files

### Rationale
The tenant-aware logger is the designated location for raw logging module usage. Test files are exempt for testing purposes. All production code must use the tenant-aware logger to ensure proper tenant context and structured logging.

## Response Leak Allowlist

### Allowed Locations
- `ResponseValidator` - Response validation utility

### Rationale
The ResponseValidator is the designated location for raw response handling. All API routes must use ResponseValidator to ensure proper response validation and prevent response leaks.

## Direct Database Access Allowlist

### Allowed Locations
- `infrastructure/` - Database abstraction layer
- `tests/` - Test files

### Rationale
The infrastructure layer is the designated location for direct SQLAlchemy session usage. Test files are exempt for testing purposes. All production code must use the infrastructure layer to ensure proper session management, tenant scoping, and transaction handling.

## Hardcoded Secrets Allowlist

### Allowed Patterns
- None - hardcoded secrets are never allowed in production code

### Rationale
Hardcoded secrets (API keys, tokens, passwords) must never be committed to the repository. All secrets must be loaded from environment variables or secret management systems. Test files may use dummy/test values that are clearly marked as such.

## Tool Bypass Allowlist

### Allowed Locations
- `services/tools/executor.py` - ToolExecutor implementation
- `domain/tools/hermeses_compiler.py` - Hermes compiler

### Rationale
The ToolExecutor is the designated location for direct tool dispatch. The Hermes compiler requires direct Hermes API calls for compilation. All other code must use ToolExecutor.execute_canonical() for tool execution.

## Requesting Allowlist Exceptions

To add a new exception to this allowlist:

1. Document the specific pattern being allowed
2. Provide a clear rationale for why the exception is necessary
3. Ensure the exception is scoped to the smallest possible location
4. Add corresponding CI check exemptions with `grep -v` patterns
5. Update this document with the new exception

## Audit Schedule

Review this allowlist quarterly to:
- Remove obsolete exceptions
- Ensure exceptions are still justified
- Verify CI check patterns are up to date
