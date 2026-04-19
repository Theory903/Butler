# Deployment Guide

> **For:** DevOps, Engineering  
> **Status:** Draft  
> **Version:** 1.0

---

## 1. Environments

### 1.1 Environment Matrix

| Env | Purpose | URL | Data |
|-----|---------|-----|------|
| Dev | Local development | localhost | Mock |
| Staging | Integration testing | staging.butler.lasmoid.ai | Test data |
| Prod | Production | app.butler.lasmoid.ai | Real data |

### 1.2 Deployment Flow

```
Dev → Staging → Prod
   (PR)   (Merge)   (Tag)
```

---

## 2. Local Development

### 2.1 Prerequisites

```bash
# Install
- Docker + Docker Compose
- Node.js 20+
- Python 3.11+
- pnpm
```

### 2.2 Quick Start

```bash
# Clone and setup
git clone butler.git
cd butler

# Start infrastructure
docker-compose up -d

# Start services
cd services/gateway && docker-compose up
cd services/orchestrator && docker-compose up
```

---

## 3. Docker Services

### 3.1 Infrastructure Services

```yaml
# docker-compose.yml (infrastructure folder)
services:
  postgres:
    image: postgres:15
    ports: [5432:5432]
    
  neo4j:
    image: neo4j:5.12
    ports: [7474:7474, 7687:7687]
    
  qdrant:
    image: qdrant/qdrant:v1.7.4
    ports: [6333:6333]
    
  redis:
    image: redis:7-alpine
    ports: [6379:6379]
    
  rabbitmq:
    image: rabbitmq:3-management
    ports: [5672:5672, 15672:15672]
```

---

## 4. Kubernetes Deployment

### 4.1 Base Configuration

```yaml
# k8s/base/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: butler-gateway
spec:
  replicas: 3
  selector:
    matchLabels:
      app: gateway
  template:
    spec:
      containers:
      - name: gateway
        image: butler/gateway:latest
        ports:
        - containerPort: 8000
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

### 4.2 Services

```yaml
# k8s/base/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: gateway
spec:
  selector:
    app: gateway
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
```

---

## 5. CI/CD Pipeline

### 5.1 GitHub Actions

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pytest
  
  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/build-push-action@v5
        with:
          push: true
          tags: butler/gateway:${{ github.sha }}

  deploy:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: azure/k8s-set-context@v1
      - run: kubectl apply -f k8s/
```

---

## 6. Health Checks

### 6.1 Endpoint Health

```bash
# Gateway
curl http://gateway/health

# Orchestrator
curl http://orchestrator/health

# Memory
curl http://memory/health
```

### 6.2 Kubernetes Probes

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
```

---

## 7. Rollback

### 7.1 Quick Rollback

```bash
# Rollback to previous version
kubectl rollout undo deployment/gateway

# Rollback to specific revision
kubectl rollout undo deployment/gateway --to-revision=3
```

---

## 8. Monitoring

### 8.1 Key Dashboards

- Grafana: grafana.butler.lasmoid.ai
- Metrics: Prometheus
- Logs: ELK Stack

---

*Document owner: DevOps Team*  
*Last updated: 2026-04-15*