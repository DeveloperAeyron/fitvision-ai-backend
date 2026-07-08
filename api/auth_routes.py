from datetime import datetime, timedelta
import logging
import os
import random
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import httpx
import secrets

from api.database import get_db
from api.models import User, PWDResetOTP, UserGoal, WorkoutLog
from api.schemas import (
    UserCreate,
    UserResponse,
    Token,
    ForgotPasswordRequest,
    VerifyOTPRequest,
    ResetPasswordRequest,
    GoogleLoginRequest,
    DashboardResponse,
    WorkoutLogCreate,
    GoalCreateRequest,
    GoalResponse,
    MealCreateRequest,
    MealPlanResponse,
)
from api.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_reset_token,
    get_reset_password_email,
    get_current_user,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


def sync_send_otp_email(email: str, otp: str):
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_sender = os.getenv("SMTP_SENDER", smtp_username)

    if not smtp_host or not smtp_username:
        logger.warning(
            "\n"
            "========================================================\n"
            "SMTP NOT CONFIGURED. PRINTING PASSWORD RESET OTP:\n"
            f"Email: {email}\n"
            f"OTP Code: {otp}\n"
            "========================================================\n"
        )
        return

    msg = MIMEMultipart()
    msg["From"] = smtp_sender
    msg["To"] = email
    msg["Subject"] = "FitVision - Password Reset OTP"

    body = f"""
    <h2>FitVision Password Reset</h2>
    <p>We received a request to reset your password. Use the following 6-digit OTP code to verify your identity:</p>
    <h1 style="color: #E2A000; font-size: 32px; letter-spacing: 2px;">{otp}</h1>
    <p>This code will expire in 5 minutes.</p>
    <p>If you did not request this, please ignore this email.</p>
    """
    msg.attach(MIMEText(body, "html"))

    try:
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail(smtp_sender, email, msg.as_string())
        server.quit()
        logger.info(f"Successfully sent password reset OTP to {email}")
    except Exception as e:
        logger.error(f"Failed to send email to {email}: {e}")
        logger.warning(f"FALLBACK OTP PRINT FOR {email}: {otp}")


async def send_otp_email(email: str, otp: str):
    await run_in_threadpool(sync_send_otp_email, email, otp)


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    # Check if email exists
    email_result = await db.execute(select(User).where(User.email == user_data.email))
    if email_result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    new_user = User(
        username=user_data.email,
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        gender=user_data.gender,
        date_of_birth=user_data.date_of_birth
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


class OAuth2PasswordRequestFormEmail:
    def __init__(
        self,
        grant_type: str | None = Form(default=None, pattern="password"),
        email: str = Form(..., description="Email address used for login"),
        password: str = Form(...),
        scope: str = Form(default=""),
        client_id: str | None = Form(default=None),
        client_secret: str | None = Form(default=None),
    ):
        self.grant_type = grant_type
        self.username = email
        self.password = password
        self.scopes = [s.strip() for s in scope.split()]
        self.client_id = client_id
        self.client_secret = client_secret


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestFormEmail = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(
            (User.username == form_data.username) | (User.email == form_data.username)
        )
    )
    user = result.scalars().first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalars().first()
    if not user:
        # Prevent user enumeration but log for developer convenience
        logger.info(f"Forgot password requested for non-existent email: {request.email}")
        return {"message": "If the email is registered, a password reset OTP has been sent."}

    # Generate 6-digit OTP
    otp_code = f"{random.randint(100000, 999999)}"
    expires_at = datetime.utcnow() + timedelta(minutes=5)

    # Delete any existing OTP for this email
    await db.execute(delete(PWDResetOTP).where(PWDResetOTP.email == request.email))

    new_otp = PWDResetOTP(
        email=request.email,
        otp_code=otp_code,
        expires_at=expires_at
    )
    db.add(new_otp)
    await db.commit()

    # Send email asynchronously using threadpool
    await send_otp_email(request.email, otp_code)

    return {"message": "If the email is registered, a password reset OTP has been sent."}


@router.post("/verify-otp")
async def verify_otp(
    request: VerifyOTPRequest,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(PWDResetOTP).where(PWDResetOTP.email == request.email))
    otp_record = result.scalars().first()

    if not otp_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No OTP requested for this email."
        )

    if otp_record.expires_at < datetime.utcnow():
        await db.delete(otp_record)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired."
        )

    if otp_record.otp_code != request.otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect OTP code."
        )

    # Valid OTP - clean it up immediately
    await db.delete(otp_record)
    await db.commit()

    # Return a temporary token for resetting password
    reset_token = create_reset_token(request.email)
    return {
        "reset_token": reset_token,
        "token_type": "bearer",
        "message": "OTP verified successfully. You can now reset your password."
    }


@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    if request.password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match."
        )

    # Validate complexity matching Figma:
    # - At least 8 characters
    # - Contains an upper case letter
    # - Contains a symbol or a number
    if len(request.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long."
        )
    if not any(c.isupper() for c in request.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one uppercase letter."
        )
    if not any(c.isdigit() or not c.isalnum() for c in request.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one number or special symbol."
        )

    # Decode reset token to get email
    email = get_reset_password_email(request.token)

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    user.hashed_password = hash_password(request.password)
    await db.commit()

    return {"message": "Password has been reset successfully."}


@router.post("/google", response_model=Token)
async def google_login(request: GoogleLoginRequest, db: AsyncSession = Depends(get_db)):
    # 1. Validate ID token via Google Tokeninfo endpoint
    token_info_url = f"https://oauth2.googleapis.com/tokeninfo?id_token={request.id_token}"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(token_info_url)
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid Google ID token"
                )
            payload = response.json()
        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Google token verification failed: {str(e)}"
            )

    # 2. Verify audience matches configured Google Client ID
    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "272845957801-lel0bj139oa9tic61f419du4fgpspc7c.apps.googleusercontent.com")
    aud = payload.get("aud")
    if google_client_id and aud != google_client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google ID token audience mismatch"
        )

    # 3. Extract email from Google payload
    email = payload.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google ID token does not contain email"
        )

    # 3. Check if user already exists
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()

    if not user:
        # User does not exist, automatically register them
        # Generate a random password for Google-authenticated user
        random_password = secrets.token_urlsafe(16)

        user = User(
            username=email,
            email=email,
            hashed_password=hash_password(random_password),
            gender=None,
            date_of_birth=None
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    # 4. Generate FitVision access token
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    current_user: User = Depends(get_current_user)
):
    # Returning hardcoded dummy response as requested
    return {
        "username": current_user.full_name or current_user.username,
        "email": current_user.email,
        "completion_percentage": 72.0,
        "goals": {
            "workouts": {"current": 11, "target": 15, "unit": "workouts"},
            "reps": {"current": 1245, "target": 1800, "unit": "reps"},
            "calories": {"current": 6250, "target": 8000, "unit": "kcal"}
        },
        "weekly_progress": [
            {"day": "Mon", "percentage": 20.0},
            {"day": "Tue", "percentage": 50.0},
            {"day": "Wed", "percentage": 48.0},
            {"day": "Thu", "percentage": 30.0},
            {"day": "Fri", "percentage": 40.0},
            {"day": "Sat", "percentage": 55.0},
            {"day": "Sun", "percentage": 38.0}
        ],
        "next_workout": {
            "title": "Full Body Kickstart",
            "time": "TOMORROW 7:00 PM",
            "duration": "45 min",
            "location": "Gym",
            "type": "Strength",
            "difficulty": "Intermediate"
        },
        "lastModifiedAt": datetime.utcnow()
    }


@router.post("/workouts/log", status_code=status.HTTP_201_CREATED)
async def log_workout(
    request: WorkoutLogCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    log_time = request.created_at if request.created_at else datetime.utcnow()
    new_log = WorkoutLog(
        user_id=current_user.id,
        exercise_name=request.exercise_name,
        reps=request.reps,
        calories=request.calories,
        duration_minutes=request.duration_minutes,
        created_at=log_time
    )
    db.add(new_log)
    await db.commit()
    await db.refresh(new_log)
    return {"message": "Workout logged successfully", "id": new_log.id}


import json

def generate_workout_and_nutrition_plans(fitness_goal: str, activity_level: str, available_days: list[str] = None):
    goal = fitness_goal.lower().strip()
    level = activity_level.lower().strip()
    
    day_map = {
        "Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday",
        "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday",
        "Monday": "Monday", "Tuesday": "Tuesday", "Wednesday": "Wednesday",
        "Thursday": "Thursday", "Friday": "Friday", "Saturday": "Saturday", "Sunday": "Sunday"
    }
    
    days = []
    if available_days:
        for d in available_days:
            if d in day_map:
                days.append(day_map[d])
    
    if not days:
        if "loss" in goal or "weight" in goal:
            days = ["Monday", "Wednesday", "Friday"]
        elif "gain" in goal or "muscle" in goal:
            days = ["Monday", "Wednesday", "Friday"]
        else:
            days = ["Tuesday", "Thursday", "Saturday"]
            
    workout_plan = []
    for day in days:
        if "loss" in goal or "weight" in goal:
            exercises = [
                {"name": "Push-Ups", "sets": 4, "reps_or_duration": "20 reps", "type": "Bodyweight"},
                {"name": "Bodyweight Squats", "sets": 4, "reps_or_duration": "15 reps", "type": "Bodyweight"},
                {"name": "Plank Hold", "sets": 3, "reps_or_duration": "45 sec", "type": "Bodyweight"}
            ]
            workout_name = "HIIT Fat Burner"
            duration = 30
        elif "gain" in goal or "muscle" in goal or "hypertrophy" in goal:
            exercises = [
                {"name": "Push-Ups", "sets": 4, "reps_or_duration": "20 reps", "type": "Bodyweight"},
                {"name": "Bodyweight Squats", "sets": 4, "reps_or_duration": "15 reps", "type": "Bodyweight"},
                {"name": "Plank Hold", "sets": 3, "reps_or_duration": "45 sec", "type": "Bodyweight"}
            ]
            workout_name = "Hypertrophy Power"
            duration = 50
        else:
            exercises = [
                {"name": "Jumping Jacks", "sets": 3, "reps_or_duration": "30 sec", "type": "Cardio"},
                {"name": "Glute Bridges", "sets": 3, "reps_or_duration": "15 reps", "type": "Bodyweight"},
                {"name": "Bird Dog", "sets": 3, "reps_or_duration": "12 reps", "type": "Mobility"}
            ]
            workout_name = "General Health & Tone"
            duration = 40

        workout_plan.append({
            "day": day,
            "workout_name": workout_name,
            "duration_minutes": duration,
            "exercises": exercises
        })

    # Nutrition Plan
    if "loss" in goal or "weight" in goal:
        cal = 1600 if "sedentary" in level else (1800 if "light" in level else 2000)
        nutrition_plan = {
            "daily_calories": cal,
            "macronutrients": {"protein_g": 135, "carbs_g": 165, "fats_g": 55},
            "meal_suggestions": {
                "breakfast": "Egg white omelet with spinach and 1 slice whole wheat toast",
                "lunch": "Mixed greens salad with 150g grilled chicken breast and light dressing",
                "dinner": "150g baked white fish with steamed broccoli and half a cup of quinoa"
            }
        }
    elif "gain" in goal or "muscle" in goal or "hypertrophy" in goal:
        cal = 2400 if "sedentary" in level else (2700 if "light" in level else 3000)
        nutrition_plan = {
            "daily_calories": cal,
            "macronutrients": {"protein_g": 160, "carbs_g": 350, "fats_g": 80},
            "meal_suggestions": {
                "breakfast": "Oatmeal (1 cup) with 2 scoops protein powder, peanut butter, and banana",
                "lunch": "200g lean beef mince with 1.5 cups white jasmine rice and green beans",
                "dinner": "200g grilled salmon filet with large sweet potato and roasted asparagus"
            }
        }
    else:
        cal = 1800 if "sedentary" in level else (2100 if "light" in level else 2400)
        nutrition_plan = {
            "daily_calories": cal,
            "macronutrients": {"protein_g": 120, "carbs_g": 260, "fats_g": 60},
            "meal_suggestions": {
                "breakfast": "Greek yogurt bowl with honey, chia seeds, and mixed berries",
                "lunch": "Turkey breast wrap with whole wheat tortilla, avocado, lettuce, and tomatoes",
                "dinner": "Grilled chicken breast with large portion of roasted Mediterranean vegetables"
            }
        }
        
    return workout_plan, nutrition_plan


async def calculate_weekly_progress(user_id: int, db: AsyncSession) -> tuple[int, int, int]:
    today = datetime.utcnow().date()
    start_of_week = datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time())
    end_of_week = start_of_week + timedelta(days=7)

    logs_result = await db.execute(
        select(WorkoutLog).where(
            WorkoutLog.user_id == user_id,
            WorkoutLog.created_at >= start_of_week,
            WorkoutLog.created_at < end_of_week
        )
    )
    logs = logs_result.scalars().all()

    actual_workouts = len(logs)
    actual_reps = sum(log.reps for log in logs)
    actual_calories = sum(log.calories for log in logs)
    return actual_workouts, actual_reps, actual_calories


def to_goal_response(model: UserGoal, workouts_current: int, reps_current: int, calories_current: int) -> dict:
    w_plan = []
    n_plan = {}
    if model.workout_plan:
        try:
            w_plan = json.loads(model.workout_plan)
        except Exception:
            pass
    if model.nutrition_plan:
        try:
            n_plan = json.loads(model.nutrition_plan)
        except Exception:
            pass
    
    if not w_plan:
        w_plan, n_plan = generate_workout_and_nutrition_plans(
            model.fitness_goal or "General Health",
            model.activity_level or "Active"
        )

    w_pct = (workouts_current / model.target_workouts) if model.target_workouts > 0 else 0
    r_pct = (reps_current / model.target_reps) if model.target_reps > 0 else 0
    c_pct = (calories_current / model.target_calories) if model.target_calories > 0 else 0
    
    w_pct = min(w_pct, 1.0)
    r_pct = min(r_pct, 1.0)
    c_pct = min(c_pct, 1.0)
    
    completion_percentage = round(((w_pct + r_pct + c_pct) / 3.0) * 100.0, 1)

    progress = {
        "workouts": {"current": workouts_current, "target": model.target_workouts, "unit": "workouts"},
        "reps": {"current": reps_current, "target": model.target_reps, "unit": "reps"},
        "calories": {"current": calories_current, "target": model.target_calories, "unit": "kcal"},
        "completion_percentage": completion_percentage
    }

    days_list = []
    if model.available_days:
        try:
            days_list = json.loads(model.available_days)
        except Exception:
            days_list = [d.strip() for d in model.available_days.split(",") if d.strip()]

    return {
        "id": model.id,
        "target_workouts": model.target_workouts,
        "target_reps": model.target_reps,
        "target_calories": model.target_calories,
        "fitness_goal": model.fitness_goal or "General Health",
        "activity_level": model.activity_level or "Active",
        "workout_plan": w_plan,
        "nutrition_plan": n_plan,
        "progress": progress,
        "age": model.age,
        "gender": model.gender,
        "weight": model.weight,
        "weight_unit": model.weight_unit,
        "timeline": model.timeline,
        "days": days_list,
        "alarm_sound": model.alarm_sound,
        "time_of_day": model.available_time,
        "is_active": model.is_active,
        "has_meal_plan": model.has_meal_plan,
        "created_at": model.created_at
    }


@router.post("/goals", response_model=GoalResponse)
async def create_user_goal(
    request: GoalCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    workout_plan, nutrition_plan = generate_workout_and_nutrition_plans(
        request.fitness_goal, request.activity_level, request.days
    )

    w_str = json.dumps(workout_plan)
    days_str = json.dumps(request.days) if request.days else None

    user_goal = UserGoal(
        user_id=current_user.id,
        target_workouts=15,
        target_reps=1800,
        target_calories=8000,
        fitness_goal=request.fitness_goal,
        activity_level=request.activity_level,
        workout_plan=w_str,
        nutrition_plan=None,
        age=request.age,
        gender=request.gender,
        weight=request.weight,
        weight_unit=request.weight_unit,
        timeline=request.timeline,
        available_days=days_str,
        alarm_sound=request.alarm_sound,
        available_time=request.time_of_day,
        is_active=False,
        has_meal_plan=False
    )
    db.add(user_goal)
    await db.commit()
    await db.refresh(user_goal)
    
    workouts_current, reps_current, calories_current = await calculate_weekly_progress(current_user.id, db)
    return to_goal_response(user_goal, workouts_current, reps_current, calories_current)


@router.post("/meals", response_model=MealPlanResponse)
async def create_user_meal(
    request: MealCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    _, nutrition_plan = generate_workout_and_nutrition_plans(
        request.fitness_goal, request.activity_level
    )

    n_str = json.dumps(nutrition_plan)

    user_goal = UserGoal(
        user_id=current_user.id,
        target_workouts=15,
        target_reps=1800,
        target_calories=8000,
        fitness_goal=request.fitness_goal,
        activity_level=request.activity_level,
        workout_plan=None,
        nutrition_plan=n_str,
        age=request.age,
        gender=request.gender,
        weight=request.weight,
        weight_unit=request.weight_unit,
        food_allergies=request.food_allergies,
        health_conditions=request.health_conditions,
        notes=request.notes,
        timeline=None,
        available_days=None,
        alarm_sound=None,
        available_time=None,
        is_active=False,
        has_meal_plan=True
    )
    db.add(user_goal)
    await db.commit()
    await db.refresh(user_goal)
    
    return MealPlanResponse(
        goal_id=user_goal.id,
        fitness_goal=user_goal.fitness_goal,
        nutrition_plan=nutrition_plan,
        created_at=user_goal.created_at
    )



@router.get("/goals/options")
async def get_goals_options(
    current_user: User = Depends(get_current_user)
):
    return {
        "fitness_goals": ["Weight Loss", "Muscle Gain", "Endurance", "General Health"],
        "activity_levels": [
            {"value": "Sedentary", "label": "Sedentary (desk job, little exercise)"},
            {"value": "Lightly Active", "label": "Lightly Active (light exercise 1-3 days/week)"},
            {"value": "Active", "label": "Active (moderate exercise 3-5 days/week)"},
            {"value": "Very Active", "label": "Very Active (hard exercise 6-7 days/week)"}
        ],
        "timelines": ["8 Weeks", "12 Weeks", "16 Weeks"],
        "alarm_sounds": ["Mission Alarm", "Energetic Wake", "Gentle Bells"]
    }


@router.get("/goals/activity-levels")
async def get_activity_levels(
    current_user: User = Depends(get_current_user)
):
    return {
        "values": [
            {"id": 1, "name": "Sedentary (desk job, little exercise)"},
            {"id": 2, "name": "Lightly Active (light exercise 1-3 days/week)"},
            {"id": 3, "name": "Active (moderate exercise 3-5 days/week)"},
            {"id": 4, "name": "Very Active (hard exercise 6-7 days/week)"}
        ]
    }


@router.get("/goals/fitness-goals")
async def get_fitness_goals(
    current_user: User = Depends(get_current_user)
):
    return {
        "values": [
            {"id": 1, "name": "Weight Loss"},
            {"id": 2, "name": "Muscle Gain"},
            {"id": 3, "name": "Endurance & Stamina"},
            {"id": 4, "name": "General Health"}
        ]
    }


@router.get("/goals/timelines")
async def get_timelines(
    current_user: User = Depends(get_current_user)
):
    return {
        "values": [
            {"id": 1, "name": "8 Weeks"},
            {"id": 2, "name": "12 Weeks"},
            {"id": 3, "name": "16 Weeks"}
        ]
    }


@router.get("/goals", response_model=list[GoalResponse])
async def get_user_goals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    goal_res = await db.execute(
        select(UserGoal)
        .where(UserGoal.user_id == current_user.id)
        .where(UserGoal.is_active == True)
        .where(UserGoal.workout_plan.is_not(None))
        .order_by(UserGoal.id.desc())
    )
    user_goals = goal_res.scalars().all()
    
    if not user_goals:
        workout_plan, _ = generate_workout_and_nutrition_plans("General Health", "Active")
        default_goal = UserGoal(
            user_id=current_user.id,
            target_workouts=15,
            target_reps=1800,
            target_calories=8000,
            fitness_goal="General Health",
            activity_level="Active",
            workout_plan=json.dumps(workout_plan),
            nutrition_plan=None,
            is_active=True
        )
        db.add(default_goal)
        await db.commit()
        await db.refresh(default_goal)
        user_goals = [default_goal]

    workouts_current, reps_current, calories_current = await calculate_weekly_progress(current_user.id, db)
    return [to_goal_response(g, workouts_current, reps_current, calories_current) for g in user_goals]


@router.post("/goals/{goal_id}/activate", response_model=GoalResponse)
async def activate_user_goal(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(UserGoal).where(UserGoal.id == goal_id, UserGoal.user_id == current_user.id))
    user_goal = result.scalars().first()
    if not user_goal:
        raise HTTPException(status_code=404, detail="Goal not found")
        
    user_goal.is_active = True
    await db.commit()
    await db.refresh(user_goal)
    
    workouts_current, reps_current, calories_current = await calculate_weekly_progress(current_user.id, db)
    return to_goal_response(user_goal, workouts_current, reps_current, calories_current)


@router.post("/goals/{goal_id}/meal-plan", response_model=GoalResponse)
async def generate_meal_plan_for_goal(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(UserGoal).where(UserGoal.id == goal_id, UserGoal.user_id == current_user.id))
    user_goal = result.scalars().first()
    if not user_goal:
        raise HTTPException(status_code=404, detail="Goal not found")
        
    user_goal.has_meal_plan = True
    await db.commit()
    await db.refresh(user_goal)
    
    workouts_current, reps_current, calories_current = await calculate_weekly_progress(current_user.id, db)
    return to_goal_response(user_goal, workouts_current, reps_current, calories_current)





@router.delete("/goals/{goal_id}")
async def delete_user_goal(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(UserGoal).where(UserGoal.id == goal_id, UserGoal.user_id == current_user.id))
    user_goal = result.scalars().first()
    if not user_goal:
        raise HTTPException(status_code=404, detail="Goal not found")
        
    await db.delete(user_goal)
    await db.commit()
    return {"message": "Goal deleted successfully"}


@router.delete("/meal-plans/{goal_id}")
async def delete_user_meal_plan(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(UserGoal).where(UserGoal.id == goal_id, UserGoal.user_id == current_user.id))
    user_goal = result.scalars().first()
    if not user_goal:
        raise HTTPException(status_code=404, detail="Meal plan not found")
        
    if not user_goal.workout_plan:
        await db.delete(user_goal)
    else:
        user_goal.has_meal_plan = False
        user_goal.nutrition_plan = None
    
    await db.commit()
    return {"message": "Meal plan deleted successfully"}


@router.get("/meal-plans", response_model=list[dict])
async def get_user_meal_plans(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from api.schemas import MealPlanResponse
    result = await db.execute(
        select(UserGoal)
        .where(UserGoal.user_id == current_user.id, UserGoal.has_meal_plan == True)
        .order_by(UserGoal.id.desc())
    )
    user_goals = result.scalars().all()
    
    meal_plans = []
    for g in user_goals:
        nut_plan = {}
        if g.nutrition_plan:
            try:
                nut_plan = json.loads(g.nutrition_plan)
            except Exception:
                pass
        meal_plans.append(
            MealPlanResponse(
                goal_id=g.id,
                fitness_goal=g.fitness_goal,
                nutrition_plan=nut_plan,
                created_at=g.created_at
            ).model_dump()
        )
    return meal_plans


@router.get("/profile", response_model=UserResponse)
async def get_user_profile(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)

@router.get("/me", response_model=UserResponse)
async def get_user_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@router.put("/profile")
async def update_user_profile(
    profile_data: dict, # using dict here because I will import UserProfileUpdate later, or I can just use dict for now
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from api.schemas import UserProfileUpdate, UserResponse
    # Validate profile_data via UserProfileUpdate
    update_schema = UserProfileUpdate(**profile_data)
    update_data = update_schema.model_dump(exclude_unset=True)
    
    if "email" in update_data and update_data["email"] != current_user.email:
        # Check if new email is already taken
        email_result = await db.execute(select(User).where(User.email == update_data["email"]))
        if email_result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
            
    for key, value in update_data.items():
        setattr(current_user, key, value)
        
    await db.commit()
    await db.refresh(current_user)
    return UserResponse.model_validate(current_user)


from sqlalchemy import func
from api.models import Exercise

@router.get("/sync/last-modified")
async def get_last_modified(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    goal_res = await db.execute(
        select(func.max(UserGoal.updated_at)).where(UserGoal.user_id == current_user.id)
    )
    max_goal_ts = goal_res.scalar()

    log_res = await db.execute(
        select(func.max(WorkoutLog.updated_at)).where(WorkoutLog.user_id == current_user.id)
    )
    max_log_ts = log_res.scalar()

    ex_res = await db.execute(
        select(func.max(Exercise.updated_at))
    )
    max_ex_ts = ex_res.scalar()

    timestamps = [ts for ts in [current_user.created_at, max_goal_ts, max_log_ts, max_ex_ts] if ts is not None]
    latest = max(timestamps) if timestamps else None
    
    return {"last_modified": latest.isoformat() if latest else None}


from pydantic import BaseModel
class ContactUsRequest(BaseModel):
    email: str
    description: str
    file_url: str | None = None

@router.post("/contact")
async def contact_us(
    request: ContactUsRequest,
    current_user: User = Depends(get_current_user)
):
    # Dummy implementation for Contact Us
    logger.info(f"Contact Us message from {request.email}: {request.description}")
    return {"message": "Thank you for contacting us. Your request has been received."}
