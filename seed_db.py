import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from api.models import Exercise

async def seed_data():
    engine = create_async_engine("postgresql+asyncpg://postgres:password@localhost:5432/fitvision", echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Check if exercises exist
        result = await session.execute(select(Exercise))
        if result.scalars().first():
            print("Exercises already seeded.")
            return

        dummy_exercises = [
            Exercise(
                title="Push-Ups",
                primary_muscle="Chest",
                exercise_type="Bodyweight",
                location_type="both",
                video_url="https://example.com/pushup.mp4",
                muscles_worked_pct="Chest: 60%, Triceps: 30%, Shoulders: 10%",
                suggested_workouts="Upper Body Strength, HIIT",
                instructions="1. Start in a plank position.\n2. Lower your body until your chest is near the floor.\n3. Push yourself back up.",
                safety_tips="Keep your core engaged. Do not let your lower back sag."
            ),
            Exercise(
                title="Squats",
                primary_muscle="Quadriceps",
                exercise_type="Bodyweight",
                location_type="home",
                video_url="https://example.com/squat.mp4",
                muscles_worked_pct="Quads: 50%, Glutes: 30%, Hamstrings: 20%",
                suggested_workouts="Lower Body Power, Cardio Burn",
                instructions="1. Stand with feet shoulder-width apart.\n2. Lower your hips as if sitting in a chair.\n3. Push through heels to return to start.",
                safety_tips="Keep your chest up. Don't let your knees go past your toes."
            ),
            Exercise(
                title="Plank",
                primary_muscle="Core",
                exercise_type="Bodyweight",
                location_type="both",
                video_url="https://example.com/plank.mp4",
                muscles_worked_pct="Abs: 70%, Shoulders: 20%, Lower Back: 10%",
                suggested_workouts="Core Stability",
                instructions="1. Rest on your forearms and toes.\n2. Keep your body in a straight line.\n3. Hold the position.",
                safety_tips="Breathe normally. Stop if you feel sharp lower back pain."
            ),
            Exercise(
                title="Barbell Bench Press",
                primary_muscle="Chest",
                exercise_type="Weights",
                location_type="gym",
                video_url="https://example.com/benchpress.mp4",
                muscles_worked_pct="Chest: 70%, Triceps: 20%, Shoulders: 10%",
                suggested_workouts="Chest Day, Upper Body Power",
                instructions="1. Lie flat on the bench.\n2. Grip the barbell slightly wider than shoulder-width.\n3. Lower the bar to your chest and press it back up.",
                safety_tips="Keep your feet flat on the floor. Have a spotter if lifting heavy."
            )
        ]
        
        session.add_all(dummy_exercises)
        await session.commit()
        print("Dummy exercises seeded successfully.")

if __name__ == "__main__":
    asyncio.run(seed_data())
