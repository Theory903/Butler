# Durable Workflow Strategy

This document defines the durable workflow strategy for Butler, ensuring reliable execution of long-running operations with proper durability and recovery.

## Overview

**Goal:** Ensure all long-running operations use durable workflows with proper recovery
**Scope:** Orchestrator executor, subagent runtime, Temporal integration
**Status:** Contract-only - implementation pending

## Workflow Contracts

### Workflow Definition
```python
@dataclass(frozen=True)
class WorkflowDefinition:
    name: str
    version: str
    input_schema: dict
    output_schema: dict
    timeout_seconds: int
    retry_policy: RetryPolicy
    idempotency_key: str | None = None
```

### Workflow Execution
```python
@dataclass(frozen=True)
class WorkflowExecution:
    execution_id: str
    workflow_name: str
    workflow_version: str
    input_data: dict
    status: WorkflowStatus  # RUNNING, COMPLETED, FAILED, CANCELLED
    start_time: datetime
    end_time: datetime | None = None
    error: str | None = None
    output_data: dict | None = None
```

## Durability Strategy

### Temporal Integration
- Primary durability: Temporal workflow engine
- Fallback: DB-backed durability
- Task leasing for distributed execution
- Heartbeat for liveness detection

### DB-Backed Fallback
- workflow_runs table for execution state
- workflow_tasks table for task state
- workflow_events table for event history
- Retry with exponential backoff

### Task Leasing
- Lease duration: 30 seconds
- Lease renewal: Every 15 seconds
- Lease expiration: Task becomes available for other workers
- Lease conflict: Task is re-queued

### Heartbeat
- Heartbeat interval: 10 seconds
- Heartbeat timeout: 30 seconds
- Heartbeat failure: Task marked as failed
- Heartbeat recovery: Task re-queued

## Idempotency

### Idempotency Keys
- All workflows accept idempotency_key
- Idempotency keys are unique per workflow
- Duplicate requests return existing execution
- Idempotency keys expire after 24 hours

### Idempotency Enforcement
- Check for existing execution before starting
- Return existing execution if found
- Update existing execution if in progress
- Create new execution if not found

## Outbox Pattern

### Outbox Table
- outbox_events table for events to be published
- Event status: PENDING, PUBLISHED, FAILED
- Event retry count
- Event last attempt timestamp

### Outbox Processing
- Background worker processes outbox events
- Events published to message queue
- Events marked as published on success
- Events retried with exponential backoff

## Dead Letter Queue

### DLQ Table
- dead_letter_queue table for failed events
- Event payload
- Error message
- Retry count
- Original timestamp

### DLQ Processing
- Failed events moved to DLQ
- DLQ events inspected manually
- DLQ events can be re-queued
- DLQ events retained for 30 days

## Recovery Worker

### Recovery Logic
- Scan for timed-out tasks
- Re-queue timed-out tasks
- Scan for failed workflows
- Retry failed workflows if retry policy allows

### Recovery Schedule
- Recovery runs every 60 seconds
- Recovery processes 100 tasks at a time
- Recovery logs all actions
- Recovery alerts on critical failures

## Implementation Status

### Completed
- Durable workflow contracts exist (domain/workflow/durable.py)

### Pending
- Temporal integrated
- DB-backed durability fallback
- Task leasing implemented
- Heartbeat implemented
- Idempotency keys enforced
- Outbox pattern implemented
- DLQ implemented
- Recovery worker exists
- Orchestrator executor uses workflows
- Subagent runtime uses workflows
- Workflow durability tests

## Migration Strategy

### Phase 1: Add Temporal
- Add Temporal client
- Add Temporal worker
- Define workflow definitions
- Implement workflow activities

### Phase 2: Add DB Fallback
- Create workflow_runs table
- Create workflow_tasks table
- Create workflow_events table
- Implement DB-backed durability

### Phase 3: Add Leasing and Heartbeat
- Implement task leasing
- Implement heartbeat
- Implement lease renewal
- Implement heartbeat timeout

### Phase 4: Add Idempotency
- Add idempotency_key to workflows
- Implement idempotency check
- Implement idempotency enforcement
- Add idempotency tests

### Phase 5: Add Outbox and DLQ
- Create outbox_events table
- Create dead_letter_queue table
- Implement outbox processor
- Implement DLQ processor

### Phase 6: Add Recovery Worker
- Implement recovery worker
- Implement timeout detection
- Implement failure retry
- Add recovery monitoring

### Phase 7: Integrate with Services
- Update orchestrator executor to use workflows
- Update subagent runtime to use workflows
- Update long-running operations to use workflows

## Testing Strategy

### Unit Tests
- Test workflow definition
- Test workflow execution
- Test task leasing
- Test heartbeat
- Test idempotency
- Test outbox pattern
- Test DLQ

### Integration Tests
- Test Temporal integration
- Test DB fallback
- Test recovery worker
- Test end-to-end workflows

### Workflow Durability Tests
- Test workflow persistence
- Test workflow recovery
- Test task timeout
- Test worker failure
- Test database failure

## Monitoring

### Metrics
- Workflow execution count
- Workflow success rate
- Workflow failure rate
- Workflow latency (p50, p95, p99)
- Task lease rate
- Heartbeat failure rate
- Outbox event rate
- DLQ event rate

### Logging
- All workflow executions logged
- All task transitions logged
- All lease acquisitions logged
- All heartbeat failures logged
- All outbox events logged
- All DLQ events logged

### Alerts
- High workflow failure rate
- High heartbeat failure rate
- High outbox backlog
- High DLQ rate
- Recovery worker failure

## Failure Modes

### Temporal Unavailable
- Fall back to DB-backed durability
- Log as critical event
- Alert operations team
- Continue processing with DB

### Database Unavailable
- Buffer workflow state in memory
- Log as critical event
- Alert operations team
- Retry with exponential backoff

### Task Timeout
- Mark task as failed
- Re-queue task for retry
- Log as warning
- Increment retry count

### Worker Failure
- Release task lease
- Re-queue task
- Log as error
- Recovery worker picks up task

## Compliance

### Durability
- All workflows persisted
- All task state persisted
- All events persisted
- Recovery guaranteed

### Observability
- All workflow executions logged
- All task transitions logged
- Metrics exported to monitoring
- Audit trail maintained
