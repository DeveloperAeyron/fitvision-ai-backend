import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    engine = create_async_engine("postgresql+asyncpg://postgres:password@localhost:5432/fitvision", echo=True)
    async with engine.begin() as conn:
        print("Running ALTER TABLE queries...")
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(100)"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS allow_notifications BOOLEAN DEFAULT TRUE"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS app_blocker BOOLEAN DEFAULT FALSE"))
            print("Successfully added columns")
        except Exception as e:
            print("Error adding columns:", e)

if __name__ == "__main__":
    asyncio.run(main())
