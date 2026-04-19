# Infrastructure Guide

> **For:** Engineering, Platform, SRE  
> **Status:** Production Required  
> **Version:** 2.0

---

## v2.0 Changes

- AWS Load Balancer Controller for EKS proper
- Fixed health model (startup/readiness/liveness)
- Redis Streams instead of BullMQ
- Honest multi-region (active-passive)
- SLO-based alerting

---

## 1. Infrastructure Architecture

### 1.1 Production Topology

```
Internet
  ↓
Cloudflare / AWS WAF
  ↓
AWS Load Balancer Controller → ALB (L7 HTTP/S)
  ↓
EKS Cluster
├─ Ingress / Gateway (8000)
├─ Gateway Service
├─ Realtime Service
├─ Orchestrator (8001)
├─ Memory (8002)
├─ ML (8004)
├─ Tools (8005)
├─ Search (8006)
├─ Communication (8007)
├─ Device/IoT (8008)
├─ Observability agents
↓
Data Plane
├─ PostgreSQL primary + read replicas
├─ Neo4j
├─ Qdrant
├─ Redis
├─ S3 / object storage
```

---

## 2. Kubernetes Platform Standards

### 2.1 Cluster Baseline

| Component | Implementation |
|-----------|---------------|
| Platform | Amazon EKS |
| Ingress | AWS Load Balancer Controller + ALB |
| Service-to-service | mTLS via service mesh |
| Autoscaling | HPA for pods, Karpenter for nodes |
| Secrets | Vault or AWS Secrets Manager |
| Observability | OTel Collector + Prometheus + Tempo + Loki |

### 2.2 AWS Load Balancer Controller (EKS)

**For EKS, use AWS Load Balancer Controller, NOT Service type:LoadBalancer.**

```yaml
# Ingress - creates ALB automatically
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: butler-gateway
  annotations:
    kubernetes.io/ingress.class: alb
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/healthcheck-path: /health/ready
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTPS":443}]'
spec:
  rules:
    - host: api.butler.lasmoid.ai
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: gateway
                port:
                  number: 80
```

### 2.3 Deployment Example

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gateway
  labels:
    app: gateway
spec:
  replicas: 3
  revisionHistoryLimit: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: gateway
  template:
    metadata:
      labels:
        app: gateway
    spec:
      terminationGracePeriodSeconds: 30
      containers:
        - name: gateway
          image: ghcr.io/lasmoid/butler-gateway:v2.0.0
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 8000
          env:
            - name: PORT
              value: "8000"
            - name: ORCHESTRATOR_URL
              value: "http://orchestrator:8001"
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
          # Four-state health model
          startupProbe:
            httpGet:
              path: /health/startup
              port: 8000
            failureThreshold: 30
            periodSeconds: 5
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8000
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /health/live
              port: 8000
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
---
apiVersion: v1
kind: Service
metadata:
  name: gateway
spec:
  selector:
    app: gateway
  ports:
    - name: http
      port: 80
      targetPort: 8000
  type: ClusterIP
```

---

## 3. Health Model

### 3.1 Four States (Kubernetes-Inspired)

| State | Indicates | Alert | Behavior |
|-------|-----------|-------|----------|
| **STARTING** | Initializing, loading config | No | Wait, don't serve traffic |
| **HEALTHY** | Ready to serve | No | Serve all traffic |
| **DEGRADED** | Partial failure | SLO-based | Monitor, alert on threshold |
| **UNHEALTHY** | Critical failure | Yes | Alert, escalate |

### 3.2 Required Endpoints

```python
class ServiceHealth:
    async def check_startup(self) -> HealthStatus:
        """Is initialization complete?"""
        if not self.startup_complete:
            return {"state": "STARTING", "message": "Initializing..."}
        return {"state": "STARTING", "complete": True}
    
    async def check_readiness(self) -> HealthStatus:
        """Should receive traffic?"""
        deps = await self.check_dependencies()
        if deps.unhealthy:
            return {"state": "UNHEALTHY", "reason": deps.reason}
        if deps.degraded:
            return {"state": "DEGRADED", "reason": "Partial deps"}
        return {"state": "HEALTHY"}
    
    async def check_liveness(self) -> HealthStatus:
        """Should be restarted?"""
        if self.critical_failure:
            return {"state": "UNHEALTHY", "action": "restart"}
        return {"state": "HEALTHY"}
```

### 3.3 Probe Configuration

| Probe | Purpose | Failure Action |
|-------|---------|----------------|
| startup | Slow initialization | Wait (max 150s with defaults) |
| readiness | Traffic eligibility | Stop traffic |
| liveness | Restart needed | Restart container |

---

## 4. Queue and Async Execution

### 4.1 Queue Choice

**NOT BullMQ.** Use Redis Streams for Butler (Python-native).

```python
# Redis Streams for Butler
STREAMS = {
    "execution": "butler:execution",
    "events": "butler:events",
    "notifications": "butler:notifications"
}

CONSUMER_GROUPS = {
    "execution": "butler:workers",
    "events": "butler:handlers"
}
```

### 4.2 Recommended Queue Pattern

| Use Case | Implementation |
|----------|----------------|
| Task queue | Redis Streams + outbox pattern |
| Fanout events | Redis Streams |
| Durable workflows | DB-backed state + queue dispatch |
| SQS fallback | AWS SQS for cloud-durable |

### 4.3 Worker Model

```python
async def execute_worker():
    """Redis Streams consumer group worker"""
    
    stream = StreamReader(
        "butler:execution",
        consumer_group="butler:workers",
        consumer_name=f"worker-{worker_id}"
    )
    
    async for message in stream.read():
        try:
            result = await execute_task(message.data)
            await stream.ack(message.id)
        except Exception as e:
            await stream.nack(message.id)
            # Retry logic handled by stream position, not requeue
```

---

## 5. Scaling Configuration

### 5.1 Horizontal Pod Autoscaler

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: gateway-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: gateway
  minReplicas: 3
  maxReplicas: 30
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0
    scaleDown:
      stabilizationWindowSeconds: 300
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
    - type: Pods
      pods:
        metric:
          name: requests_per_pod
        target:
          type: AverageValue
          averageValue: "1000"
```

### 5.2 Pod Disruption Budget

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: gateway-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: gateway
```

---

## 6. Redis Strategy

### 6.1 Use Cases

| Use Case | Redis Use |
|----------|----------|
| Rate limiting | Sliding window counters |
| Session cache | Hot user data |
| Context cache | Ephemeral context fragments |
| Embeddings | Vector cache (if PII-free) |
| Workflow state | Short-lived coordination |
| Streams | Event consumers |

### 6.2 Cache Key Patterns

```python
CACHE_KEYS = {
    "user_profile": "user:{user_id}:profile",
    "session": "session:{session_id}",
    "context": "context:{session_id}:summary",
    "embedding": "embedding:{model}:{content_hash}",
    "prefs": "prefs:{user_id}",
    "workflow": "workflow:{workflow_id}",
    "approval": "approval:{workflow_id}"
}

# TTL policy
TTL = {
    "user_profile": 3600,           # 1 hour
    "session": 1800,               # 30 min
    "context_summary": 300,        # 5 min
    "embedding": 86400,           # 24 hours
    "workflow_hot": 60,            # 1 min - not authoritative
    "approval": 900                # 15 min
}
```

### 6.3 Redis Cluster (When Needed)

Redis Cluster for horizontal scaling when single-node insufficient.

---

## 7. Data Layer

### 7.1 PostgreSQL

| Component | Implementation |
|-----------|---------------|
| Writer | Single primary |
| Read replicas | Async replicas for read-heavy |
| Connection pool | PgBouncer |
| Backups | RDS automated + PITR |

### 7.2 Write/Read Rules

- **Writes** → Primary only
- **Strong reads** → Primary  
- **Eventual reads** → Replica (if lag < threshold)
- **Read-after-write** → Primary (sticky window)

### 7.3 Storage Summary

| Data Type | Storage |
|----------|---------|
| Users, sessions | PostgreSQL |
| Workflow state | PostgreSQL (outbox) |
| Conversations | PostgreSQL + vector index |
| Graph relationships | Neo4j |
| Semantic memory | Qdrant |
| Files, artifacts | S3 |
| Cache, events | Redis |

---

## 8. Multi-Region Strategy

### 8.1 Active-Passive for Writes

```
Global DNS / Route 53
  ├─ Primary Region: us-east-1 (writes + reads)
  └─ Secondary Region: eu-west-1 (warm standby)
```

**Multi-region starts as active-passive, NOT active-active.**

- Writes go to single primary region
- Reads can serve from local replicas (if lag acceptable)
- Failover via Route 53 failover policy
- Controlled promotion, no dual-write

### 8.2 DNS Configuration

```yaml
# Route 53 failover record
- name: api.butler.lasmoid.ai
  type: A
  failover: PRIMARY
  health_check: /health
  target: us-east-1-alb

- name: api.butler.lasmoid.ai  
  type: A
  failover: SECONDARY
  target: eu-west-1-alb
```

---

## 9. SLO-Based Alerting

### 9.1 Alert Triggers

| Metric | SLO Target | Alert When |
|--------|-------------|------------|
| Availability | 99.9% | < 99.9% in window |
| Error rate | < 1% | > 1% for 5 min |
| Latency P99 | < 1.5s | > 1.5s for 5 min |
| Queue depth | < 1000 | > 1000 for 10 min |
| Replica lag | < 30s | > 30s for 5 min |

### 9.2 NOT Alert Triggers

- Single request timeout
- One-time spike without sustained violation
- Startup latency
- Cache miss (unless < 50% hit rate)

---

## 10. Observability

### 10.1 Required Stack

- OpenTelemetry SDKs in services
- OTel Collector
- Prometheus/Mimir
- Tempo (traces)
- Loki (logs)
- Grafana

### 10.2 Core Dashboards

| Dashboard | Metrics |
|-----------|---------|
| System overview | RPS, errors, latency |
| Gateway SLI | Availability, latency |
| Orchestrator | Queue depth, task success |
| Memory | Retrieval latency, hit rate |
| PostgreSQL | Connections, replica lag |
| Redis | Memory, eviction, stream lag |
| ML | Inference latency |

---

## 11. Anti-Patterns

### NEVER Use

| Anti-Pattern | Problem | Use Instead |
|--------------|---------|--------------|
| Service type:LoadBalancer | Creates CLB on EKS | AWS ALB Controller |
| Single /health endpoint | Startup/ready/live same | Four-state probes |
| BullMQ in Python world | Unnecessary Node dep | Redis Streams |
| Active-active everywhere | Dual-write complexity | Active-passive |
| Threshold-heavy alerting | Alert fatigue | SLO-based |

---

*Document owner: Platform Team*  
*Version: 2.0 - Production Required*  
*Last updated: 2026-04-18*