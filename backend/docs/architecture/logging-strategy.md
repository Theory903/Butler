# Logging Strategy

This document defines the logging strategy for Butler, ensuring tenant-aware structured logging with proper redaction and sampling.

## Overview

**Goal:** Ensure all logging is tenant-aware, structured, and safe
**Scope:** Core logging, observability, service adapters, all application code
**Status:** Contract-only - implementation pending

## TenantAwareLogger

### Logger Contract
```python
class TenantAwareLogger:
    def __init__(self, tenant_id: UUID, account_id: UUID, session_id: str | None = None):
        self.tenant_id = tenant_id
        self.account_id = account_id
        self.session_id = session_id

    def info(self, event: str, **kwargs):
        ...

    def warning(self, event: str, **kwargs):
        ...

    def error(self, event: str, **kwargs):
        ...

    def debug(self, event: str, **kwargs):
        ...
```

### Usage
All logging must use TenantAwareLogger:
```python
logger = TenantAwareLogger(tenant_id=..., account_id=..., session_id=...)
logger.info("tool_execution", tool_name="search", status="success")
```

## Logging Rules

### No Raw IDs in Logs
- UUIDs must be truncated or hashed
- Use short IDs for debugging
- Log full IDs only in debug mode

### No Secrets in Logs
- API keys must never be logged
- Tokens must never be logged
- Passwords must never be logged
- Sensitive data must be redacted

### Health Logs Deduplicated
- Health check logs sampled
- Repeated health logs deduplicated
- Only log health state changes

### Success Logs Sampled
- Success logs sampled at 10%
- Error logs never sampled
- Warning logs sampled at 50%

### Errors Logged Safely
- Error context logged
- Sensitive data redacted
- Stack traces logged only in debug mode

## Implementation Status

### Completed
- TenantAwareLogger exists (core/tenant_aware_logger.py)
- CI check for raw logger usage

### Pending
- Replace raw logging (173 files)
- Core logging updated
- Observability updated
- Service adapters updated
- No raw IDs in logs
- No secrets in logs
- Health logs deduplicated
- Success logs sampled
- Errors logged safely
- Logging tests

## Migration Strategy

### Phase 1: Add TenantAwareLogger
- Ensure TenantAwareLogger is available
- Add context propagation
- Add redaction utilities

### Phase 2: Update Core Logging
- Update core/ to use TenantAwareLogger
- Update infrastructure/ to use TenantAwareLogger
- Update services/ to use TenantAwareLogger

### Phase 3: Update Application Code
- Update 173 files to use TenantAwareLogger
- Remove raw logging module usage
- Add context to all log statements

### Phase 4: Remove Raw Logging
- Remove direct logger usage
- Remove print statements
- Ensure all logging goes through TenantAwareLogger

## Testing Strategy

### Unit Tests
- Test TenantAwareLogger initialization
- Test logging with context
- Test redaction logic
- Test sampling logic

### Integration Tests
- Test logging integration with observability
- Test context propagation
- Test log aggregation
- Test log search

### Logging Tests
- Test no raw IDs in logs
- Test no secrets in logs
- Test health log deduplication
- Test success log sampling
- Test error logging safety

## Monitoring

### Metrics
- Log volume per tenant
- Log volume per level
- Redaction rate
- Sampling rate
- Error rate

### Logging
- All logs structured
- All logs tenant-scoped
- All logs have context
- All logs have correlation IDs

### Alerts
- High error rate
- High warning rate
- Logging system failure
- Redaction failure

## Failure Modes

### Logger Unavailable
- Buffer logs in memory
- Log to stderr as fallback
- Alert operations team
- Do not block application

### Context Missing
- Use default context
- Log warning about missing context
- Continue logging
- Alert operations team

### Redaction Failure
- Log redaction failure
- Continue with partial redaction
- Alert operations team
- Do not block application

## Compliance

### GDPR
- No personal data in logs
- Right to erasure for logs
- Log retention policies
- Log access controls

### SOC 2
- Audit trail maintained
- Log tamper detection
- Log retention policies
- Log access controls

## Observability

### OpenTelemetry Integration
- Logs exported to OpenTelemetry
- Logs correlated with traces
- Logs correlated with metrics
- Logs exported to monitoring system

### Structured Logging
- All logs structured as JSON
- All logs have consistent schema
- All logs have timestamp
- All logs have tenant_id and account_id

### Log Aggregation
- Logs aggregated by tenant
- Logs aggregated by service
- Logs aggregated by level
- Logs searchable
