import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from api.database import Base
from api.models import User, PWDResetOTP, UserGoal, WorkoutLog, Exercise
from sqlalchemy import text

async def main():
    print("Tables in Base metadata:", Base.metadata.tables.keys())
    engine = create_async_engine("postgresql+asyncpg://postgres:password@localhost:5432/fitvision", echo=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))
        tables = result.fetchall()
        print("Tables in public schema:")
        for row in tables:
            print("-", row[0])

if __name__ == "__main__":
    asyncio.run(main())
