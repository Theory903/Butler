# Development Guide

> **For:** Engineers
> **Version:** 4.0
> **Last Updated:** 2026-04-18

---

## Getting Started

### Quick Start

1. **Setup**: [SETUP.md](./SETUP.md)
2. **Build order**: [build-order.md](./build-order.md)
3. **Run locally**: [run-local.md](./run-local.md)

---

## Core Documents

| Document | Purpose |
|---------|---------|
| [architecture.md](./architecture.md) | Backend architecture overview |
| [SETUP.md](./SETUP.md) | Local development setup |
| [build-order.md](./build-order.md) | Service build sequence |
| [run-local.md](./run-local.md) | Running services locally |

---

## Prerequisites

- Python 3.11+
- Node.js 20+
- Docker + Docker Compose
- PostgreSQL (via Docker)
- Redis (via Docker)

---

## Development Workflow

### 1. Setup

```bash
# Clone and setup
git clone git@github.com:yourorg/Butler.git
cd Butler

# Start infrastructure
docker-compose up -d

# Verify
curl http://localhost:8000/health
```

### 2. Build

Follow the [build-order.md](./build-order.md) sequence:
- Phase 1: Foundation (DB, Auth, Gateway)
- Phase 2: Core (Memory, ML, Tools)
- Phase 3: Orchestration
- Phase 4: Integration
- Phase 5: Advanced

### 3. Test

```bash
# Run tests
cd backend
pytest

# Run with coverage
pytest --cov=Butler --cov-report=html
```

### 4. Contribute

See [CONTRIBUTING.md](../CONTRIBUTING.md)

---

## Common Tasks

### Add a New Service

1. Create directory in `backend/services/`
2. Add routes in `backend/api/routes/`
3. Add schema in `backend/api/schemas/`
4. Write tests in `backend/tests/`
5. Add to docker-compose.yml

### Add a New API Endpoint

1. Define schema in `api/schemas/`
2. Add route in `api/routes/`
3. Implement in domain/service
4. Add tests

### Run Full System

```bash
docker-compose up -d
```

---

## Architecture Overview

See [architecture.md](./architecture.md) for:

- Service structure
- Data flow
- Database schema
- Security model
- Observability

---

## Support

| Channel | Link |
|---------|------|
| Engineering | #butler-engineering |
| Discord | discord.gg/butler |

*Development guide owner: Platform Team*
*Version: 4.0*