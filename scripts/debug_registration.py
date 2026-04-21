import asyncio
import uuid
import sys
import os
from datetime import datetime, timezone

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from infrastructure.database import async_session_factory
from infrastructure.cache import get_redis
from services.auth.service import AuthService
from services.auth.password import PasswordService

from services.auth.jwt import get_jwks_manager

async def debug_register():
    print("Connecting to DB...")
    async with async_session_factory() as db:
        print("Connecting to Redis...")
        redis = await get_redis()
        
        jwks = get_jwks_manager()
        passwords = PasswordService()
        
        service = AuthService(db=db, redis=redis, jwks=jwks, passwords=passwords)
        
        test_email = f"debug_{uuid.uuid4().hex[:8]}@example.com"
        test_password = "Password123!"
        
        print(f"Attempting to register {test_email}...")
        try:
            tokens = await service.register(
                email=test_email,
                password=test_password,
                display_name="Debug User"
            )
            print(f"SUCCESS: {tokens}")
        except Exception as e:
            print("FAILURE during registration!")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_register())
