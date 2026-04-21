import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check_db():
    db_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://butler:butler@localhost:5432/butler")
    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        print("Connected!")
        res = await conn.execute(text("SELECT extname FROM pg_extension"))
        print("Extensions:", [r[0] for r in res])
        
        try:
            # Check availability
            extensions = ['uuid-ossp', 'pg_trgm', 'vector']
            res = await conn.execute(text("SELECT name FROM pg_available_extensions"))
            available = [r[0] for r in res]
            print("Available extensions in system:", available)
            
            for ext in extensions:
                if ext in available:
                    print(f"{ext} is AVAILABLE")
                    try:
                        await conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS \"{ext}\""))
                        print(f"{ext} CREATED successfully")
                    except Exception as e:
                        print(f"{ext} creation FAILED (likely permission issue): {e}")
                else:
                    print(f"{ext} is NOT AVAILABLE")
        except Exception as e:
            print(f"Error checking extensions: {e}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_db())
