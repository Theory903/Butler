# Phase 0: Foundation & Cross-Cutting Concerns

> **Status:** Ready for execution  
> **Depends on:** Nothing  
> **Unlocks:** Phase 1 (Auth), Phase 2 (Gateway)  
> **Estimated files:** 18 new, 3 modified

---

## Objective

Establish the shared infrastructure that every Butler service depends on:
- RFC 9457 error model
- Canonical request envelope
- Structured logging with trace context
- Database migrations (full Data spec schema)
- Health probe pattern
- Domain abstractions
- Test infrastructure
- Dependency injection

---

## Deliverable 1: RFC 9457 Problem Details

**File:** `backend/core/errors.py`

Every error in Butler MUST follow [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457):

```python
# Core error model
class Problem(Exception):
    """RFC 9457 Problem Details for HTTP APIs."""
    def __init__(
        self,
        type: str,           # URI reference: https://docs.butler.lasmoid.ai/problems/{slug}
        title: str,          # Human-readable summary
        status: int,         # HTTP status code
        detail: str = None,  # Human-readable explanation
        instance: str = None, # URI of the specific occurrence
        extensions: dict = None  # Additional members
    )

# Service-specific error codes
class AuthProblem:
    INVALID_CREDENTIALS = Problem(type="...", title="Invalid Credentials", status=401)
    EMAIL_TAKEN = Problem(type="...", title="Email Already Registered", status=409)
    TOKEN_EXPIRED = Problem(type="...", title="Token Expired", status=401)
    TOKEN_FAMILY_COMPROMISED = Problem(type="...", title="Token Family Compromised", status=401)

class GatewayProblem:
    RATE_LIMITED = Problem(type="...", title="Rate Limit Exceeded", status=429)
    IDEMPOTENCY_CONFLICT = Problem(type="...", title="Idempotent Request Already Processed", status=409)
    MISSING_AUTH = Problem(type="...", title="Authorization Required", status=401)
```

**Response shape (always):**
```json
{
  "type": "https://docs.butler.lasmoid.ai/problems/rate-limited",
  "title": "Rate Limit Exceeded",
  "status": 429,
  "detail": "You have exceeded 100 requests per 60 seconds",
  "instance": "/api/v1/chat",
  "retry_after": 42
}
```

**FastAPI integration:**
```python
# In core/middleware.py — global exception handler
@app.exception_handler(Problem)
async def problem_handler(request: Request, exc: Problem) -> JSONResponse:
    body = {
        "type": exc.type,
        "title": exc.title,
        "status": exc.status,
        "detail": exc.detail,
        "instance": str(request.url.path),
    }
    if exc.extensions:
        body.update(exc.extensions)
    return JSONResponse(
        status_code=exc.status,
        content=body,
        media_type="application/problem+json",
    )
```

---

## Deliverable 2: Canonical Butler Envelope

**File:** `backend/core/envelope.py`

Every inbound request is normalized into this envelope before reaching the Orchestrator:

```python
class ButlerEnvelope(BaseModel):
    """Canonical request envelope — the contract between Gateway and Orchestrator."""
    request_id: str             # UUID, generated at Gateway
    account_id: str             # From JWT subject
    session_id: str             # From JWT sid claim
    device_id: str | None       # From JWT or header
    channel: str                # mobile | web | watch | voice | api
    timestamp: datetime         # When Gateway received the request
    trace_id: str               # OpenTelemetry trace ID
    
    # Payload
    message: str                # User's raw input
    message_type: str = "text"  # text | voice | image | command
    attachments: list[dict] = []
    
    # Context hints
    location: dict | None = None
    client_version: str | None = None
    idempotency_key: str | None = None
    
    # Internal routing (set by Gateway, not by client)
    assurance_level: str = "aal1"
    rate_limit_remaining: int | None = None
```

---

## Deliverable 3: Structured Logging

**File:** `backend/core/logging.py`

```python
import structlog
from opentelemetry import trace

def setup_logging(service_name: str, environment: str):
    """Configure structlog with OTel trace context injection."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_trace_context,           # Inject trace_id, span_id
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )

def add_trace_context(logger, method_name, event_dict):
    """Inject OTel trace context into every log entry."""
    span = trace.get_current_span()
    if span.is_recording():
        ctx = span.get_span_context()
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict
```

---

## Deliverable 4: Health Probe Mixin

**File:** `backend/core/health.py`

Every service gets three health endpoints per docs spec:

```python
from enum import Enum

class HealthState(str, Enum):
    STARTING = "starting"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

class HealthCheck:
    """Four-state health model from docs/AGENTS.md."""
    
    async def check_live(self) -> dict:
        """Simple alive check — no dependencies."""
        return {"status": "ok"}
    
    async def check_ready(self, deps: dict) -> dict:
        """Full readiness — checks DB, Redis, etc."""
        results = {}
        all_healthy = True
        for name, checker in deps.items():
            try:
                await checker()
                results[name] = "healthy"
            except Exception as e:
                results[name] = f"unhealthy: {e}"
                all_healthy = False
        return {
            "status": "ready" if all_healthy else "not_ready",
            "checks": results,
        }
    
    async def check_startup(self) -> dict:
        """Startup probe — dependency availability."""
        return {"status": "starting"}
```

Router factory:
```python
def create_health_router(prefix: str, deps: dict) -> APIRouter:
    """Create health probe routes for any service."""
    router = APIRouter(prefix=prefix, tags=["health"])
    health = HealthCheck()
    
    @router.get("/health/live")
    async def live():
        return await health.check_live()
    
    @router.get("/health/ready")
    async def ready():
        return await health.check_ready(deps)
    
    @router.get("/health/startup")
    async def startup():
        return await health.check_startup()
    
    return router
```

---

## Deliverable 5: Domain Base Classes

**File:** `backend/domain/base.py`

```python
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")

class DomainService(ABC):
    """Base class for all domain service contracts."""
    pass

class Repository(ABC, Generic[T]):
    """Base repository contract — domain defines, infrastructure implements."""
    
    @abstractmethod
    async def get_by_id(self, id: str) -> T | None: ...
    
    @abstractmethod
    async def save(self, entity: T) -> T: ...
    
    @abstractmethod
    async def delete(self, id: str) -> bool: ...
```

---

## Deliverable 6: Dependency Injection

**File:** `backend/core/deps.py`

```python
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from infrastructure.database import get_session
from infrastructure.cache import get_redis

async def get_db(session: AsyncSession = Depends(get_session)) -> AsyncSession:
    """Inject database session."""
    return session

async def get_cache():
    """Inject Redis client."""
    return await get_redis()

async def get_current_account(request: Request) -> dict:
    """Extract and validate JWT from Authorization header.
    Returns account context dict with account_id, session_id, assurance_level.
    Implemented fully in Phase 2 (Gateway auth middleware).
    """
    # Phase 0 stub — Phase 2 provides real implementation
    raise NotImplementedError("Implement in Phase 2")
```

---

## Deliverable 7: Middleware Stack

**File:** `backend/core/middleware.py`

```python
import uuid
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class RequestContextMiddleware(BaseHTTPMiddleware):
    """Inject request_id, measure timing, set CORS headers."""
    
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        
        start = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - start
        
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration:.3f}s"
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        return response
```

---

## Deliverable 8: Database Migrations (Full Data Spec)

**Setup:** Alembic with async PostgreSQL

```
backend/alembic.ini
backend/alembic/env.py
backend/alembic/versions/001_initial_schema.py
```

The initial migration implements the **complete schema from `docs/02-services/data.md`**:

### Identity/Auth Domain
- `accounts` — with RFC 5321 email constraint, soft-delete, settings JSONB
- `identities` — multi-provider, unique(account_id, identity_type, identifier)
- `sessions` — device binding, assurance levels, risk scoring, workflow linkage
- `refresh_token_families` — rotation tracking, compromise detection

### Runtime Domain
- `workflows` — plan schema, versioning, tags
- `tasks` — durable execution with state machine, compensation linkage
- `task_nodes` — plan node structure per task
- `task_transitions` — event-sourced trail, **partitioned by month**
- `approval_requests` — type, expiry, step-up auth linkage

### Tool/Audit Domain
- `tool_executions` — risk tier, verification, compensation
- `audit_events` — **partitioned by month**, sensitivity classes
- `outbox_events` — transactional outbox, **partitioned by month**

### Config Domain
- `user_settings` — per-user preferences
- `feature_flags` — runtime feature toggles

---

## Deliverable 9: Test Infrastructure

**Files:**
```
backend/tests/__init__.py
backend/tests/conftest.py           ← Test DB, fixtures, Redis mock
backend/tests/factories.py          ← Account, Session, Task factories
backend/tests/unit/__init__.py
backend/tests/integration/__init__.py
```

```python
# conftest.py (key fixtures)
@pytest.fixture
async def db_session():
    """Isolated test database session with rollback."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_factory() as session:
        yield session
        await session.rollback()

@pytest.fixture
def mock_redis():
    """In-memory Redis mock using fakeredis."""
    return fakeredis.aioredis.FakeRedis()

@pytest.fixture
def auth_headers(account_factory, jwks_manager):
    """Pre-authenticated request headers."""
    account = account_factory.create()
    token = jwks_manager.sign_token({"sub": str(account.id), "sid": "test-session"}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}
```

---

## Deliverable 10: Updated main.py

**File:** `backend/main.py` — Rewrite as pure assembly

```python
"""Butler main entrypoint — wire all services together."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infrastructure.config import settings
from infrastructure.database import init_db, close_db
from infrastructure.cache import redis_client
from core.middleware import RequestContextMiddleware
from core.errors import problem_exception_handler, Problem
from core.logging import setup_logging

# Route imports (added per phase)
from api.routes.auth import router as auth_router
from api.routes.gateway import router as gateway_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.SERVICE_NAME, settings.ENVIRONMENT)
    await init_db()
    await redis_client.connect()
    yield
    await redis_client.disconnect()
    await close_db()

app = FastAPI(
    title="Butler API",
    version=settings.SERVICE_VERSION,
    lifespan=lifespan,
)

# Middleware stack
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# RFC 9457 error handler
app.add_exception_handler(Problem, problem_exception_handler)

# Routes
app.include_router(auth_router, prefix="/api/v1")
app.include_router(gateway_router, prefix="/api/v1")
```

---

## Modified Files

| File | Change |
|------|--------|
| `pyproject.toml` | Add `alembic`, `fakeredis`, `opentelemetry-*`, `structlog` deps |
| `infrastructure/config.py` | Add `ALLOWED_ORIGINS`, `OTEL_ENDPOINT` settings |
| `infrastructure/database.py` | Add `test_engine` for isolated test DB |

---

## Verification Checklist

- [ ] `ruff check backend/` — zero errors
- [ ] `pytest backend/tests/` — all pass
- [ ] `alembic upgrade head` — schema created successfully
- [ ] `alembic downgrade -1` — rollback works
- [ ] RFC 9457 error handler returns `application/problem+json` content type
- [ ] Health endpoints respond at `/api/v1/health/{live,ready,startup}`
- [ ] Structured logs include `trace_id` and `span_id`
- [ ] Request ID propagates through `X-Request-ID` header

---

## File Creation Order

1. `core/__init__.py`
2. `core/errors.py`
3. `core/envelope.py`
4. `core/logging.py`
5. `core/health.py`
6. `domain/base.py`
7. `core/deps.py`
8. `core/middleware.py`
9. `api/__init__.py` + `api/schemas/__init__.py` + `api/schemas/common.py`
10. `alembic.ini` + `alembic/env.py` + `alembic/versions/001_initial_schema.py`
11. `tests/conftest.py` + `tests/factories.py`
12. Update `main.py`
13. Update `pyproject.toml`
14. Update `infrastructure/config.py`

---

*After Phase 0, every subsequent phase inherits: error model, envelope, logging, health, migrations, and test infrastructure.*
