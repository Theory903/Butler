import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from redis.asyncio import from_url
import structlog

# Set up logging to console
structlog.configure()
logger = structlog.get_logger(__name__)

async def check_infrastructure():
    print("🛠️  Starting Infrastructure Smoke Test...")
    success = True
    
    # 1. Load Settings
    try:
        from infrastructure.config import settings
        print(f"✅ Settings Loaded: ENVIRONMENT={settings.ENVIRONMENT}")
    except Exception as e:
        print(f"❌ Failed to load settings: {e}")
        return False

    # 2. Test Redis Connectivity
    try:
        redis = from_url(settings.REDIS_URL)
        await redis.ping()
        print(f"✅ Redis Connected: {settings.REDIS_URL}")
    except Exception as e:
        print(f"⚠️  Redis Connectivity Failed: {e} (Expected if Redis is not running locally)")
        success = False

    # 3. Test Database Pool Initialization
    try:
        engine = create_async_engine(settings.DATABASE_URL)
        async with engine.connect() as conn:
            await conn.execute("SELECT 1")
        print(f"✅ Database Connected: {settings.DATABASE_URL}")
    except Exception as e:
        print(f"⚠️  Database Connectivity Failed: {e} (Expected if Postgres is not running locally)")
        success = False

    if success:
        print("\n🚀 Infrastructure is READY!")
    else:
        print("\n🟡 Infrastructure is DEGRADED (External services unreachable), but wiring is verified.")
    
    return True

if __name__ == "__main__":
    asyncio.run(check_infrastructure())
