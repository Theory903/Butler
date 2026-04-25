# Butler Hyperscale Agent Execution OS - Operational Handoff

## System Overview

Butler is a hyperscale agent execution OS designed to support 1M users, 10K RPS, with P95 latency under 1.5 seconds. The system consists of 18 specialized services organized in a layered architecture.

## Quick Start

### Development Environment

```bash
# Start all services
docker-compose up -d

# Check health
curl http://localhost:8000/health

# Run tests
pytest backend/tests/
```

### Key Services

- **API Gateway**: `http://localhost:8000`
- **Multi-Tenant**: Quota and entitlement management
- **Workflow Orchestration**: Durable workflow execution
- **Agent Runtime**: Agent lifecycle management
- **Memory Service**: Embeddings and vector search
- **ML Runtime**: Model serving and A/B testing

## Architecture

### Service Layers

1. **API Layer** (`backend/api/`)
   - HTTP routes and schemas
   - Request/response handling

2. **Domain Layer** (`backend/domain/`)
   - Business rules and contracts
   - Core domain logic

3. **Services Layer** (`backend/services/`)
   - 18 specialized services
   - Application orchestration

4. **Infrastructure Layer** (`backend/infrastructure/`)
   - External integrations
   - Database and queue clients

### Service Dependencies

```
API Gateway
    ↓
Services Layer (18 services)
    ↓
Domain Layer
    ↓
Infrastructure Layer
```

## Operational Procedures

### Deployment

1. **Pre-deployment Checklist**
   - Run all tests: `pytest`
   - Check lint: `ruff check .`
   - Review logs for errors
   - Verify configuration

2. **Deployment Steps**
   ```bash
   # Build Docker images
   docker-compose build
   
   # Stop existing services
   docker-compose down
   
   # Start new services
   docker-compose up -d
   
   # Verify health
   curl http://localhost:8000/health
   ```

3. **Rollback**
   ```bash
   # Stop current deployment
   docker-compose down
   
   # Start previous version
   docker-compose -f docker-compose.previous.yml up -d
   ```

### Monitoring

### Health Checks

- **Liveness**: `/health/live` - Service is running
- **Readiness**: `/health/ready` - Service is ready to accept traffic
- **Startup**: `/health/startup` - Service is starting up

### Metrics to Monitor

- Request latency (P50, P95, P99)
- Error rate by endpoint
- Database connection pool
- Cache hit rate
- Queue depths
- Service health status

### Alert Thresholds

- P95 latency > 1500ms
- Error rate > 5%
- Database pool exhaustion
- Cache hit rate < 70%
- Queue depth > 1000

### Common Issues

#### High Latency

1. Check database query performance
2. Verify cache hit rate
3. Check connection pool exhaustion
4. Review external service response times

#### High Error Rate

1. Check service logs for errors
2. Verify external service availability
3. Check rate limiting configuration
4. Review authentication/authorization

#### Database Issues

1. Check connection pool settings
2. Verify query performance
3. Check replication lag
4. Review disk space

### Troubleshooting

#### Service Won't Start

1. Check logs: `docker-compose logs <service>`
2. Verify configuration
3. Check dependencies
4. Verify port availability

#### Service Unhealthy

1. Check health endpoint
2. Review service metrics
3. Check dependencies
4. Verify external connectivity

#### Memory Issues

1. Check memory usage: `docker stats`
2. Review connection pools
3. Check for memory leaks
4. Verify cache configuration

## Service-Specific Runbooks

### Multi-Tenant Service

#### Quota Exhaustion

Symptoms: Users getting 429 errors

Resolution:
1. Check quota configuration
2. Review metering data
3. Adjust limits if needed
4. Contact tenant for upgrade

### Workflow Orchestrator

#### Workflow Stuck

Symptoms: Workflow not progressing

Resolution:
1. Check workflow state
2. Review task execution logs
3. Verify external dependencies
4. Manually retry or cancel workflow

### Memory Service

#### Search Slow

Symptoms: Vector search latency high

Resolution:
1. Check embedding cache
2. Verify vector index
3. Review database performance
4. Consider cache warming

### ML Runtime

#### Model Loading Failed

Symptoms: Model not available

Resolution:
1. Check model storage
2. Verify model format
3. Review loading logs
4. Reload model

## Security Procedures

### Incident Response

1. **Identify**
   - Determine scope of incident
   - Assess impact
   - Notify stakeholders

2. **Contain**
   - Isolate affected systems
   - Block malicious traffic
   - Preserve evidence

3. **Eradicate**
   - Remove vulnerabilities
   - Patch systems
   - Update configurations

4. **Recover**
   - Restore from backups
   - Verify systems
   - Monitor for recurrence

5. **Learn**
   - Document incident
   - Update procedures
   - Train team

### Security Alerts

- Unauthorized access attempts
- Data exfiltration
- Malware detection
- Configuration changes
- Privilege escalation

## Backup and Recovery

### Database Backups

- **Frequency**: Hourly
- **Retention**: 30 days
- **Location**: Secure storage
- **Encryption**: At rest and in transit

### Recovery Procedures

1. Identify point of failure
2. Select backup to restore
3. Verify backup integrity
4. Execute restore
5. Validate data
6. Update applications

### Disaster Recovery

- **RTO**: 1 hour
- **RPO**: 5 minutes
- **Failover**: Automatic
- **Testing**: Monthly

## Scaling

### Horizontal Scaling

1. Add more service instances
2. Update load balancer
3. Monitor performance
4. Adjust as needed

### Database Scaling

1. Add read replicas
2. Optimize queries
3. Add indexes
4. Partition data

### Cache Scaling

1. Add Redis nodes
2. Configure sharding
3. Monitor hit rate
4. Adjust eviction policy

## Contact Information

### Team Roles

- **Engineering Lead**: System architecture and development
- **Security Lead**: Security policies and incidents
- **Operations Lead**: Deployment and monitoring
- **Product Lead**: Features and requirements

### Escalation

1. **Level 1**: On-call engineer
2. **Level 2**: Team lead
3. **Level 3**: Engineering manager
4. **Level 4**: CTO

## Documentation

- **System Overview**: `docs/SYSTEM_OVERVIEW.md`
- **Production Readiness**: `docs/PRODUCTION_READINESS.md`
- **Project Completion**: `docs/PROJECT_COMPLETION_REPORT.md`
- **Service Documentation**: `docs/services/`
- **Security Documentation**: `docs/security/`
- **Development Setup**: `docs/dev/SETUP.md`

## Appendix

### Environment Variables

Key configuration variables (see `.env.example`):

```
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
JWT_SECRET_KEY=...
ENCRYPTION_KEY=...
```

### Configuration Files

- `docker-compose.yml` - Service orchestration
- `.env` - Environment variables
- `requirements.txt` - Python dependencies
- `pyproject.toml` - Project configuration

### Useful Commands

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs -f

# Run tests
pytest

# Check lint
ruff check .

# Format code
ruff format .
```

---

**Document Version**: 1.0.0
**Last Updated**: 2026-04-22
**Maintained By**: Butler Engineering Team
