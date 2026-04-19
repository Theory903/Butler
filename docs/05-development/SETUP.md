# Development Setup Guide

> **For:** Engineers
> **Version:** 4.0
> **Last Updated:** 2026-04-18

---

## Prerequisites

### Required Software

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Backend runtime |
| Node.js | 20+ | Mobile app |
| Docker | Latest | Containers |
| Docker Compose | Latest | Service orchestration |
| Git | Latest | Version control |

### Recommended Tools

| Tool | Purpose |
|------|---------|
| pyenv | Python version management |
| direnv | Environment variable loading |
| VS Code | IDE with Pylance |
| TablePlus | PostgreSQL GUI |

---

## Quick Start (5 minutes)

### 1. Clone and Enter

```bash
git clone git@github.com:yourorg/Butler.git
cd Butler
```

### 2. Create Environment File

```bash
cp .env.example .env
# Edit .env with your local values
```

### 3. Start Services

```bash
docker-compose up -d
```

### 4. Verify

```bash
# Health check
curl http://localhost:8000/health

# API docs
open http://localhost:8000/docs
```

---

## Project Structure

```
Butler/
├── app/                    # React Native (Expo) mobile app
├── backend/                # FastAPI backend
│   ├── api/               # HTTP routes
│   ├── domain/            # Business logic
│   ├── services/          # Service implementations
│   ├── infrastructure/    # DB, cache, external APIs
│   └── tests/            # Test suite
├── docs/                  # Documentation
├── docker-compose.yml     # Service orchestration
└── .env                  # Environment variables
```

---

## Backend Setup

### Python Virtual Environment

```bash
# Create virtual environment
cd backend
python -m venv .venv

# Activate (macOS/Linux)
source .venv/bin/activate

# Activate (Windows)
.venv\Scripts\activate.bat

# Install dependencies
pip install -r requirements.txt

# Install dev dependencies
pip install -r requirements-dev.txt
```

### Database Setup

```bash
# Run migrations
alembic upgrade head

# Seed initial data (optional)
python -m Butler.scripts.seed
```

### Environment Variables

```bash
# .env file
DATABASE_URL=postgresql://butler:butler@localhost:5432/butler
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-secret-key-change-in-production
JWT_ALGORITHM=RS256
LOG_LEVEL=DEBUG
```

---

## Mobile App Setup

### Prerequisites

```bash
# Install Expo CLI
npm install -g expo

# Install dependencies
cd app
npm install
```

### Run Development

```bash
# Start Metro bundler
npx expo start

# Or run on iOS simulator
npx expo start --ios

# Or run on Android emulator
npx expo start --android

# Or run with tunnel (for physical device)
npx expo start --tunnel
```

---

## Running the Full System

### Option 1: Docker Compose (Recommended)

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f api

# Stop all services
docker-compose down
```

### Option 2: Backend Only (for API development)

```bash
# Activate virtual environment
cd backend
source .venv/bin/activate

# Run with hot reload
uvicorn Butler.main:app --reload --port 8000
```

### Option 3: Backend + External Services

```bash
# Start only infrastructure services
docker-compose up -d postgres redis

# Run backend locally
cd backend
source .venv/bin/activate
uvicorn Butler.main:app --reload --port 8000
```

---

## Testing

### Run All Tests

```bash
# Backend tests
cd backend
pytest

# With coverage
pytest --cov=Butler --cov-report=html
```

### Run Specific Tests

```bash
# Unit tests only
pytest tests/unit/

# Integration tests
pytest tests/integration/

# Single test file
pytest tests/unit/test_auth.py

# Single test
pytest tests/unit/test_auth.py::test_login
```

### Mobile Tests

```bash
cd app
npm test
```

---

## Linting and Formatting

### Backend

```bash
# Lint
cd backend
ruff check .

# Format
ruff format .

# Type check
pyright Butler
```

### Mobile

```bash
cd app
npm run lint
npm run format
```

---

## Common Issues

### "Database connection refused"

```bash
# Check if PostgreSQL is running
docker-compose ps

# Restart container
docker-compose restart postgres
```

### "Module not found"

```bash
# Reinstall dependencies
pip install -r requirements.txt

# Or recreate venv
rm -rf .venv
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### "Port already in use"

```bash
# Find process using port 8000
lsof -i :8000

# Kill process
kill -9 <PID>

# Or use different port
uvicorn Butler.main:app --port 8001
```

### "Apple Simulator not found"

```bash
# List available simulators
xcrun simctl list devices available

# Boot a simulator
xcrun simctl boot "iPhone 15 Pro"
```

---

## IDE Setup

### VS Code (Recommended)

Extensions to install:
- Python (Microsoft)
- Ruff (charliermarsh)
- Prettier (Esben Petersen)
- Docker (Microsoft)
- SQLite (alexcvzz)

Settings (`settings.json`):

```json
{
  "python.defaultInterpreterPath": "./backend/.venv/bin/python",
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "ruff",
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff"
  }
}
```

---

## Next Steps

1. **Read the architecture**: [architecture.md](./architecture.md)
2. **Understand the build order**: [build-order.md](./build-order.md)
3. **Learn run commands**: [run-local.md](./run-local.md)
4. **Contribute**: See [CONTRIBUTING.md](../CONTRIBUTING.md)

---

## Support

| Channel | Link |
|---------|------|
| Engineering | #butler-engineering |
| Discord | discord.gg/butler |
| Issues | github.com/yourorg/Butler/issues |

*Setup guide owner: Platform Team*
*Version: 4.0*