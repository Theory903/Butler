# Runbook Index

> **For:** Operations, On-call  
> **Status:** Production Required  
> **Version:** 2.0

---

## v2.0 Changes

- SLO-based alerting (not threshold-heavy)
- Four-state health model
- Anti-patterns documented

---

## Quick Reference

| Emergency | Runbook | Contact |
|-----------|---------|----------|
| Service down | [service-down.md](./service-down.md) | On-call |
| High latency | [high-latency.md](./high-latency.md) | Platform |
| DB failure | [database-failure.md](./database-failure.md) | Data |

---

## SLO Targets

| Metric | Target | Alert When Violated |
|--------|--------|-------------------|
| Availability | 99.9% | < 99.9% in window |
| Error rate | < 1% | > 1% for 5 min |
| Latency P99 | < 1.5s | > 1.5s for 5 min |
| Latency P95 | < 500ms | > 500ms for 5 min |
| Replication lag | < 30s | > 30s for 5 min |

---

## Escalation Path

```
P0 (Critical):   On-call → Team Lead → VP → CEO (30 min)
P1 (High):     On-call → Team (1 hour)
P2 (Medium):   Team → Ticket (4 hours)
P3 (Low):      Ticket → Next sprint
```

---

## Health Model

### Four States

| State | Indicates | Alert |
|-------|-----------|-------|
| **STARTING** | Initializing | No |
| **HEALTHY** | Ready to serve | No |
| **DEGRADED** | Partial failure | SLO-based |
| **UNHEALTHY** | Critical failure | Yes |

### Health Endpoints

```
/health/startup   - Initialization status
/health/ready     - Traffic eligibility  
/health/live      - Restart needed
/health/degraded  - Partial failure
/health/deps     - Dependency status
```

---

## On-Call Checklist

1. Acknowledge alert (5 min)
2. Check health state (`curl /health`)
3. Assess severity (STARTING/HEALTHY/DEGRADED/UNHEALTHY)
4. Check SLO dashboard
5. Execute runbook
6. Notify stakeholders

---

## Common Issues

| Issue | Symptoms | Check |
|-------|----------|-------|
| Gateway 5xx | High error rate | `curl /health` → UNHEALTHY? |
| Slow response | P99 > 1.5s | SLO violation? |
| DB failure | Connection errors | Check replication lag |
| Tool failures | Action errors | Check tool policy |

---

## Anti-Patterns

### Alert Anti-Patterns

| Anti-Pattern | Problem | Use Instead |
|--------------|---------|-------------|
| Threshold-heavy | Alert fatigue | SLO-based |
| Single /health | Ambiguous state | Four-state model |

### Database Anti-Patterns

| Anti-Pattern | Problem | Use Instead |
|--------------|---------|-------------|
| pg_archivecleanup | Dangerous | Rebuild replica |
| VACUUM FULL | Locks tables | VACUUM (no FULL) |

---

## Contacts

| Role | Contact |
|------|---------|
| On-call | PagerDuty |
| DBA | Slack #data |
| Team Lead | Slack #leadership |

---

*Document owner: Operations*  
*Version: 2.0 - Production Required*  
*Last updated: 2026-04-18*