from datetime import datetime, timedelta
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc

from api.database import get_db
from api.models import User, UserGoal, WorkoutLog
from api.auth import get_current_user
from api.schemas import (
    DashboardResponse,
    DashboardGoals,
    GoalMetric,
    WeeklyProgressDay,
    NextWorkoutInfo
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("", response_model=DashboardResponse)
async def get_dashboard_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # 1. Fetch active goal
    goal_result = await db.execute(
        select(UserGoal)
        .where(UserGoal.user_id == current_user.id, UserGoal.is_active == True)
        .order_by(desc(UserGoal.created_at))
    )
    active_goal = goal_result.scalars().first()
    
    target_workouts = active_goal.target_workouts if active_goal else 15
    target_reps = active_goal.target_reps if active_goal else 1800
    target_calories = active_goal.target_calories if active_goal else 8000

    # 2. Fetch workout logs for the last 7 days
    seven_days_ago = datetime.utcnow().date() - timedelta(days=7)
    logs_result = await db.execute(
        select(WorkoutLog)
        .where(
            WorkoutLog.user_id == current_user.id,
            WorkoutLog.workout_date >= seven_days_ago
        )
    )
    recent_logs = logs_result.scalars().all()

    # 3. Calculate current progress
    current_workouts = sum(1 for log in recent_logs if log.is_completed)
    current_reps = sum(log.reps for log in recent_logs)
    current_calories = sum(log.calories for log in recent_logs)
    
    # Base completion percentage off workouts primarily, but can be an average
    perc_workouts = min((current_workouts / target_workouts) * 100, 100.0) if target_workouts > 0 else 0.0
    perc_reps = min((current_reps / target_reps) * 100, 100.0) if target_reps > 0 else 0.0
    perc_calories = min((current_calories / target_calories) * 100, 100.0) if target_calories > 0 else 0.0
    
    completion_percentage = round((perc_workouts + perc_reps + perc_calories) / 3.0, 1)

    # 4. Format Weekly Progress (Group by day)
    # We'll create a dictionary for the last 7 days, defaulting to 0 percentage.
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    # Initialize last 7 days based on current day
    today = datetime.utcnow().date()
    weekly_progress_dict = {}
    for i in range(6, -1, -1):
        day_date = today - timedelta(days=i)
        day_name = days[day_date.weekday()]
        weekly_progress_dict[day_date] = {"day": day_name, "percentage": 0.0, "calories": 0}

    # Sum calories per day
    for log in recent_logs:
        log_date = log.workout_date
        if log_date in weekly_progress_dict:
            weekly_progress_dict[log_date]["calories"] += log.calories

    # Calculate percentage per day based on a daily calorie goal (target / 7)
    daily_cal_target = target_calories / 7.0 if target_calories > 0 else 1000
    weekly_progress = []
    for d, data in weekly_progress_dict.items():
        pct = min((data["calories"] / daily_cal_target) * 100, 100.0) if daily_cal_target > 0 else 0.0
        weekly_progress.append(WeeklyProgressDay(day=data["day"], percentage=round(pct, 1)))

    # 5. Mock Next Workout Info
    # Ideally, parse `active_goal.workout_plan`, but here we provide a sensible fallback
    next_workout = NextWorkoutInfo(
        title="Full Body Circuit",
        time="Today, 5:00 PM",
        duration="45 min",
        location="Home",
        type="Strength",
        difficulty="Intermediate"
    )

    goals = DashboardGoals(
        workouts=GoalMetric(current=current_workouts, target=target_workouts, unit="sessions"),
        reps=GoalMetric(current=current_reps, target=target_reps, unit="reps"),
        calories=GoalMetric(current=current_calories, target=target_calories, unit="kcal")
    )

    return DashboardResponse(
        username=current_user.full_name or current_user.username,
        email=current_user.email,
        completion_percentage=completion_percentage,
        goals=goals,
        weekly_progress=weekly_progress,
        next_workout=next_workout,
        lastModifiedAt=datetime.utcnow()
    )
