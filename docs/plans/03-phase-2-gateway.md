# Phase 2: Gateway & Request Pipeline

> **Status:** Ready for execution  
> **Depends on:** Phase 0 (Foundation), Phase 1 (Auth)  
> **Unlocks:** Phase 3 (Orchestrator)  
> **Source of truth:** `docs/02-services/gateway.md`

---

## Objective

Build the edge control plane that:
- Terminates all external HTTP/WS traffic
- Enforces JWT authentication via JWKS
- Normalizes every request into a canonical `ButlerEnvelope`
- Applies Redis-backed rate limiting (token bucket)
- Enforces idempotency for mutating operations
- Exposes `POST /api/v1/chat` as the primary user-facing endpoint
- Returns all errors as RFC 9457 Problem Details
- NEVER calls Memory or Tools directly — always routes through Orchestrator

---

## Architecture (from `gateway.md`)

```
Client Request
    │
    ▼
┌─────────────────────────────────────────────┐
│ Gateway (Edge Control Plane)                │
│                                             │
│ 1. TLS termination                          │
│ 2. Request ID + timing middleware           │
│ 3. JWT verification (JWKS-backed)           │
│ 4. Rate limiting (Redis token bucket)       │
│ 5. Idempotency check (Redis)               │
│ 6. Normalize → ButlerEnvelope              │
│ 7. Dispatch to Orchestrator                 │
│                                             │
│ NEVER calls: Memory, Tools, ML directy     │
└─────────────────────────────────────────────┘
    │
    ▼
Orchestrator Service
```

---

## Files to Create

| File | Purpose |
|------|---------|
| `services/gateway/auth_middleware.py` | JWT verification via JWKS |
| `services/gateway/rate_limiter.py` | Token bucket rate limiter |
| `services/gateway/idempotency.py` | Idempotent request enforcement |
| `services/gateway/service.py` | GatewayService — envelope building + dispatch |
| `api/routes/gateway.py` | Chat endpoint + health probes |
| `api/schemas/gateway.py` | Chat request/response DTOs |
| `domain/gateway/contracts.py` | Service interface |

---

## Deliverable 1: JWT Auth Middleware

**File:** `services/gateway/auth_middleware.py`

```python
class JWTAuthMiddleware:
    """Verify JWT on every protected request using JWKS public key."""
    
    def __init__(self, jwks_manager: JWKSManager, redis: Redis):
        self._jwks = jwks_manager
        self._redis = redis
    
    async def authenticate(self, authorization: str | None) -> AccountContext:
        """Extract and verify Bearer token, return account context."""
        if not authorization or not authorization.startswith("Bearer "):
            raise GatewayErrors.MISSING_AUTH
        
        token = authorization[7:]
        
        try:
            claims = self._jwks.verify_token(token)
        except jwt.ExpiredSignatureError:
            raise GatewayErrors.TOKEN_EXPIRED
        except jwt.InvalidTokenError:
            raise GatewayErrors.INVALID_TOKEN
        
        # Check session not revoked (Redis check for speed)
        session_id = claims.get("sid")
        if session_id:
            revoked = await self._redis.get(f"session_revoked:{session_id}")
            if revoked:
                raise GatewayErrors.SESSION_REVOKED
        
        return AccountContext(
            account_id=claims["sub"],
            session_id=claims["sid"],
            assurance_level=claims.get("aal", "aal1"),
            token_id=claims.get("jti"),
        )

@dataclass
class AccountContext:
    account_id: str
    session_id: str
    assurance_level: str
    token_id: str | None = None
    device_id: str | None = None
```

**FastAPI Dependency:**
```python
# In core/deps.py — replace Phase 0 stub
async def get_current_account(
    request: Request,
    auth_middleware: JWTAuthMiddleware = Depends(get_auth_middleware),
) -> AccountContext:
    authorization = request.headers.get("Authorization")
    ctx = await auth_middleware.authenticate(authorization)
    # Enrich with device info from headers
    ctx.device_id = request.headers.get("X-Device-ID")
    return ctx
```

---

## Deliverable 2: Rate Limiter

**File:** `services/gateway/rate_limiter.py`

Redis-backed token bucket per the gateway.md spec:

```python
class RateLimiter:
    """Token bucket rate limiter using Redis.
    
    Default: 100 requests per 60 seconds per account.
    Sliding window implementation.
    """
    
    def __init__(self, redis: Redis, max_requests: int = 100, window_seconds: int = 60):
        self._redis = redis
        self._max_requests = max_requests
        self._window = window_seconds
    
    async def check(self, key: str) -> RateLimitResult:
        """Check if request is within rate limit.
        
        Args:
            key: Rate limit key (e.g., account_id or IP).
        
        Returns:
            RateLimitResult with allowed flag and remaining count.
        """
        redis_key = f"ratelimit:{key}"
        now = time.time()
        window_start = now - self._window
        
        pipe = self._redis.pipeline()
        # Remove expired entries
        pipe.zremrangebyscore(redis_key, 0, window_start)
        # Add current request
        pipe.zadd(redis_key, {str(now): now})
        # Count requests in window
        pipe.zcard(redis_key)
        # Set expiry on the key
        pipe.expire(redis_key, self._window)
        
        results = await pipe.execute()
        current_count = results[2]
        
        remaining = max(0, self._max_requests - current_count)
        allowed = current_count <= self._max_requests
        
        if not allowed:
            retry_after = int(self._window - (now - window_start))
            raise GatewayErrors.rate_limited(remaining=0, retry_after=retry_after)
        
        return RateLimitResult(
            allowed=True,
            remaining=remaining,
            limit=self._max_requests,
            reset=int(now + self._window),
        )

@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    limit: int
    reset: int
```

---

## Deliverable 3: Idempotency Enforcement

**File:** `services/gateway/idempotency.py`

```python
class IdempotencyService:
    """Prevent duplicate processing of requests.
    
    Client sends X-Idempotency-Key header.
    If key exists in Redis → return cached response.
    If not → process and cache response.
    """
    
    def __init__(self, redis: Redis, ttl_seconds: int = 86400):
        self._redis = redis
        self._ttl = ttl_seconds
    
    async def check(self, key: str | None) -> CachedResponse | None:
        """Check if idempotency key has been seen."""
        if not key:
            return None
        
        cached = await self._redis.get(f"idempotent:{key}")
        if cached:
            return CachedResponse.from_json(cached)
        return None
    
    async def store(self, key: str, response: dict, status_code: int) -> None:
        """Cache response for idempotency key."""
        if not key:
            return
        
        cached = CachedResponse(body=response, status_code=status_code)
        await self._redis.setex(
            f"idempotent:{key}",
            self._ttl,
            cached.to_json(),
        )
    
    async def acquire_lock(self, key: str) -> bool:
        """Acquire processing lock to prevent concurrent execution."""
        if not key:
            return True
        return await self._redis.set(
            f"idempotent_lock:{key}",
            "1",
            nx=True,  # Only set if not exists
            ex=30,     # 30 second lock timeout
        )
```

---

## Deliverable 4: Gateway Service

**File:** `services/gateway/service.py`

```python
class GatewayService:
    """Edge control plane — builds envelope, dispatches to Orchestrator."""
    
    def __init__(
        self,
        rate_limiter: RateLimiter,
        idempotency: IdempotencyService,
        orchestrator_dispatch: Callable,  # Injected Orchestrator.intake
    ):
        self._rate_limiter = rate_limiter
        self._idempotency = idempotency
        self._dispatch = orchestrator_dispatch
    
    async def handle_chat(
        self,
        message: str,
        session_id: str,
        account: AccountContext,
        request_meta: RequestMeta,
    ) -> ChatResponse:
        """Main entry point — normalize, check, dispatch."""
        
        # 1. Rate limit check
        rate_result = await self._rate_limiter.check(account.account_id)
        
        # 2. Idempotency check
        cached = await self._idempotency.check(request_meta.idempotency_key)
        if cached:
            return cached.to_response()
        
        # 3. Build canonical envelope
        envelope = ButlerEnvelope(
            request_id=request_meta.request_id,
            account_id=account.account_id,
            session_id=session_id,
            device_id=account.device_id,
            channel=request_meta.channel,
            timestamp=datetime.now(UTC),
            trace_id=request_meta.trace_id,
            message=message,
            assurance_level=account.assurance_level,
            rate_limit_remaining=rate_result.remaining,
            idempotency_key=request_meta.idempotency_key,
        )
        
        # 4. Dispatch to Orchestrator
        result = await self._dispatch(envelope)
        
        # 5. Cache and return
        response = ChatResponse(
            response=result.content,
            session_id=session_id,
            request_id=envelope.request_id,
            workflow_id=result.workflow_id,
            actions_taken=result.actions,
        )
        
        await self._idempotency.store(
            request_meta.idempotency_key,
            response.model_dump(),
            200,
        )
        
        return response
```

---

## API Layer

### `api/schemas/gateway.py`

```python
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4096)
    session_id: str = Field(min_length=1, max_length=64)
    attachments: list[dict] = []
    location: dict | None = None

class ChatResponse(BaseModel):
    response: str
    session_id: str
    request_id: str
    workflow_id: str | None = None
    actions_taken: list[dict] = []

class HealthResponse(BaseModel):
    status: str
    checks: dict | None = None
```

### `api/routes/gateway.py`

```python
router = APIRouter(tags=["gateway"])

@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    request: Request,
    account: AccountContext = Depends(get_current_account),
    gateway: GatewayService = Depends(get_gateway_service),
):
    """Main chat endpoint — the primary user entry point."""
    meta = RequestMeta(
        request_id=request.state.request_id,
        channel=request.headers.get("X-Butler-Channel", "api"),
        trace_id=get_trace_id(),
        idempotency_key=request.headers.get("X-Idempotency-Key"),
    )
    return await gateway.handle_chat(
        message=req.message,
        session_id=req.session_id,
        account=account,
        request_meta=meta,
    )

# Health probes
@router.get("/health/live")
async def live():
    return {"status": "ok"}

@router.get("/health/ready")
async def ready(db=Depends(get_db), cache=Depends(get_cache)):
    checks = {}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception:
        checks["database"] = "unhealthy"
    try:
        await cache.ping()
        checks["redis"] = "healthy"
    except Exception:
        checks["redis"] = "unhealthy"
    
    all_healthy = all(v == "healthy" for v in checks.values())
    return {"status": "ready" if all_healthy else "not_ready", "checks": checks}

@router.get("/health/startup")
async def startup():
    return {"status": "ready", "missing_deps": []}
```

---

## Gateway Error Definitions

**File:** `domain/gateway/errors.py`

```python
class GatewayErrors:
    MISSING_AUTH = Problem(
        type="https://docs.butler.lasmoid.ai/problems/missing-auth",
        title="Authorization Required",
        status=401,
        detail="Bearer token required in Authorization header.",
    )
    TOKEN_EXPIRED = Problem(
        type="https://docs.butler.lasmoid.ai/problems/token-expired",
        title="Token Expired",
        status=401,
        detail="The access token has expired. Use refresh endpoint.",
    )
    INVALID_TOKEN = Problem(
        type="https://docs.butler.lasmoid.ai/problems/invalid-token",
        title="Invalid Token",
        status=401,
    )
    SESSION_REVOKED = Problem(
        type="https://docs.butler.lasmoid.ai/problems/session-revoked",
        title="Session Revoked",
        status=401,
    )
    
    @staticmethod
    def rate_limited(remaining: int, retry_after: int) -> Problem:
        return Problem(
            type="https://docs.butler.lasmoid.ai/problems/rate-limited",
            title="Rate Limit Exceeded",
            status=429,
            detail=f"Rate limit exceeded. Retry after {retry_after} seconds.",
            extensions={"retry_after": retry_after, "limit_remaining": remaining},
        )
    
    IDEMPOTENCY_CONFLICT = Problem(
        type="https://docs.butler.lasmoid.ai/problems/idempotency-conflict",
        title="Idempotent Request In Progress",
        status=409,
        detail="This request is already being processed.",
    )
```

---

## Tests

```python
class TestRateLimiter:
    async def test_allows_within_limit(self, rate_limiter):
        result = await rate_limiter.check("user_1")
        assert result.allowed is True
        assert result.remaining == 99
    
    async def test_blocks_when_exceeded(self, rate_limiter):
        for i in range(101):
            try:
                await rate_limiter.check("user_2")
            except Problem as e:
                assert e.status == 429
                assert i == 100

class TestIdempotency:
    async def test_first_request_returns_none(self, idempotency):
        result = await idempotency.check("key_1")
        assert result is None
    
    async def test_cached_response_returned(self, idempotency):
        await idempotency.store("key_2", {"data": "test"}, 200)
        result = await idempotency.check("key_2")
        assert result.body == {"data": "test"}

class TestGatewayService:
    async def test_chat_builds_envelope_and_dispatches(self, gateway_service, mock_orchestrator):
        response = await gateway_service.handle_chat(
            message="Hello",
            session_id="test-session",
            account=AccountContext(account_id="usr_1", session_id="sid_1", assurance_level="aal1"),
            request_meta=RequestMeta(request_id="req_1", channel="api", trace_id="t_1"),
        )
        assert response.response
        mock_orchestrator.intake.assert_called_once()

class TestAuthMiddleware:
    async def test_valid_token_returns_context(self, auth_middleware, jwks_manager):
        token = jwks_manager.sign_access_token({"account_id": "usr_1", "session_id": "sid_1"}, timedelta(hours=1))
        ctx = await auth_middleware.authenticate(f"Bearer {token}")
        assert ctx.account_id == "usr_1"
    
    async def test_missing_header_raises_401(self, auth_middleware):
        with pytest.raises(Problem) as exc:
            await auth_middleware.authenticate(None)
        assert exc.value.status == 401
    
    async def test_expired_token_raises_401(self, auth_middleware, jwks_manager):
        token = jwks_manager.sign_access_token({"account_id": "usr_1", "session_id": "sid_1"}, timedelta(seconds=-1))
        with pytest.raises(Problem) as exc:
            await auth_middleware.authenticate(f"Bearer {token}")
        assert exc.value.status == 401
```

---

## Response Headers (Rate Limit Info)

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1714003200
X-Request-ID: req_abc123
X-Response-Time: 0.045s
```

---

## Verification Checklist

- [ ] `POST /api/v1/chat` with valid JWT → receives response
- [ ] `POST /api/v1/chat` without JWT → 401 with `application/problem+json`
- [ ] `POST /api/v1/chat` with expired JWT → 401
- [ ] Rate limiter triggers at threshold → 429 with `retry_after`
- [ ] Idempotency key returns cached response on duplicate
- [ ] Envelope contains all required fields before dispatch
- [ ] Rate limit headers present in all responses
- [ ] Gateway does NOT import Memory, Tools, or ML modules

---

*Phase 2 complete → Gateway is production-grade → Phase 3 (Orchestrator) can begin.*
