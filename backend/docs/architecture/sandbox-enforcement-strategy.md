# Sandbox Enforcement Strategy

This document defines the sandbox enforcement strategy for Butler, ensuring that all subprocess execution is safely isolated with proper filesystem and resource controls.

## Overview

**Goal:** Ensure all subprocess execution is sandboxed with proper isolation
**Scope:** Local Docker provider, production providers, filesystem policies, denylists
**Status**: Contract-only - implementation pending

## Sandbox Architecture

### Sandbox Providers
- **Local Docker:** Docker containers for local development
- **Production Providers:** Firecracker, gVisor, or similar for production
- **Fallback:** Chroot + seccomp for environments without VM support

### Sandbox Manager
```python
class SandboxManager(Protocol):
    async def create(self, config: SandboxConfig) -> str:
        """Create a sandbox and return sandbox_id"""
        ...
    async def execute(self, sandbox_id: str, command: list[str]) -> SandboxResult:
        """Execute a command in the sandbox"""
        ...
    async def destroy(self, sandbox_id: str) -> None:
        """Destroy a sandbox"""
        ...
    async def get_status(self, sandbox_id: str) -> SandboxStatus:
        """Get sandbox status"""
        ...
```

## Enforcement Rules

### TTL Enforcement
- Maximum sandbox lifetime: 30 minutes
- TTL enforced by SandboxManager
- TTL warning at 25 minutes
- TTL expiration triggers automatic cleanup

### Cleanup Enforcement
- Automatic cleanup on TTL expiration
- Automatic cleanup on process completion
- Manual cleanup on request
- Cleanup retries: 3 times with exponential backoff

### Artifact Export
- Artifacts must be explicitly exported
- Export requires approval for large artifacts (>10MB)
- Export destination validated against policy
- Export logged for audit

## Filesystem Policy

### Workspace-Root Policy
- Default: Read-only access to workspace root
- Explicit: Write access requires approval
- Blocked: No access to host root
- Blocked: No access to .git/

### Denylist Enforcement
- **.env:** Blocked - environment variables
- **.key:** Blocked - private keys
- **.secret:** Blocked - secrets
- **.git/:** Blocked - git metadata
- **/root:** Blocked - host root
- **SSH keys:** Blocked - SSH credentials
- **Cloud config:** Blocked - cloud credentials

### Allowlist
- **Workspace directory:** Read-only by default
- **Artifact directory:** Write-only for artifacts
- **Temp directory:** Write-only for temporary files

## Subprocess Refactoring

### Refactor Strategy
- Replace 16 subprocess files with sandbox calls
- Use SandboxManager for all subprocess execution
- Remove direct subprocess.Popen usage
- Remove direct os.system usage
- Remove direct os.exec* usage

### Refactor Pattern
```python
# Old
result = subprocess.run(command, capture_output=True)

# New
sandbox_id = await sandbox_manager.create(config)
result = await sandbox_manager.execute(sandbox_id, command)
await sandbox_manager.destroy(sandbox_id)
```

## Implementation Status

### Completed
- CI check for subprocess usage
- SandboxManager contract exists

### Pending
- Local Docker provider
- Production providers
- TTL enforced
- Cleanup enforced
- Artifact export explicit
- Workspace-root filesystem policy
- Denylist enforced
- Refactor 16 subprocess files
- .env blocked
- *.key blocked
- *.secret blocked
- .git/ blocked
- Host root blocked
- SSH keys blocked
- Cloud config blocked
- Sandbox tests

## Migration Strategy

### Phase 1: Add SandboxManager
- Implement SandboxManager interface
- Implement local Docker provider
- Implement filesystem policy
- Implement denylist

### Phase 2: Add Production Providers
- Add Firecracker provider
- Add gVisor provider
- Add provider selection logic
- Add provider fallback logic

### Phase 3: Add Enforcement
- Implement TTL enforcement
- Implement cleanup enforcement
- Implement artifact export validation
- Implement filesystem policy enforcement

### Phase 4: Refactor Subprocess Usage
- Update 16 files to use SandboxManager
- Remove direct subprocess usage
- Remove direct os.system usage
- Remove direct os.exec* usage

### Phase 5: Add Tests
- Add sandbox creation tests
- Add sandbox execution tests
- Add sandbox cleanup tests
- Add filesystem policy tests
- Add denylist tests

## Testing Strategy

### Unit Tests
- Test SandboxManager interface
- Test TTL enforcement
- Test cleanup enforcement
- Test artifact export validation
- Test filesystem policy
- Test denylist enforcement

### Integration Tests
- Test local Docker provider
- Test production providers
- Test provider fallback
- Test end-to-end sandbox usage

### Sandbox Tests
- Test sandbox isolation
- Test resource limits
- Test network isolation
- Test filesystem isolation

## Monitoring

### Metrics
- Sandbox creation count
- Sandbox execution count
- Sandbox destruction count
- Sandbox lifetime (p50, p95, p99)
- TTL expiration count
- Cleanup failure count

### Logging
- All sandbox creations logged
- All sandbox executions logged
- All sandbox destructions logged
- All TTL expirations logged
- All cleanup failures logged
- All denylist violations logged

### Alerts
- High TTL expiration rate
- High cleanup failure rate
- Denylist violation
- Sandbox creation failure
- Sandbox execution failure

## Failure Modes

### Sandbox Creation Failure
- Return error to caller
- Log as error
- Alert operations team
- Do not retry automatically

### Sandbox Execution Failure
- Return error to caller
- Log as error
- Include command output in error
- Do not retry automatically

### Cleanup Failure
- Log as warning
- Retry with exponential backoff
- Alert operations team after 3 failures
- Mark sandbox for manual cleanup

### Denylist Violation
- Block the operation
- Log as security event
- Alert operations team
- Include in audit trail

## Compliance

### Security
- All subprocess execution sandboxed
- Filesystem access controlled
- Denylist enforced
- Audit trail maintained

### Multi-Tenancy
- Sandboxes scoped to tenant
- Sandboxes scoped to account
- No cross-tenant access
- No cross-account access

## Security

### Isolation
- Process isolation via containers/VMs
- Filesystem isolation via bind mounts
- Network isolation via network namespaces
- Resource isolation via cgroups

### Resource Limits
- CPU limit: 2 cores
- Memory limit: 4GB
- Disk limit: 10GB
- Network limit: No external access

### Access Control
- Read-only workspace by default
- Write access requires approval
- Denylist enforced
- Allowlist enforced
