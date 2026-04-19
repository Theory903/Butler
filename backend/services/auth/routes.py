"""Auth service routes - login, register, sessions, JWKS."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid

from services.auth.jwt import create_access_token, create_refresh_token, password_hasher, jwks_manager
from domain.auth.models import Account, Identity, Session, TokenFamily
from infrastructure.database import async_session_factory
from sqlalchemy import select

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest):
    async with async_session_factory() as session:
        result = await session.execute(select(Account).where(Account.email == req.email))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already registered")

        account = Account(email=req.email)
        session.add(account)
        await session.flush()

        identity = Identity(
            account_id=account.id,
            provider="password",
            provider_subject=req.email,
            password_hash=password_hasher.hash(req.password),
        )
        session.add(identity)

        session_obj = Session(
            account_id=account.id,
            auth_method="password",
            assurance_level="AAL1",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        session.add(session_obj)
        await session.flush()

        token_family = TokenFamily(session_id=session_obj.id)
        session.add(token_family)
        await session.commit()

        access_token = create_access_token(str(account.id), str(session_obj.id))
        refresh_token = create_refresh_token(str(account.id), str(token_family.id))

        return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    async with async_session_factory() as session:
        result = await session.execute(
            select(Identity, Account)
            .join(Account, Identity.account_id == Account.id)
            .where(Account.email == req.email)
        )
        row = result.first()
        if not row or not row[0].password_hash:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        identity, account = row
        if not password_hasher.verify(req.password, identity.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        session_obj = Session(
            account_id=account.id,
            auth_method="password",
            assurance_level="AAL1",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        session.add(session_obj)
        await session.flush()

        token_family = TokenFamily(session_id=session_obj.id)
        session.add(token_family)
        await session.commit()

        access_token = create_access_token(str(account.id), str(session_obj.id))
        refresh_token = create_refresh_token(str(account.id), str(token_family.id))

        return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(refresh_token: str):
    try:
        from services.auth.jwt import jwks_manager
        payload = jwks_manager.verify_token(refresh_token)
        account_id = payload["sub"]
        token_family_id = payload.get("fam")

        session_id = str(uuid.uuid4())
        access_token = create_access_token(account_id, session_id)
        new_refresh = create_refresh_token(account_id, token_family_id or str(uuid.uuid4()))

        return TokenResponse(access_token=access_token, refresh_token=new_refresh)
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@router.get("/sessions")
async def get_sessions():
    return {"sessions": []}


@router.get("/.well-known/jwks.json")
async def jwks():
    return jwks_manager.jwks_document()