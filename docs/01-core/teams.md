# Team Structure and Responsibilities

> **For:** All teams, HR, Leadership
> **Status:** v0.3 (Production-Ready)
> **Version:** 3.0
> **Reference:** Production-ready team structure

---

## 1. Team Overview

| Team | Size | Focus |
|------|------|-------|
| Platform | 2-3 | Infrastructure, Gateway |
| Orchestration | 2-3 | Brain, Planning, Execution |
| Memory | 2 | Graph, Vector, Retrieval |
| ML/AI | 2-3 | Intent, Recommendations, Embeddings |
| Mobile | 2 | Expo app, Voice interface |
| Tools | 2 | Action execution, Integrations |
| Data | 1-2 | Pipeline, Analytics |

---

## 2. Platform Team

### Responsibilities
- API Gateway
- Authentication
- Rate limiting
- Deployment infrastructure

### Owned Services
- Gateway
- Auth Service

### SLA
- 99.9% uptime
- <100ms latency (P95)

---

## 3. Orchestration Team

### Responsibilities
- Intent understanding
- Task planning
- Execution coordination

### Owned Services
- Orchestrator
- Planner

### SLA
- <2s response (complex tasks)

---

## 4. Memory Team

### Responsibilities
- User data storage
- Context retrieval
- Graph relationships

### Owned Services
- Memory Service
- Neo4j
- Qdrant

### SLA
- <200ms retrieval

---

## 5. ML/AI Team

### Responsibilities
- Model training
- Intent classification
- Recommendations

### Owned Services
- ML Service
- Embeddings
- Models

### SLA
- >90% intent accuracy

---

## 6. Mobile Team

### Responsibilities
- User interface
- Voice input/output
- Push notifications

### Owned Services
- Expo Mobile App

### SLA
- 60fps UI

---

## 7. Tools Team

### Responsibilities
- Action execution
- Third-party integrations
- Automation

### Owned Services
- Tools Service

### SLA
- >95% action success

---

## 8. Data Team

### Responsibilities
- Event logging
- Analytics
- ML training data

### SLA
- Real-time pipelines

---

*Document owner: Engineering Lead*  
*Last updated: 2026-04-15*
