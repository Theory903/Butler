# Phase 1: Auth & Identity Platform

> **Status:** Ready for execution  
> **Depends on:** Phase 0 (Foundation)  
> **Unlocks:** Phase 2 (Gateway)  
> **Source of truth:** `docs/02-services/auth.md`, `docs/02-services/data.md`

---

## Objective

Build a production-grade identity platform implementing:
- Account lifecycle with soft-delete
- Multi-identity support (password + passkey + OIDC stubs)
- RS256 JWT issuance with full JWKS RFC 7517 document
- Token family rotation with reuse detection
- Session management with device binding and assurance levels
- Argon2id password hashing (OWASP minimum)
- Clean domain/service/route separation

---

## Domain Layer: `domain/auth/`

### `domain/auth/models.py` — Enrich Existing

Add missing fields from the `data.md` spec to existing models:

```python
# Account — add:
status: Mapped[str]          # active, suspended, deleted
display_name: Mapped[str]
settings: Mapped[dict]       # JSONB — user preferences
deleted_at: Mapped[datetime]  # Soft-delete support

# Identity — add:
identity_type: Mapped[str]   # password, passkey, google, apple, github
identifier: Mapped[str]      # email, provider subject, etc.
verified_at: Mapped[datetime]

# Session — add:
ip_address: Mapped[str]
user_agent: Mapped[str]
revoked_at: Mapped[datetime]
risk_score: Mapped[float]
```

### `domain/auth/contracts.py` — Service Interface

```python
from abc import ABC, abstractmethod

class AuthServiceContract(ABC):
    """Auth domain service interface — what the service CAN do."""
    
    @abstractmethod
    async def register(self, email: str, password: str) -> tuple[Account, str]:
        """Create account, identity, session. Returns (account, access_token)."""
    
    @abstractmethod
    async def login(self, email: str, password: str, device_id: str | None) -> TokenPair:
        """Authenticate and issue tokens."""
    
    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> TokenPair:
        """Rotate refresh token. Detect family reuse."""
    
    @abstractmethod
    async def logout(self, session_id: str) -> None:
        """Revoke session and all associated token families."""
    
    @abstractmethod
    async def get_jwks(self) -> dict:
        """Return JWKS document with RSA public key material."""
    
    @abstractmethod
    async def verify_token(self, token: str) -> dict:
        """Verify JWT and return claims."""
    
    @abstractmethod
    async def get_session(self, session_id: str) -> Session | None:
        """Get session by ID."""
    
    @abstractmethod
    async def revoke_all_sessions(self, account_id: str) -> int:
        """Revoke all sessions for an account. Returns count revoked."""
```

### `domain/auth/exceptions.py` — Auth-Specific Errors

```python
from core.errors import Problem

class AuthErrors:
    INVALID_CREDENTIALS = Problem(
        type="https://docs.butler.lasmoid.ai/problems/invalid-credentials",
        title="Invalid Credentials",
        status=401,
        detail="The email or password provided is incorrect.",
    )
    EMAIL_ALREADY_REGISTERED = Problem(
        type="https://docs.butler.lasmoid.ai/problems/email-taken",
        title="Email Already Registered",
        status=409,
        detail="An account with this email already exists.",
    )
    TOKEN_EXPIRED = Problem(
        type="https://docs.butler.lasmoid.ai/problems/token-expired",
        title="Token Expired",
        status=401,
        detail="The provided token has expired.",
    )
    TOKEN_FAMILY_COMPROMISED = Problem(
        type="https://docs.butler.lasmoid.ai/problems/token-reuse",
        title="Token Family Compromised",
        status=401,
        detail="Refresh token reuse detected. All sessions in this family have been revoked.",
    )
    SESSION_REVOKED = Problem(
        type="https://docs.butler.lasmoid.ai/problems/session-revoked",
        title="Session Revoked",
        status=401,
        detail="This session has been revoked.",
    )
    INVALID_TOKEN = Problem(
        type="https://docs.butler.lasmoid.ai/problems/invalid-token",
        title="Invalid Token",
        status=401,
        detail="The provided token is invalid or malformed.",
    )
```

---

## Service Layer: `services/auth/`

### `services/auth/password.py` — Argon2id Hasher

```python
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

class PasswordService:
    """Argon2id password hashing per OWASP guidelines."""
    
    def __init__(self):
        self._hasher = PasswordHasher(
            time_cost=2,        # OWASP minimum
            memory_cost=19456,   # ~19 MB
            parallelism=1,
        )
    
    def hash(self, password: str) -> str:
        return self._hasher.hash(password)
    
    def verify(self, password: str, hash: str) -> bool:
        try:
            return self._hasher.verify(hash, password)
        except VerifyMismatchError:
            return False
    
    def needs_rehash(self, hash: str) -> bool:
        return self._hasher.check_needs_rehash(hash)
```

### `services/auth/jwt.py` — Rewrite with Full JWKS

The existing JWT module is incomplete. Rewrite with:

```python
class JWKSManager:
    """RS256 JWT signing with RFC 7517 JWKS document."""
    
    def __init__(self, private_key_pem: str, key_id: str):
        self._private_key = load_pem_private_key(private_key_pem.encode(), password=None)
        self._public_key = self._private_key.public_key()
        self._key_id = key_id
    
    def sign_access_token(self, claims: dict, ttl: timedelta) -> str:
        """Issue short-lived access token."""
        payload = {
            "sub": claims["account_id"],
            "sid": claims["session_id"],
            "aal": claims.get("assurance_level", "aal1"),
            "iss": "https://butler.lasmoid.ai",
            "aud": "https://butler.lasmoid.ai",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + ttl,
            "jti": str(uuid4()),
        }
        return jwt.encode(payload, self._private_key, algorithm="RS256", headers={"kid": self._key_id})
    
    def sign_refresh_token(self, claims: dict, family_id: str, ttl: timedelta) -> str:
        """Issue refresh token bound to token family."""
        payload = {
            "sub": claims["account_id"],
            "sid": claims["session_id"],
            "fid": family_id,  # Token family ID
            "typ": "refresh",
            "iss": "https://butler.lasmoid.ai",
            "aud": "https://butler.lasmoid.ai",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + ttl,
            "jti": str(uuid4()),
        }
        return jwt.encode(payload, self._private_key, algorithm="RS256", headers={"kid": self._key_id})
    
    def verify_token(self, token: str) -> dict:
        """Verify and decode JWT using public key."""
        return jwt.decode(
            token,
            self._public_key,
            algorithms=["RS256"],
            issuer="https://butler.lasmoid.ai",
            audience="https://butler.lasmoid.ai",
        )
    
    def get_jwks_document(self) -> dict:
        """Return RFC 7517 JWKS document with full RSA public key material."""
        public_numbers = self._public_key.public_numbers()
        n_bytes = public_numbers.n.to_bytes((public_numbers.n.bit_length() + 7) // 8, "big")
        e_bytes = public_numbers.e.to_bytes((public_numbers.e.bit_length() + 7) // 8, "big")
        
        return {
            "keys": [{
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": self._key_id,
                "n": base64url_encode(n_bytes),
                "e": base64url_encode(e_bytes),
            }]
        }
```

### `services/auth/service.py` — AuthService Implementation

```python
class AuthService(AuthServiceContract):
    """Production-grade auth service with token family rotation detection."""
    
    def __init__(self, db: AsyncSession, redis: Redis, jwks: JWKSManager, passwords: PasswordService):
        self._db = db
        self._redis = redis
        self._jwks = jwks
        self._passwords = passwords
    
    async def register(self, email: str, password: str) -> tuple[Account, str]:
        # 1. Check email not taken
        existing = await self._db.execute(select(Account).where(Account.email == email))
        if existing.scalar_one_or_none():
            raise AuthErrors.EMAIL_ALREADY_REGISTERED
        
        # 2. Create account
        account = Account(email=email, status="active")
        self._db.add(account)
        
        # 3. Create password identity
        identity = Identity(
            account_id=account.id,
            identity_type="password",
            identifier=email,
            password_hash=self._passwords.hash(password),
        )
        self._db.add(identity)
        
        # 4. Create session
        session = Session(
            account_id=account.id,
            auth_method="password",
            assurance_level="aal1",
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        self._db.add(session)
        
        # 5. Create token family
        family = TokenFamily(session_id=session.id)
        self._db.add(family)
        
        await self._db.flush()
        
        # 6. Issue tokens
        access = self._jwks.sign_access_token(
            {"account_id": str(account.id), "session_id": str(session.id)},
            timedelta(minutes=15),
        )
        refresh = self._jwks.sign_refresh_token(
            {"account_id": str(account.id), "session_id": str(session.id)},
            str(family.id),
            timedelta(days=7),
        )
        
        await self._db.commit()
        return account, TokenPair(access_token=access, refresh_token=refresh)
    
    async def refresh_token(self, refresh_token: str) -> TokenPair:
        # 1. Decode and verify
        claims = self._jwks.verify_token(refresh_token)
        if claims.get("typ") != "refresh":
            raise AuthErrors.INVALID_TOKEN
        
        family_id = claims["fid"]
        
        # 2. Check token family is still valid
        family = await self._db.get(TokenFamily, family_id)
        if not family or family.invalidated_at:
            raise AuthErrors.TOKEN_FAMILY_COMPROMISED
        
        # 3. Check rotation counter matches (detect reuse)
        jti = claims["jti"]
        used = await self._redis.get(f"refresh_used:{jti}")
        if used:
            # REUSE DETECTED — revoke entire family
            family.invalidated_at = datetime.now(UTC)
            await self._db.commit()
            raise AuthErrors.TOKEN_FAMILY_COMPROMISED
        
        # 4. Mark current token as used
        await self._redis.setex(f"refresh_used:{jti}", 7 * 86400, "1")
        
        # 5. Bump rotation counter
        family.rotation_counter += 1
        await self._db.commit()
        
        # 6. Issue new token pair
        access = self._jwks.sign_access_token(
            {"account_id": claims["sub"], "session_id": claims["sid"]},
            timedelta(minutes=15),
        )
        refresh = self._jwks.sign_refresh_token(
            {"account_id": claims["sub"], "session_id": claims["sid"]},
            str(family.id),
            timedelta(days=7),
        )
        
        return TokenPair(access_token=access, refresh_token=refresh)
```

---

## API Layer: `api/routes/auth.py` + `api/schemas/auth.py`

### Schemas

```python
# api/schemas/auth.py
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 900  # 15 minutes

class AccountResponse(BaseModel):
    id: str
    email: str
    status: str
    created_at: datetime
```

### Routes

```python
# api/routes/auth.py — THIN layer, no business logic
router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest, auth: AuthService = Depends(get_auth_service)):
    account, tokens = await auth.register(req.email, req.password)
    return tokens

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, auth: AuthService = Depends(get_auth_service)):
    tokens = await auth.login(req.email, req.password)
    return tokens

@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, auth: AuthService = Depends(get_auth_service)):
    tokens = await auth.refresh_token(req.refresh_token)
    return tokens

@router.post("/logout", status_code=204)
async def logout(account: dict = Depends(get_current_account), auth: AuthService = Depends(get_auth_service)):
    await auth.logout(account["session_id"])

@router.get("/.well-known/jwks.json")
async def jwks(auth: AuthService = Depends(get_auth_service)):
    return await auth.get_jwks()
```

---

## Tests: `tests/unit/test_auth_service.py`

```python
class TestAuthService:
    async def test_register_creates_account_and_tokens(self, auth_service, db_session):
        account, tokens = await auth_service.register("new@test.com", "Password123!")
        assert account.email == "new@test.com"
        assert tokens.access_token
        assert tokens.refresh_token
    
    async def test_register_duplicate_email_raises_409(self, auth_service, db_session):
        await auth_service.register("dup@test.com", "Password123!")
        with pytest.raises(Problem) as exc:
            await auth_service.register("dup@test.com", "Password123!")
        assert exc.value.status == 409
    
    async def test_login_with_correct_password(self, auth_service, db_session):
        await auth_service.register("login@test.com", "Password123!")
        tokens = await auth_service.login("login@test.com", "Password123!")
        assert tokens.access_token
    
    async def test_login_with_wrong_password_raises_401(self, auth_service, db_session):
        await auth_service.register("login@test.com", "Password123!")
        with pytest.raises(Problem) as exc:
            await auth_service.login("login@test.com", "WrongPass!")
        assert exc.value.status == 401
    
    async def test_refresh_token_rotation(self, auth_service, db_session):
        _, tokens1 = await auth_service.register("r@test.com", "Password123!")
        tokens2 = await auth_service.refresh_token(tokens1.refresh_token)
        assert tokens2.access_token != tokens1.access_token
    
    async def test_refresh_token_reuse_revokes_family(self, auth_service, db_session):
        _, tokens1 = await auth_service.register("r2@test.com", "Password123!")
        await auth_service.refresh_token(tokens1.refresh_token)
        with pytest.raises(Problem) as exc:
            await auth_service.refresh_token(tokens1.refresh_token)  # REUSE
        assert exc.value.status == 401
        assert "Compromised" in exc.value.title

class TestJWKS:
    def test_jwks_document_has_required_fields(self, jwks_manager):
        doc = jwks_manager.get_jwks_document()
        key = doc["keys"][0]
        assert key["kty"] == "RSA"
        assert key["alg"] == "RS256"
        assert "n" in key  # RSA modulus
        assert "e" in key  # RSA exponent
        assert "kid" in key
    
    def test_sign_and_verify_roundtrip(self, jwks_manager):
        token = jwks_manager.sign_access_token({"account_id": "test", "session_id": "sid"}, timedelta(hours=1))
        claims = jwks_manager.verify_token(token)
        assert claims["sub"] == "test"
        assert claims["sid"] == "sid"

class TestPasswordService:
    def test_hash_and_verify(self):
        svc = PasswordService()
        h = svc.hash("test-password")
        assert svc.verify("test-password", h) is True
        assert svc.verify("wrong-password", h) is False
    
    def test_argon2id_format(self):
        svc = PasswordService()
        h = svc.hash("test")
        assert h.startswith("$argon2id$")
```

---

## Verification Checklist

- [ ] Register creates account + identity + session + token family in DB
- [ ] Login verifies Argon2id hash and issues RS256 JWT
- [ ] Access token contains: sub, sid, aal, iss, aud, iat, exp, jti
- [ ] JWKS endpoint returns RFC 7517 with n, e, kty, alg, kid
- [ ] Token refresh increments family rotation_counter
- [ ] Refresh token reuse → revoke family → 401
- [ ] Logout revokes session
- [ ] All errors return `application/problem+json`
- [ ] Domain auth models have NO FastAPI imports
- [ ] Route handlers contain NO business logic

---

## Dependencies to Add (pyproject.toml)

```toml
argon2-cffi = ">=23.1"
pyjwt = { extras = ["crypto"], version = ">=2.8" }
pydantic = { extras = ["email"], version = ">=2.6" }
```

---

*Phase 1 complete → Auth is production-grade → Phase 2 (Gateway) can begin.*
