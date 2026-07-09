import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from api.models import Exercise

async def seed_data():
    engine = create_async_engine("postgresql+asyncpg://postgres:password@localhost:5432/fitvision", echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # We will insert dummy exercises if they don't already exist by checking title
        result = await session.execute(select(Exercise.title))
        existing_titles = set(result.scalars().all())

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
            ),
            Exercise(
                title="Jumping Jacks",
                primary_muscle="Cardio",
                exercise_type="Cardio",
                location_type="both",
                video_url="https://example.com/jumpingjacks.mp4",
                muscles_worked_pct="Full Body: 100%",
                suggested_workouts="Warmup, Cardio Burn",
                instructions="1. Stand upright with legs together, arms at sides.\n2. Jump up and spread legs apart while swinging arms over your head.\n3. Jump back to starting position.",
                safety_tips="Land softly on the balls of your feet."
            ),
            Exercise(
                title="Glute Bridges",
                primary_muscle="Glutes",
                exercise_type="Bodyweight",
                location_type="both",
                video_url="https://example.com/glutebridges.mp4",
                muscles_worked_pct="Glutes: 70%, Hamstrings: 20%, Core: 10%",
                suggested_workouts="Lower Body Tone, Mobility",
                instructions="1. Lie on your back with knees bent and feet flat on the floor.\n2. Squeeze your glutes and lift your hips off the floor until your body forms a straight line.\n3. Lower back down slowly.",
                safety_tips="Do not overextend your lower back at the top of the movement."
            ),
            Exercise(
                title="Bird Dog",
                primary_muscle="Core",
                exercise_type="Mobility",
                location_type="both",
                video_url="https://example.com/birddog.mp4",
                muscles_worked_pct="Core: 60%, Lower Back: 20%, Glutes: 20%",
                suggested_workouts="Core Stability, Warmup",
                instructions="1. Start on all fours.\n2. Extend your right arm forward and left leg back simultaneously.\n3. Return to start and repeat on the other side.",
                safety_tips="Keep your back flat and minimize rocking of the hips."
            )
        ]
        
        new_exercises = [ex for ex in dummy_exercises if ex.title not in existing_titles]
        if new_exercises:
            session.add_all(new_exercises)
            await session.commit()
            print(f"Dummy exercises seeded successfully. Added {len(new_exercises)} new exercises.")
        else:
            print("All dummy exercises already exist in the database.")

if __name__ == "__main__":
    asyncio.run(seed_data())
