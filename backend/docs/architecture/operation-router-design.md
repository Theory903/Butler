# Operation Router Design

This document defines the Operation Router design for Butler, ensuring that all operations are routed through a centralized router for governance and policy enforcement.

## Overview

**Goal:** Centralize all operation routing through a single router for consistent governance
**Scope:** Orchestrator, Planner, Executor, Tool Executor, Memory Service, ML Runtime, API routes
**Status:** Contract-only - implementation pending

## Router Architecture

### OperationRouter Contract
```python
@dataclass(frozen=True)
class OperationRequest:
    operation_type: OperationType  # TOOL, MEMORY, ML, WORKFLOW
    operation_name: str
    input_data: dict
    context: RuntimeContext
    approval_id: str | None = None
    idempotency_key: str | None = None

@dataclass(frozen=True)
class OperationResponse:
    operation_type: OperationType
    operation_name: str
    status: OperationStatus  # SUCCESS, FAILED, PENDING
    data: dict
    error: str | None = None
    latency_ms: int | None = None
```

### Router Methods
- `route(request: OperationRequest) -> OperationResponse` - Route operation to appropriate handler
- `get_handler(operation_type: OperationType) -> OperationHandler` - Get handler for operation type
- `register_handler(operation_type: OperationType, handler: OperationHandler)` - Register a handler
- `get_routing_stats() -> RoutingStats` - Get routing statistics

## Routing Logic

### Operation Types
- **TOOL:** Tool execution operations
- **MEMORY:** Memory read/write operations
- **ML:** ML model inference operations
- **WORKFLOW:** Workflow execution operations

### Routing Decision
```python
def route(request: OperationRequest) -> OperationResponse:
    # Validate request
    validate_request(request)
    
    # Get handler for operation type
    handler = get_handler(request.operation_type)
    
    # Check policy
    decision = policy_evaluate(request)
    if not decision.allowed:
        return OperationResponse(
            operation_type=request.operation_type,
            operation_name=request.operation_name,
            status=OperationStatus.FAILED,
            data={},
            error=decision.reason,
        )
    
    # Route to handler
    response = handler.handle(request)
    
    # Log routing decision
    log_routing(request, response)
    
    return response
```

### Handler Interface
```python
class OperationHandler(Protocol):
    async def handle(self, request: OperationRequest) -> OperationResponse:
        ...
```

## Integration Points

### Orchestrator Intake
- Orchestrator intake uses router for all incoming requests
- Request is wrapped in OperationRequest
- Response is unwrapped from OperationResponse

### Planner
- Planner uses router for tool execution operations
- Planner uses router for memory read operations
- Planner uses router for ML inference operations

### Executor
- Executor uses router for tool execution operations
- Executor uses router for workflow operations

### Tool Executor
- Tool Executor uses router for tool execution
- Tool Executor is a handler for TOOL operations

### Memory Service
- Memory Service uses router for memory operations
- Memory Service is a handler for MEMORY operations

### ML Runtime
- ML Runtime uses router for ML operations
- ML Runtime is a handler for ML operations

### API Routes
- API routes use router for all operations
- API routes wrap requests in OperationRequest
- API routes unwrap responses from OperationResponse

## AdmissionController

### Purpose
AdmissionController evaluates requests before routing to ensure policy compliance.

### Admission Stages
1. **Validation:** Validate request structure and required fields
2. **Authentication:** Verify authentication and authorization
3. **Policy Evaluation:** Evaluate operation against policy
4. **Quota Check:** Check tenant/account quotas
5. **Approval Check:** Check if approval is required

### Admission Decision
```python
@dataclass(frozen=True)
class AdmissionDecision:
    allowed: bool
    reason: str | None = None
    approval_required: bool = False
    quota_exceeded: bool = False
```

## Implementation Status

### Completed
- OperationRouter contract exists (domain/orchestration/router.py)
- AdmissionController contract exists (domain/orchestration/router.py)
- CI check for router bypass

### Pending
- Router into orchestrator intake
- Router into planner
- Router into executor
- Router into tool executor
- Router into memory service
- Router into ML Runtime
- API routes use router
- Operation router tests
- Remove router bypasses

## Migration Strategy

### Phase 1: Add Router to New Code
- All new operations must use router
- All new API routes must use router
- All new service integrations must use router

### Phase 2: Integrate Router into Existing Code
- Update orchestrator intake to use router
- Update planner to use router
- Update executor to use router
- Update tool executor to use router
- Update memory service to use router
- Update ML Runtime to use router

### Phase 3: Update API Routes
- Update all API routes to use router
- Wrap requests in OperationRequest
- Unwrap responses from OperationResponse

### Phase 4: Remove Bypasses
- Remove direct tool execution
- Remove direct memory access
- Remove direct ML calls
- Ensure all operations go through router

## Testing Strategy

### Unit Tests
- Test routing decision logic
- Test handler selection
- Test admission controller stages
- Test policy evaluation

### Integration Tests
- Test router integration with orchestrator
- Test router integration with planner
- Test router integration with executor
- Test router integration with services

### Router Tests
- Test operation type routing
- Test handler registration
- Test routing statistics
- Test error handling

## Monitoring

### Metrics
- Routing decisions per operation type
- Handler selection distribution
- Admission controller decisions
- Routing latency (p50, p95, p99)

### Logging
- All routing decisions logged
- All admission decisions logged
- All handler selections logged
- All errors logged

### Alerts
- High routing latency
- High admission denial rate
- Handler not found
- Routing errors

## Failure Modes

### Handler Not Found
- Return error to caller
- Log as critical event
- Alert operations team

### Admission Denied
- Return error to caller
- Log as security event
- Include denial reason

### Handler Failure
- Return error to caller
- Log as error
- Do not retry automatically

## Compliance

### Governance
- All operations go through router
- All operations are policy-evaluated
- All operations are logged
- All operations are auditable

### Observability
- All routing decisions logged
- All admission decisions logged
- Metrics exported to monitoring system
- Audit trail maintained
