# High Latency Runbook

> **Severity:** P1 - High  
> **SLA:** 1 hour  
> **On-Call:** Platform Team

---

## v2.0 Changes

- SLO-based alerting (not threshold-heavy)
- Four-state health model integration
- Error budget tracking

---

## Triggering Conditions (SLO-Based)

| Metric | SLO Target | Alert Condition |
|--------|-----------|-----------------|
| Latency P99 | < 1.5s | > 1.5s for 5+ minutes |
| Latency P95 | < 500ms | > 500ms for 5+ minutes |
| Latency spike | < 50% | > 50% increase for 5+ min |

**Health Check First:**
```bash
curl http://gateway:8000/health
# HEALTHY = Normal latency
# DEGRADED = Elevated latency, monitor
# UNHEALTHY = Critical latency, alert
# STARTING = Initializing
```

---

## Quick Diagnosis

### Step 1: Check Service Health

```bash
# Check latency SLO status
curl http://gateway:8000/metrics/slo/latency
# Returns: current_value, error_budget_remaining, burn_rate

# Check overall health
curl http://gateway:8000/health
```

### Step 2: Identify Affected Service

```bash
# Check latency by service
curl http://gateway:8000/metrics/latency

# Check percentiles
curl http://gateway:8000/metrics/percentiles

# Check error budget
curl http://gateway:8000/metrics/slo
```

### Step 3: Check Dependencies

```bash
# Database latency
curl http://memory:8003/metrics/db_latency

# Cache hit rate
curl http://memory:8003/metrics/cache_hit_rate

# External API latency
curl http://gateway:8000/metrics/external_latency
```

---

## Resolution Steps

### Database Issues

```bash
# Check connection pool
curl http://memory:8003/debug/connections

# Check slow queries
kubectl exec -it postgresql-0 -- psql -U butler -c "SELECT * FROM pg_stat_activity WHERE state = 'active'"

# Check query performance
kubectl exec -it postgresql-0 -- psql -U butler -c "SELECT query, calls, mean_time FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10"
```

### Cache Issues

```bash
# Check Redis memory
kubectl exec -it redis-0 -- redis-cli INFO memory

# Check hit rate
curl http://memory:8003/metrics/cache_hit_rate

# If hit rate < 80%, clear stale cache
curl -X POST http://memory:8003/cache/clear

# Increase cache size
kubectl set env deployment/memory REDIS_MAXMEMORY=4gb
```

### External API Issues

```bash
# Check external API health
curl http://gateway:8000/health/external

# Use fallback (if available)
curl -X POST http://gateway:8000/config/use-fallback
```

### Resource Exhaustion

```bash
# Check CPU throttling
kubectl top pods -l app={service}

# Check for OOM
kubectl get events --field-selector reason=OOMKilled

# Check memory
kubectl top pods

# Scale up if needed
kubectl scale deployment/{service} --replicas=5
```

---

## Latency by Service

### Gateway

```bash
# Check rate limiting
curl http://gateway:8000/debug/rate_limits

# Check circuit breakers
curl http://gateway:8000/debug/circuit_breakers

# Check SLO status
curl http://gateway:8000/metrics/slo
```

### Orchestrator

```bash
# Check task queue depth
curl http://orchestrator:8002/queue/depth

# Check worker availability
curl http://orchestrator:8002/workers/status

# Check queue latency
curl http://orchestrator:8002/metrics/queue_latency
```

### Memory

```bash
# Check embedding cache
curl http://memory:8003/cache/embeddings

# Check vector search latency
curl http://memory:8003/metrics/vector_search

# Preload embeddings
curl -X POST http://memory:8003/cache/preload-embeddings
```

---

## Post-Incident

1. Document slow component
2. Create optimization ticket
3. Update SLAs if needed
4. Log SLO violation

---

## SLO-Based Alerting Rules

### Alert Triggers

| Alert | Condition | Action |
|-------|----------|--------|
| SLO Burn Rate | > 10% in 1 hour | Warning |
| SLO Burn Rate | > 50% in 1 hour | Critical |
| Error Budget Exhausted | < 10% remaining | Alert |
| Latency Spike | > 2x baseline | Investigate |

### NOT Alert Triggers

- Single request timeout
- One-time spike without sustained violation
- Startup latency
- Cache miss (unless sustained < 50% hit rate)

---

## Contacts

| Role | Name | Contact |
|------|------|---------|
| On-call | | PagerDuty |
| Team Lead | | Slack #platform |

---

*Version: 2.0*  
*Last updated: 2026-04-18*