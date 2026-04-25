# ML Runtime Health and Fallback Strategy

This document defines the health monitoring and fallback strategy for the ML Runtime, ensuring reliable and resilient provider access.

## Overview

**Goal:** Ensure ML Runtime can detect provider failures and route to healthy providers
**Scope:** ML Runtime service, provider registry, fallback chains
**Status:** Contract-only - implementation pending

## Health Model

### Health States
- **STARTING:** Provider is initializing
- **HEALTHY:** Provider is responding normally
- **DEGRADED:** Provider is responding but with degraded performance
- **UNHEALTHY:** Provider is not responding or failing requests

### Health Checks
- **Liveness:** Can the provider accept requests?
- **Readiness:** Is the provider ready to serve traffic?
- **Startup:** Has the provider completed initialization?

### Health Metrics
- **Latency:** Request response time (p50, p95, p99)
- **Error Rate:** Percentage of failed requests
- **Success Rate:** Percentage of successful requests
- **Throughput:** Requests per second

## Provider Registry

### Provider Registration
```python
@dataclass(frozen=True)
class ProviderConfig:
    name: str
    provider_type: ProviderType  # OPENAI, ANTHROPIC, etc.
    api_key: str
    base_url: str
    model: str
    max_retries: int
    timeout_seconds: int
    enabled: bool
```

### Registry Methods
- `register_provider(config: ProviderConfig)` - Register a provider
- `get_provider(name: str) -> ProviderConfig` - Get provider config
- `list_providers() -> list[ProviderConfig]` - List all providers
- `disable_provider(name: str)` - Disable a provider
- `enable_provider(name: str)` - Enable a provider

### Health Tracking
- Each provider has a health state
- Health state is updated by health checks
- Health state is persisted across restarts
- Health state is exposed for routing decisions

## Fallback Chains

### Fallback Strategy
When a provider fails, the ML Runtime routes to the next provider in the fallback chain.

### Fallback Chain Definition
```python
@dataclass(frozen=True)
class FallbackChain:
    primary_provider: str
    fallback_providers: list[str]
    fallback_strategy: FallbackStrategy  # SEQUENTIAL, PARALLEL, ADAPTIVE
```

### Fallback Strategies
- **SEQUENTIAL:** Try primary, then fallback1, then fallback2, etc.
- **PARALLEL:** Send to all providers, use first successful response
- **ADAPTIVE:** Route based on current health and performance metrics

### Fallback Triggers
- **Timeout:** Provider does not respond within timeout
- **Error:** Provider returns an error
- **Degraded:** Provider is in DEGRADED state
- **Unhealthy:** Provider is in UNHEALTHY state

## Dead Provider Skip

### Skip Logic
When a provider is marked UNHEALTHY, the ML Runtime skips it entirely:
- No requests sent to unhealthy providers
- Health checks continue to monitor unhealthy providers
- Unhealthy providers can be re-enabled if health recovers

### Recovery
- Health checks run periodically (e.g., every 30 seconds)
- If health check passes, provider is marked HEALTHY
- Provider is re-added to routing pool
- Provider is marked as primary if configured

## Metrics Failure Safety

### Metrics Collection Failure
If metrics collection fails:
- Log the failure
- Continue using cached metrics
- Mark metrics collection as degraded
- Do not block requests due to metrics failure

### Metrics Storage Failure
If metrics storage fails:
- Log the failure
- Continue collecting metrics in memory
- Do not block requests due to storage failure
- Retry storage with exponential backoff

## Health Routing

### Routing Decision
```python
def select_provider(request: MLRequest) -> ProviderConfig:
    # Filter to enabled providers
    enabled_providers = registry.list_enabled_providers()
    
    # Filter to healthy providers
    healthy_providers = [
        p for p in enabled_providers 
        if health_tracker.get_health(p.name) == HealthState.HEALTHY
    ]
    
    # Select based on fallback chain
    if not healthy_providers:
        # All providers unhealthy - return error
        raise NoHealthyProvidersError()
    
    return fallback_chain.select(healthy_providers, request)
```

### Routing Metrics
- Track routing decisions
- Track fallback usage
- Track provider selection distribution
- Track latency per provider

## Implementation Status

### Completed
- Health contracts defined (domain/ml/runtime_health.py)
- CI check for direct provider imports

### Pending
- Health integrated into MLRuntime
- Provider registry enforced
- Fallback chains implemented
- Dead provider skip
- Metrics failure safe
- Health routing tests
- Remove ML bypasses

## Migration Strategy

### Phase 1: Add Health Contracts
- Define health state enum
- Define health check interface
- Define provider config dataclass

### Phase 2: Implement Provider Registry
- Implement registry with in-memory storage
- Add provider registration methods
- Add health tracking methods

### Phase 3: Implement Fallback Chains
- Define fallback chain dataclass
- Implement fallback strategies
- Integrate with ML Runtime

### Phase 4: Remove Direct Provider SDK Imports
- Refactor 64 files to use ML Runtime
- Update imports to use ML Runtime interfaces
- Remove direct OpenAI/Anthropic imports

## Testing Strategy

### Unit Tests
- Test health state transitions
- Test provider registry methods
- Test fallback chain selection
- Test metrics failure handling

### Integration Tests
- Test provider health monitoring
- Test fallback chain execution
- Test dead provider skip
- Test routing decisions

### Chaos Tests
- Test provider failure scenarios
- Test provider recovery scenarios
- Test all providers unhealthy scenario
- Test metrics failure scenarios

## Monitoring

### Metrics
- Provider health states
- Provider latency (p50, p95, p99)
- Provider error rates
- Fallback chain usage
- Routing decisions

### Logging
- Health check results
- Provider state transitions
- Fallback chain activations
- Routing decisions

### Alerts
- Provider unhealthy
- All providers unhealthy
- High error rate
- High latency

## Failure Modes

### No Healthy Providers
- Return error to caller
- Log as critical event
- Alert operations team

### Metrics Collection Failure
- Continue using cached metrics
- Log as warning
- Do not block requests

### Provider Registry Failure
- Use in-memory fallback
- Log as error
- Alert operations team

## Compliance

### SLA
- 99.9% uptime for ML Runtime
- 95th percentile latency < 2 seconds
- 99.9% of requests succeed (with fallback)

### Observability
- All health checks logged
- All routing decisions logged
- All fallbacks logged
- Metrics exported to monitoring system
