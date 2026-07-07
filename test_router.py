import asyncio
from api.exercise_routes import get_exercises
from api.database import async_session

async def test():
    async with async_session() as db:
        try:
            res = await get_exercises(db=db)
            print("Response:", res)
        except Exception as e:
            import traceback
            traceback.print_exc()

asyncio.run(test())
