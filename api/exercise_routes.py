import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from api.database import get_db
from api.models import User, Exercise
from api.schemas import ExerciseCreate, ExerciseUpdate, ExerciseResponse
from api.auth import get_current_user

router = APIRouter(prefix="/exercises", tags=["exercises"])


def to_exercise_response(model: Exercise) -> ExerciseResponse:
    # Safely decode muscles_worked_pct JSON string
    muscles = {}
    if model.muscles_worked_pct:
        try:
            muscles = json.loads(model.muscles_worked_pct)
        except Exception:
            pass

    # Parse suggested_workouts from comma-separated string
    workouts = []
    if model.suggested_workouts:
        workouts = [w.strip() for w in model.suggested_workouts.split(",") if w.strip()]

    # Parse instructions from newline-separated string
    instructions_list = []
    if model.instructions:
        instructions_list = [i.strip() for i in model.instructions.split("\n") if i.strip()]

    # Parse safety_tips from newline-separated string
    tips_list = []
    if model.safety_tips:
        tips_list = [t.strip() for t in model.safety_tips.split("\n") if t.strip()]

    return ExerciseResponse(
        id=model.id,
        title=model.title,
        primary_muscle=model.primary_muscle,
        exercise_type=model.exercise_type,
        video_url=model.video_url,
        video_instruction=model.video_url or "https://example.com/default_video.mp4",
        image_url=model.image_url or "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?q=80&w=400&auto=format&fit=crop",
        muscles_worked_pct=muscles,
        suggested_workouts=workouts,
        instructions=instructions_list,
        safety_tips=tips_list,
        created_at=model.created_at
    )


@router.get("", response_model=list[ExerciseResponse])
async def get_exercises(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Exercise).order_by(Exercise.title))
        exercises = result.scalars().all()
        if exercises:
            return [to_exercise_response(e) for e in exercises]
        
        # Fallback to dummy data if DB is empty
        return [
            ExerciseResponse(
                id=1,
                title="Push-ups",
                primary_muscle="Chest",
                exercise_type="Home",
                video_url="https://example.com/pushups.mp4",
                muscles_worked_pct={"Chest": 70, "Triceps": 20, "Shoulders": 10},
                suggested_workouts=["Upper Body", "Full Body"],
                instructions=["Keep body straight", "Lower until chest touches floor"],
                safety_tips=["Don't flare elbows", "Keep core tight"],
                created_at=datetime.utcnow(),
                lastModifiedAt=datetime.utcnow()
            ),
            ExerciseResponse(
                id=2,
                title="Barbell Squats",
                primary_muscle="Legs",
                exercise_type="Gym",
                video_url="https://example.com/squats.mp4",
                muscles_worked_pct={"Quads": 60, "Glutes": 30, "Core": 10},
                suggested_workouts=["Leg Day", "Full Body"],
                instructions=["Keep chest up", "Push knees out", "Break parallel"],
                safety_tips=["Use a spotter", "Don't round lower back"],
                created_at=datetime.utcnow(),
                lastModifiedAt=datetime.utcnow()
            ),
            ExerciseResponse(
                id=3,
                title="Plank",
                primary_muscle="Core",
                exercise_type="Home",
                video_url="https://example.com/plank.mp4",
                video_instruction="https://example.com/plank.mp4",
                muscles_worked_pct={"Core": 80, "Shoulders": 20},
                suggested_workouts=["Core Crusher"],
                instructions=["Rest on forearms", "Keep body in straight line"],
                safety_tips=["Don't let hips sag"],
                created_at=datetime.utcnow(),
                lastModifiedAt=datetime.utcnow()
            ),
            ExerciseResponse(
                id=4,
                title="Cable Chest Fly",
                primary_muscle="Chest",
                exercise_type="Gym",
                video_url="https://example.com/cable_fly.mp4",
                video_instruction="https://example.com/cable_fly.mp4",
                muscles_worked_pct={"Chest": 100, "Shoulders": 60},
                suggested_workouts=["Upper Body"],
                instructions=["Squeeze chest", "Keep arms slightly bent"],
                safety_tips=["Don't use too much weight"],
                created_at=datetime.utcnow(),
                lastModifiedAt=datetime.utcnow()
            ),
            ExerciseResponse(
                id=5,
                title="High to low Cable Fly",
                primary_muscle="Chest",
                exercise_type="Gym",
                video_url="https://example.com/high_low_fly.mp4",
                video_instruction="https://example.com/high_low_fly.mp4",
                muscles_worked_pct={"Chest": 100, "Triceps": 20},
                suggested_workouts=["Upper Body"],
                instructions=["Pull cables downward and inward"],
                safety_tips=["Keep core tight"],
                created_at=datetime.utcnow(),
                lastModifiedAt=datetime.utcnow()
            ),
            ExerciseResponse(
                id=6,
                title="Dumbbell Bench Press",
                primary_muscle="Chest",
                exercise_type="Gym",
                video_url="https://example.com/db_bench.mp4",
                video_instruction="https://example.com/db_bench.mp4",
                muscles_worked_pct={"Chest": 100, "Triceps": 60, "Shoulders": 40},
                suggested_workouts=["Upper Body"],
                instructions=["Press dumbbells up", "Lower slowly"],
                safety_tips=["Don't flare elbows"],
                created_at=datetime.utcnow(),
                lastModifiedAt=datetime.utcnow()
            ),
            ExerciseResponse(
                id=7,
                title="Barbell Deadlift",
                primary_muscle="Back",
                exercise_type="Gym",
                video_url="https://example.com/deadlift.mp4",
                instructions=["Hinge at hips", "Keep bar close to body"],
                safety_tips=["Keep back straight", "Don't jerk the weight"],
                created_at=datetime.utcnow(),
                lastModifiedAt=datetime.utcnow()
            )
        ]
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise e


@router.get("/{exercise_id}", response_model=ExerciseResponse)
async def get_exercise(exercise_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Exercise).where(Exercise.id == exercise_id))
    exercise = result.scalars().first()
    if not exercise:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exercise not found"
        )
    return to_exercise_response(exercise)


@router.post("", response_model=ExerciseResponse, status_code=status.HTTP_201_CREATED)
async def create_exercise(
    request: ExerciseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Check if name/title already exists
    existing_result = await db.execute(select(Exercise).where(Exercise.title == request.title))
    if existing_result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An exercise with this title already exists."
        )

    # Serialize helpers
    muscles_str = json.dumps(request.muscles_worked_pct) if request.muscles_worked_pct else None
    workouts_str = ",".join(request.suggested_workouts) if request.suggested_workouts else None
    instructions_str = "\n".join(request.instructions) if request.instructions else None
    tips_str = "\n".join(request.safety_tips) if request.safety_tips else None

    new_exercise = Exercise(
        title=request.title,
        primary_muscle=request.primary_muscle,
        exercise_type=request.exercise_type,
        video_url=request.video_url,
        muscles_worked_pct=muscles_str,
        suggested_workouts=workouts_str,
        instructions=instructions_str,
        safety_tips=tips_str
    )
    db.add(new_exercise)
    await db.commit()
    await db.refresh(new_exercise)
    return to_exercise_response(new_exercise)


@router.put("/{exercise_id}", response_model=ExerciseResponse)
async def update_exercise(
    exercise_id: int,
    request: ExerciseUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Exercise).where(Exercise.id == exercise_id))
    exercise = result.scalars().first()
    if not exercise:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exercise not found"
        )

    # Check title uniqueness if title changed
    if exercise.title != request.title:
        title_check = await db.execute(select(Exercise).where(Exercise.title == request.title))
        if title_check.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Another exercise with this title already exists."
            )

    # Serialize update helpers
    exercise.title = request.title
    exercise.primary_muscle = request.primary_muscle
    exercise.exercise_type = request.exercise_type
    exercise.video_url = request.video_url
    exercise.muscles_worked_pct = json.dumps(request.muscles_worked_pct) if request.muscles_worked_pct else None
    exercise.suggested_workouts = ",".join(request.suggested_workouts) if request.suggested_workouts else None
    exercise.instructions = "\n".join(request.instructions) if request.instructions else None
    exercise.safety_tips = "\n".join(request.safety_tips) if request.safety_tips else None

    await db.commit()
    await db.refresh(exercise)
    return to_exercise_response(exercise)


@router.delete("/{exercise_id}", status_code=status.HTTP_200_OK)
async def delete_exercise(
    exercise_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Exercise).where(Exercise.id == exercise_id))
    exercise = result.scalars().first()
    if not exercise:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exercise not found"
        )

    await db.delete(exercise)
    await db.commit()
    return {"message": "Exercise deleted successfully"}
