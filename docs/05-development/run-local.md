# Local Run Guide

> **For:** Engineers
> **Version:** 4.0
> **Last Updated:** 2026-04-18

---

## Quick Reference

### Start Everything

```bash
# Docker Compose (recommended)
docker-compose up -d
```

### Stop Everything

```bash
docker-compose down
```

---

## Service Commands

### Backend Services

| Service | Port | Start Command | Health Endpoint |
|---------|------|----------------|------------------|
| Gateway | 8000 | `make run-gateway` | `/health` |
| Auth | 8001 | `make run-auth` | `/health` |
| Orchestrator | 8002 | `make run-orchestrator` | `/health` |
| Memory | 8003 | `make run-memory` | `/health` |
| ML | 8006 | `make run-ml` | `/health` |
| Tools | 8005 | `make run-tools` | `/health` |
| Realtime | 8004 | `make run-realtime` | `/health` |
| Search | 8012 | `make run-search` | `/health` |
| Communication | 8013 | `make run-comms` | `/health` |

### Infrastructure

| Service | Port | Start Command |
|---------|------|----------------|
| PostgreSQL | 5432 | `docker-compose up -d postgres` |
| Redis | 6379 | `docker-compose up -d redis` |
| Qdrant | 6333 | `docker-compose up -d qdrant` |
| Neo4j | 7474 | `docker-compose up -d neo4j` |

---

## Development Modes

### Mode 1: Full Stack (All Services)

```bash
# Start all services including infrastructure
docker-compose up -d

# View all logs
docker-compose logs -f

# Verify all healthy
curl http://localhost:8000/health
```

### Mode 2: Backend Only

```bash
# Start infrastructure only
docker-compose up -d postgres redis

# Activate virtual environment
cd backend
source .venv/bin/activate

# Run gateway with hot reload
uvicorn Butler.main:app --reload --port 8000
```

### Mode 3: Single Service Development

```bash
# Start infrastructure
docker-compose up -d postgres redis

# Run specific service
cd backend
source .venv/bin/activate
uvicorn Butler.services.orchestrator:app --reload --port 8002
```

### Mode 4: Mobile Development

```bash
# Start backend
docker-compose up -d

# Start mobile
cd app
npx expo start --tunnel
```

---

## Common Commands

### Start Services

```bash
# All services
docker-compose up -d

# Specific services
docker-compose up -d postgres redis gateway

# With logs visible
docker-compose up
```

### Stop Services

```bash
# Stop all
docker-compose down

# Stop specific
docker-compose stop postgres

# Stop and remove volumes (clean slate)
docker-compose down -v
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f gateway

# Last 100 lines
docker-compose logs --tail=100 gateway
```

### Restart Services

```bash
# Restart all
docker-compose restart

# Restart specific
docker-compose restart gateway
```

---

## Health Checks

### Check All Services

```bash
#!/bin/bash
echo "Checking services..."
for port in 8000 8001 8002 8003 8004 8005 8006 8012 8013; do
  if curl -s http://localhost:$port/health > /dev/null 2>&1; then
    echo "✓ Port $port OK"
  else
    echo "✗ Port $port FAILED"
  fi
done
```

### Manual Checks

```bash
# Gateway
curl http://localhost:8000/health

# Gateway detailed
curl http://localhost:8000/health/ready

# Auth
curl http://localhost:8001/health

# Orchestrator
curl http://localhost:8002/health
```

---

## Test Commands

### Run Tests

```bash
# All tests
cd backend
pytest

# With coverage
pytest --cov=Butler --cov-report=html

# Watch mode
pytest --watch

# Specific file
pytest tests/services/test_orchestrator.py
```

### Quick Test

```bash
# Login test
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "test123"}'

# Chat test
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"message": "hello"}'
```

---

## Database Commands

### Connect to PostgreSQL

```bash
# Via Docker
docker exec -it butler-postgres psql -U butler -d butler

# Via CLI
psql postgresql://butler:butler@localhost:5432/butler
```

### Run Migrations

```bash
cd backend
alembic upgrade head
```

### Reset Database

```bash
# Drop and recreate
docker-compose down -v
docker-compose up -d postgres
alembic upgrade head
```

---

## Redis Commands

### Connect

```bash
# Via Docker
docker exec -it butler-redis redis-cli

# Via CLI
redis-cli -p 6379
```

### Common Commands

```redis
# Check keys
KEYS *

# Check connection
PING

# Clear all keys (careful!)
FLUSHDB
```

---

## Troubleshooting

### "Connection refused"

```bash
# Check what's running
docker-compose ps

# Check port
lsof -i :8000
```

### "Service not healthy"

```bash
# Check logs
docker-compose logs gateway

# Restart service
docker-compose restart gateway
```

### "Migration failed"

```bash
# Check current version
alembic current

# Check history
alembic history

# Stamp as current (if needed)
alembic stamp head
```

### "Token expired"

```bash
# Get new token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "test123"}'
```

---

## Makefile Commands

```bash
# Show all commands
make help

# Start/stop
make start          # docker-compose up -d
make stop           # docker-compose down
make restart        # docker-compose restart

# Services
make run-gateway    # Run gateway
make run-auth       # Run auth
make run-orch       # Run orchestrator

# Tests
make test           # Run all tests
make test-unit      # Run unit tests
make test-int       # Run integration tests

# Database
make db-migrate     # Run migrations
make db-reset       # Reset database

# Linting
make lint           # Run linter
make format        # Format code
```

---

## Clean Up

```bash
# Remove all containers
docker-compose down

# Remove volumes (all data)
docker-compose down -v

# Remove images
docker system prune -f

# Full reset
make db-reset && docker-compose down -v && docker-compose up -d
```

---

## Next Steps

1. **Setup**: [SETUP.md](./SETUP.md)
2. **Build order**: [build-order.md](./build-order.md)
3. **Architecture**: [architecture.md](./architecture.md)

*Run guide owner: Platform Team*
*Version: 4.0*