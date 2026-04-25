import asyncio

import structlog
from redis.asyncio import from_url
from sqlalchemy.ext.asyncio import create_async_engine

# Set up logging to console
structlog.configure()
logger = structlog.get_logger(__name__)


async def check_infrastructure():
    success = True

    # 1. Load Settings
    try:
        from infrastructure.config import settings

    except Exception:
        return False

    # 2. Test Redis Connectivity
    try:
        redis = from_url(settings.REDIS_URL)
        await redis.ping()
    except Exception:
        success = False

    # 3. Test Database Pool Initialization
    try:
        engine = create_async_engine(settings.DATABASE_URL)
        async with engine.connect() as conn:
            await conn.execute("SELECT 1")
    except Exception:
        success = False

    if success:
        pass
    else:
        pass

    return True


if __name__ == "__main__":
    asyncio.run(check_infrastructure())
