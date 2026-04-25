# Butler Hyperscale Agent Execution OS - System Overview

## Overview

Butler is a hyperscale agent execution OS designed to support 1M users and 10K RPS with P95 latency under 1.5 seconds. This document provides a comprehensive overview of the system architecture, services, and capabilities.

## Architecture

### Core Layers

1. **API Layer** (`backend/api/`)
   - HTTP routes and schemas
   - Request/response handling
   - Middleware integration

2. **Domain Layer** (`backend/domain/`)
   - Business rules and contracts
   - Service interfaces
   - Core domain logic

3. **Services Layer** (`backend/services/`)
   - Application orchestration
   - 18 specialized services
   - Service-to-service communication

4. **Infrastructure Layer** (`backend/infrastructure/`)
   - External integrations
   - Database clients
   - Message queues and caching

## Services

### Core Services

1. **Multi-Tenant Foundation** (`services/tenant/`)
   - Quota management
   - Entitlements system
   - Metering and billing
   - Tenant isolation

2. **Workflow Orchestration** (`services/workflow/`)
   - Durable workflows
   - State machines
   - Saga pattern implementation

3. **Agent Runtime** (`services/agent/`)
   - Agent lifecycle management
   - Task scheduling
   - Execution coordination

### Security & Compliance

4. **Security Service** (`services/security/`)
   - Encryption at rest and in transit
   - Audit logging
   - Consent management

5. **Advanced Security** (`services/security/`)
   - OAuth2/OIDC integration
   - JWT validation (RS256/ES256)
   - RBAC implementation

### Observability & Monitoring

6. **Observability** (`services/observability/`)
   - Metrics collection
   - Distributed tracing
   - Health checks

7. **Advanced Monitoring** (`services/analytics/`)
   - Real-time analytics
   - Alerting system
   - Dashboard aggregation

### Performance & Caching

8. **Advanced Caching** (`services/caching/`)
   - Distributed caching
   - Cache warming strategies
   - Cache invalidation

9. **Rate Limiting** (`services/rate_limiting/`)
   - Adaptive rate limiting
   - Request prioritization
   - Token bucket algorithm

### Data Management

10. **Memory Service** (`services/memory/`)
    - Embeddings generation
    - Vector search
    - Long-term memory storage

11. **Data Synchronization** (`services/sync/`)
    - Multi-master sync
    - Conflict resolution
    - Change log and replay

12. **Event Sourcing & CQRS** (`services/event_sourcing/`)
    - Event store
    - Projections
    - Read/write separation

### Networking & Messaging

13. **Advanced Networking** (`services/networking/`)
    - Service discovery
    - Connection pooling
    - Retry policies with backoff

14. **Advanced Message Processing** (`services/messaging/`)
    - Priority message queues
    - Dead letter queues
    - Message transformation

### Testing & Reliability

15. **Advanced API Testing** (`services/testing/`)
    - Load testing framework
    - Chaos engineering tools
    - Canary deployment automation

16. **API Gateway** (`services/gateway/`)
    - Rate limiting
    - Request routing
    - Circuit breaker

### ML Infrastructure

17. **ML Runtime** (`services/ml/`)
    - Model serving
    - A/B testing
    - Model monitoring and drift detection

### Configuration & Deployment

18. **Feature Flags** (`services/features/`)
    - Dynamic configuration
    - Rollout strategies
    - Experiment management

## Technology Stack

### Backend
- **Framework**: FastAPI
- **Language**: Python 3.11+
- **Database**: PostgreSQL
- **Cache**: Redis
- **Message Queue**: Redpanda (Kafka-compatible)

### Security
- **Authentication**: OAuth2/OIDC
- **Authorization**: RBAC
- **Encryption**: Argon2id for passwords, TLS for transit
- **JWT**: RS256/ES256 with JWKS

### Observability
- **Logging**: Structlog
- **Tracing**: OpenTelemetry
- **Metrics**: Prometheus-compatible
- **Monitoring**: Custom analytics service

### Deployment
- **Containerization**: Docker
- **Orchestration**: Docker Compose (development)
- **CI/CD**: Git-based workflows

## Design Principles

### Butler Engineering Constitution

1. **Prime Directive**
   - Correct before clever
   - Readable before compressed
   - Explicit before magical
   - Testable before extensible
   - Maintainable before impressive
   - Performant where it matters
   - Production-safe by default

2. **Python Standards**
   - PEP 8 compliance
   - PEP 257 docstrings
   - Line lengths: 88-100 chars
   - snake_case for variables/functions
   - CapWords for classes
   - UPPER_SNAKE_CASE for constants

3. **Domain First**
   - Business logic in domain/
   - Application orchestration in services/
   - External integrations in infrastructure/
   - HTTP concerns in api/

4. **Framework Boundaries**
   - Domain code must not depend on FastAPI
   - Domain code must not depend on ORM models directly
   - All infrastructure through explicit interfaces

5. **Dependency Direction**
   - Allowed: api -> services -> domain
   - Allowed: infrastructure -> domain
   - Forbidden: domain -> api
   - Forbidden: domain -> FastAPI

## Performance Targets

- **Users**: 1M concurrent users
- **RPS**: 10K requests per second
- **Latency**: P95 < 1.5 seconds
- **Availability**: 99.9% uptime
- **Scalability**: Horizontal scaling

## Security Model

### Authentication
- OAuth2/OIDC authorization code flow
- JWT with RS256/ES256 signatures
- JWKS endpoint for key validation
- Issuer and audience validation

### Authorization
- Role-Based Access Control (RBAC)
- Hierarchical role inheritance
- Resource-level permissions
- Policy evaluation engine

### Encryption
- TLS 1.3 for all network traffic
- Argon2id for password hashing
- AES-256 for data at rest
- Secure key management

## Deployment Architecture

### Development
- Docker Compose for local development
- Local PostgreSQL and Redis
- Mocked external services

### Production
- Horizontal scaling via container orchestration
- Database replication for high availability
- Distributed caching layer
- Load balancer for API gateway

## Monitoring & Observability

### Metrics
- Request latency (P50, P95, P99)
- Error rates by endpoint
- Database connection pool metrics
- Cache hit rates
- Queue depths

### Logging
- Structured logging with context
- Log levels: DEBUG, INFO, WARNING, ERROR
- Correlation IDs for request tracing
- Sensitive data redaction

### Tracing
- Distributed tracing across services
- Span propagation
- Performance bottleneck identification

## Documentation

- API documentation: OpenAPI/Swagger
- Service documentation: `docs/services/`
- Runbooks: `docs/runbooks/`
- Security: `docs/security/`
- Development setup: `docs/dev/SETUP.md`

## Testing Strategy

- Unit tests for domain logic
- Integration tests for service boundaries
- API tests for transport contracts
- Load tests for performance validation
- Chaos tests for resilience verification

## Next Steps

For detailed information on specific services, refer to:
- Service documentation in `docs/services/`
- Implementation plan in `backend/butler_runtime/`
- Architecture rules in `docs/rules/SYSTEM_RULES.md`
