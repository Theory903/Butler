from fastapi import Depends, Request
from redis.asyncio import Redis

from core.deps import get_cache, get_jwks_manager
from domain.auth.contracts import AccountContext
from services.gateway.auth_middleware import JWTAuthMiddleware


async def get_current_user(request: Request, redis: Redis = Depends(get_cache)) -> AccountContext:
    """FastAPI dependency to get authenticated account context.

    Wired to match requirements of MCP server and Gateway routes.
    Avoids circular imports by living in its own deps file.
    """
    auth = JWTAuthMiddleware(jwks=get_jwks_manager(), redis=redis)

    authorization: str | None = request.headers.get("Authorization")
    return await auth.authenticate(authorization)
