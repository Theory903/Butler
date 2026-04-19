# Service Down Runbook

> **Severity:** P0 - Critical  
> **SLA:** 30 minutes  
> **On-Call:** Platform Team

---

## v2.0 Changes

- Added four-state health model
- Startup/liveness/readiness/degraded distinction
- SLO-based alerting

---

## Triggering Conditions (SLO-Based)

| Metric | SLO Target | Alert Condition |
|--------|-----------|-----------------|
| Availability | 99.9% | < 99.9% window |
| Error rate | < 1% | > 10% for 5+ min |
| Health state | HEALTHY | UNHEALTHY |

**Health Check First:**
```bash
curl http://gateway:8000/health
# Returns: STARTING | HEALTHY | DEGRADED | UNHEALTHY

# Understand which state you have:
# STARTING = Service booting, wait
# HEALTHY = Ready, serve traffic
# DEGRADED = Partial failure, monitor
# UNHEALTHY = Critical, alert immediately
```

---

## Quick Diagnosis

### Step 1: Check Health State

```bash
# Check all service health
curl http://gateway:8000/health/all

# Check specific service
curl http://gateway:8000/health/{service_name}

# Check availability SLO
curl http://gateway:8000/metrics/slo/availability
```

### Step 2: Identify Health State

```bash
# Four states: STARTING → HEALTHY → DEGRADED → UNHEALTHY

STARTING: 
  - Service initializing
  - Config loading
  - Wait, don't alert

HEALTHY:
  - All checks pass
  - Ready to serve
  - Normal operation

DEGRADED:
  - Partial dependency failure
  - Elevated error rate
  - Monitor, alert on threshold

UNHEALTHY:
  - Critical failure
  - Cannot serve
  - Immediate alert and escalate
```

---

## Resolution Steps

### Step 1: Determine Health State

```bash
curl http://gateway:8000/health

# If STARTING → Wait for HEALTHY
# If HEALTHY → Check other symptoms
# If DEGRADED → Investigate dependencies
# If UNHEALTHY → Immediate action
```

### Step 2: Restart Service

```bash
# Quick restart (recommended first step)
kubectl rollout restart deployment/{service}
kubectl rollout status deployment/{service}

# Check health after restart
curl http://{service}:8000/health
```

### Step 3: Check Logs

```bash
# View recent logs
kubectl logs -l app={service} --tail=100 -f

# With previous container
kubectl logs -l app={service} --previous --tail=100
```

### Step 4: Check Resources

```bash
# CPU/Memory
kubectl top pods -l app={service}

# Check OOM events
kubectl get events --field-selector reason=OOMKilled
```

### Step 5: Scale Up (if overloaded)

```bash
# Scale deployment
kubectl scale deployment/{service} --replicas=5
```

### Step 6: Rollback (if after deploy)

```bash
# Check recent deploys
kubectl rollout history deployment/{service}

# Rollback
kubectl rollout undo deployment/{service}
```

---

## Service-Specific Steps

### Gateway

```bash
# Check health
curl http://gateway:8000/health

# Check upstream services
curl http://gateway:8000/debug/upstreams

# Check availability SLO
curl http://gateway:8000/metrics/slo/availability

# Restart with zero downtime
kubectl rollout restart deployment/gateway
```

### Orchestrator

```bash
# Check health
curl http://orchestrator:8002/health

# Check queue depth
curl http://orchestrator:8002/queue/depth

# Clear stuck tasks
curl -X POST http://orchestrator:8002/queue/clear-stuck
```

### Memory

```bash
# Check health
curl http://memory:8003/health

# Check Redis connection
curl http://memory:8003/health/redis

# Check cache hit rate
curl http://memory:8003/metrics/cache_hit_rate
```

---

## Health State Transitions

```
STARTING ──→ HEALTHY ──→ DEGRADED ──→ UNHEALTHY
   ▲           │            │            │
   │           ▼            ▼            │
   └───────────HEALTHY◄─────DEGRADED─────┘
   
Recovery path:
UNHEALTHY → Fix → HEALTHY (or STARTING → HEALTHY)
DEGRADED → Fix → HEALTHY
```

---

## Post-Incident

1. Update status page
2. Document root cause
3. Create ticket for prevention
4. Review runbook improvements
5. Log SLO violation

---

## Contacts

| Role | Name | Contact |
|------|------|---------|
| On-call | | PagerDuty |
| Team Lead | | Slack #ops |
| VP Eng | | Slack #leadership |

---

*Version: 2.0*  
*Last updated: 2026-04-18*