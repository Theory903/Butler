# Database Failure Runbook

> **Severity:** P0 - Critical  
> **SLA:** 15 minutes  
> **On-Call:** Data Team

---

## v2.0 Changes

- Added SLO-based alerting
- Added four-state health model
- Fixed dangerous DB operations
- Added split-brain prevention for failover

---

## Triggering Conditions (SLO-Based)

| Metric | SLO Target | Trigger Condition |
|--------|-----------|-----------------|
| DB availability | 99.9% | Unavailable |
| Connection errors | < 1% | > 10% for 5 min |
| Replication lag | < 30s | > 30s sustained |
| Error rate | < 1% | > 1% for 5 min |

**Health Check First:**
```bash
# Check current health state
curl http://postgresql:8000/health
# Returns: STARTING | HEALTHY | DEGRADED | UNHEALTHY
```

---

## Quick Diagnosis

### Step 1: Check Database Status

```bash
# Check pod status
kubectl get pods -l app=postgresql -o wide

# Check PVC usage
kubectl get pvc postgresql-data

# Check events
kubectl get events --field-selector involvedObject.name=postgresql-0
```

### Step 2: Check Health State

```bash
# Four-state health model
curl http://postgresql:8000/health
# HEALTHY = Ready, serve traffic
# DEGRADED = Partial failure, monitor  
# UNHEALTHY = Critical, alert immediately
# STARTING = Initializing, wait
```

### Step 3: Check Replication

```bash
# Check replication status
kubectl exec -it postgresql-0 -- psql -U postgres -c "SELECT * FROM pg_stat_replication"

# Check lag
kubectl exec -it postgresql-0 -- psql -U postgres -c "SELECTnow() - pg_last_xact_replay_timestamp() AS replication_lag"
```

---

## Resolution Steps

### Database Pod Crash

```bash
# Check logs
kubectl logs postgresql-0 --previous

# Check resource limits
kubectl get pod postgresql-0 -o jsonpath='{.spec.containers[0].resources}'

# Check OOM events
kubectl get events --field-selector reason=OOMKilled

# Restart with resources (NOT delete for auto-heal)
kubectl delete pod postgresql-0
```

---

### Replication Lag (SLO-Based Alert)

```bash
# Check lag
kubectl exec -it postgresql-0 -- psql -U postgres -c "SELECT now() - pg_last_xact_replay_timestamp() AS replication_lag"

# WARNING: Alert if > 30s for > 5 minutes
# Recovery: Pause and resume
kubectl exec -it postgresql-replica-0 -- psql -U postgres -c "SELECT pg_wal_replay_pause()"
kubectl exec -it postgresql-replica-0 -- psql -U postgres -c "SELECT pg_wal_replay_resume()"

# If still lagging, rebuild replica (NOT pg_archivecleanup)
kubectl delete pod postgresql-replica-0
```

---

### Disk Full

```bash
# Check disk usage
kubectl exec -it postgresql-0 -- df -h

# Clean up WAL replicas (SAFE - don't use VACUUM FULL)
kubectl exec -it postgresql-0 -- rm -f /var/lib/postgresql/archive/*

# Increase storage (NOT VACUUM FULL)
kubectl patch pvc postgresql-data -p '{"spec":{"resources":{"requests":{"storage":"50Gi"}}}}'

# IF you must vacuum, use autovacuum only:
kubectl exec -it postgresql-0 -- psql -U butler -c "VACUUM"
# NOT VACUUM FULL - it locks tables and causes downtime
```

---

### Connection Pool Exhaustion

```bash
# Check connections
kubectl exec -it postgresql-0 -- psql -U postgres -c "SELECT count(*) FROM pg_stat_activity"

# Kill idle connections (SAFE):
kubectl exec -it postgresql-0 -- psql -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - interval '15 minutes'"

# Restart connection pooler
kubectl rollout restart deployment/pgbouncer
```

---

## Failover Procedure (Split-Brain Prevention)

### Prerequisites (MUST verify)

1. **Verify primary is DOWN:**

```bash
# Check if primary accepts writes
kubectl exec -it postgresql-0 -- psql -U postgres -c "SELECT 1"
# If fails, primary is DOWN
```

2. **Verify replica caught up:**

```bash
# Verify zero lag
kubectl exec -it postgresql-replica-0 -- psql -U postgres -c "SELECT now() - pg_last_xact_replay_timestamp() AS replication_lag"
# Must show < 1 second
```

### Step 1: Prevent Dual-Write

```bash
# CRITICAL: Stop writes to OLD primary
kubectl exec -it postgresql-0 -- psql -U postgres -c "SELECT pg_switch_wal()"
# This ensures WAL is flushed before promotion
```

### Step 2: Promote Replica

```bash
# Promote replica to primary
kubectl exec -it postgresql-replica-0 -- pg_ctl promote -D /var/lib/postgresql/15/main
```

### Step 3: Update Service (Atomic)

```bash
# Update connection string atomically
kubectl patch service postgresql -p '{"spec":{"selector":{"role":"primary"}}}'
```

### Step 4: Verify New Primary

```bash
# Test new primary
kubectl exec -it postgresql-replica-0 -- psql -U postgres -c "SELECT 1"
```

### Step 5: Notify All Clients

```bash
# Update connection config atomically
kubectl delete configmap app-config
kubectl create configmap app-config --from-literal=DATABASE_URL="postgresql-replica:5432/butler"
```

---

## Recovery Checklist

- [ ] Database responding
- [ ] Replication caught up (lag < 1s)
- [ ] Connections working
- [ ] Health state = HEALTHY
- [ ] No error rate
- [ ] Document root cause
- [ ] Plan fix
- [ ] SLO violation logged

---

## Anti-Patterns

### NEVER Do

| Action | Why | Use Instead |
|--------|-----|------------|
| `pg_archivecleanup` | Dangerous, manual | Rebuild replica |
| `VACUUM FULL` | Locks tables | `VACUUM` (no FULL) |
| Force promote | Causes data loss | Verify lag first |

---

## Contacts

| Role | Name | Contact |
|------|------|---------|
| On-call | | PagerDuty |
| DBA | | Slack #data |
| Team Lead | | Slack #leadership |

---

*Version: 2.0*  
*Last updated: 2026-04-18*