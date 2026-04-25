# Redis Abstraction Design

This document defines the Redis abstraction design for Butler, ensuring that all Redis operations use tenant-scoped abstractions instead of raw key construction.

## Overview

**Goal:** Ensure all Redis operations use tenant-scoped abstractions
**Scope:** Cache, Lock, Rate Limit, Artifact, Sandbox, Workflow abstractions
**Status:** Contract-only - implementation pending

## TenantNamespace

### Namespace Contract
```python
@dataclass(frozen=True)
class TenantNamespace:
    tenant_id: UUID
    account_id: UUID
    session_id: str | None = None

    def prefix(self, resource: str) -> str:
        """Generate tenant-scoped Redis key prefix."""
        parts = ["tenant", str(self.tenant_id), "account", str(self.account_id)]
        if self.session_id:
            parts.append("session")
            parts.append(self.session_id)
        parts.append(resource)
        return ":".join(parts)
```

### Usage
All Redis operations must use TenantNamespace to generate keys:
```python
namespace = TenantNamespace(tenant_id=..., account_id=...)
cache_key = namespace.prefix("cache")
lock_key = namespace.prefix("lock")
rate_limit_key = namespace.prefix("rate_limit")
```

## Abstractions

### Cache Abstraction
```python
class CacheAbstraction(Protocol):
    async def get(self, namespace: TenantNamespace, key: str) -> Any | None:
        ...
    async def set(self, namespace: TenantNamespace, key: str, value: Any, ttl: int) -> None:
        ...
    async def delete(self, namespace: TenantNamespace, key: str) -> None:
        ...
    async def exists(self, namespace: TenantNamespace, key: str) -> bool:
        ...
```

### Lock Abstraction
```python
class LockAbstraction(Protocol):
    async def acquire(self, namespace: TenantNamespace, lock_name: str, ttl: int) -> bool:
        ...
    async def release(self, namespace: TenantNamespace, lock_name: str) -> None:
        ...
    async def is_locked(self, namespace: TenantNamespace, lock_name: str) -> bool:
        ...
```

### Rate Limit Abstraction
```python
class RateLimitAbstraction(Protocol):
    async def check(self, namespace: TenantNamespace, limit_id: str, limit: int, window: int) -> bool:
        ...
    async def increment(self, namespace: TenantNamespace, limit_id: str) -> int:
        ...
    async def reset(self, namespace: TenantNamespace, limit_id: str) -> None:
        ...
```

### Artifact Abstraction
```python
class ArtifactAbstraction(Protocol):
    async def store(self, namespace: TenantNamespace, artifact_id: str, data: bytes, ttl: int) -> None:
        ...
    async def retrieve(self, namespace: TenantNamespace, artifact_id: str) -> bytes | None:
        ...
    async def delete(self, namespace: TenantNamespace, artifact_id: str) -> None:
        ...
    async def list(self, namespace: TenantNamespace) -> list[str]:
        ...
```

### Sandbox Abstraction
```python
class SandboxAbstraction(Protocol):
    async def create(self, namespace: TenantNamespace, sandbox_id: str, config: dict) -> str:
        ...
    async def destroy(self, namespace: TenantNamespace, sandbox_id: str) -> None:
        ...
    async def get_status(self, namespace: TenantNamespace, sandbox_id: str) -> SandboxStatus:
        ...
```

### Workflow Abstraction
```python
class WorkflowAbstraction(Protocol):
    async def start(self, namespace: TenantNamespace, workflow_id: str, input: dict) -> str:
        ...
    async def get_status(self, namespace: TenantNamespace, execution_id: str) -> WorkflowStatus:
        ...
    async def cancel(self, namespace: TenantNamespace, execution_id: str) -> None:
        ...
```

## Implementation Status

### Completed
- TenantNamespace contract exists (domain/tenant/namespace.py)
- CI check for raw Redis key construction

### Pending
- Refactor 37 Redis key files
- Cache abstraction enforced
- Lock abstraction enforced
- Rate limit abstraction enforced
- Artifact abstraction enforced
- Sandbox abstraction enforced
- Workflow abstraction enforced
- Namespace isolation tests

## Migration Strategy

### Phase 1: Add Abstractions
- Define abstraction protocols
- Implement abstraction classes
- Add TenantNamespace integration

### Phase 2: Refactor New Code
- All new Redis operations use abstractions
- All new Redis operations use TenantNamespace
- No raw Redis key construction in new code

### Phase 3: Refactor Existing Code
- Update 37 files to use abstractions
- Update 37 files to use TenantNamespace
- Remove raw Redis key construction

### Phase 4: Remove Direct Redis Access
- Remove direct Redis client usage
- Remove direct key construction
- Ensure all operations go through abstractions

## Testing Strategy

### Unit Tests
- Test TenantNamespace key generation
- Test cache abstraction methods
- Test lock abstraction methods
- Test rate limit abstraction methods
- Test artifact abstraction methods
- Test sandbox abstraction methods
- Test workflow abstraction methods

### Integration Tests
- Test abstraction integration with Redis
- Test namespace isolation
- Test concurrent access
- Test TTL handling

### Namespace Isolation Tests
- Test tenant isolation
- Test account isolation
- Test session isolation
- Test cross-namespace access blocking

## Monitoring

### Metrics
- Abstraction usage per type
- Namespace usage per tenant
- Cache hit/miss rates
- Lock acquisition times
- Rate limit enforcement counts

### Logging
- All abstraction operations logged
- All namespace usage logged
- All TTL expirations logged
- All errors logged

### Alerts
- High cache miss rate
- Lock timeout
- Rate limit exceeded
- Abstraction failure

## Failure Modes

### Namespace Missing
- Return error to caller
- Log as error
- Require namespace for all operations

### Redis Unavailable
- Return error to caller
- Log as critical event
- Alert operations team
- Implement fallback if configured

### TTL Expired
- Return None for cache get
- Return False for lock check
- Return 0 for rate limit check
- Log as info event

## Compliance

### Multi-Tenancy
- All operations scoped to tenant
- All operations scoped to account
- No cross-tenant access possible
- No cross-account access possible

### Data Isolation
- Tenant data isolated
- Account data isolated
- Session data isolated
- No data leakage

## Security

### Key Construction
- Keys constructed by TenantNamespace
- No manual key construction allowed
- Keys validated before use
- Keys logged for audit

### Access Control
- Namespace validated against context
- Unauthorized access blocked
- Security event logged
- Admin notified
