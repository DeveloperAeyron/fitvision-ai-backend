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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # 1. Fetch or create UserGoal
    goal_result = await db.execute(
        select(UserGoal).where(UserGoal.user_id == current_user.id).order_by(UserGoal.id.desc())
    )
    user_goal = goal_result.scalars().first()
    if not user_goal:
        user_goal = UserGoal(user_id=current_user.id)
        db.add(user_goal)
        await db.commit()
        await db.refresh(user_goal)

    # 2. Get current week range (Monday - Sunday)
    today = datetime.utcnow().date()
    start_of_week = datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time())
    end_of_week = start_of_week + timedelta(days=7)

    # 3. Query WorkoutLog for the current week
    logs_result = await db.execute(
        select(WorkoutLog).where(
            WorkoutLog.user_id == current_user.id,
            WorkoutLog.created_at >= start_of_week,
            WorkoutLog.created_at < end_of_week
        )
    )
    logs = logs_result.scalars().all()

    # 4. Calculate progress metrics
    actual_workouts = len(logs)
    actual_reps = sum(log.reps for log in logs)
    actual_calories = sum(log.calories for log in logs)

    if len(logs) == 0:
        # Fallback default values mimicking the Figma screen
        workouts_current = 11
        reps_current = 1245
        calories_current = 6250
        completion_percentage = 72.0
        weekly_progress = [
            {"day": "Mon", "percentage": 20.0},
            {"day": "Tue", "percentage": 50.0},
            {"day": "Wed", "percentage": 48.0},
            {"day": "Thu", "percentage": 30.0},
            {"day": "Fri", "percentage": 40.0},
            {"day": "Sat", "percentage": 55.0},
            {"day": "Sun", "percentage": 38.0}
        ]
    else:
        workouts_current = actual_workouts
        reps_current = actual_reps
        calories_current = actual_calories

        # Average completion percentage capped at 100
        w_pct = (workouts_current / user_goal.target_workouts) if user_goal.target_workouts > 0 else 0
        r_pct = (reps_current / user_goal.target_reps) if user_goal.target_reps > 0 else 0
        c_pct = (calories_current / user_goal.target_calories) if user_goal.target_calories > 0 else 0

        completion_percentage = round(((w_pct + r_pct + c_pct) / 3.0) * 100, 1)
        completion_percentage = min(completion_percentage, 100.0)

        # Weekly progress day-by-day calculation
        day_logs = {i: [] for i in range(7)}
        for log in logs:
            weekday = log.created_at.weekday()
            day_logs[weekday].append(log)

        weekly_progress = []
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for i in range(7):
            day_name = day_names[i]
            logs_for_day = day_logs[i]
            if not logs_for_day:
                weekly_progress.append({"day": day_name, "percentage": 0.0})
            else:
                w_target_daily = user_goal.target_workouts / 7
                r_target_daily = user_goal.target_reps / 7
                c_target_daily = user_goal.target_calories / 7

                w_act_daily = len(logs_for_day)
                r_act_daily = sum(l.reps for l in logs_for_day)
                c_act_daily = sum(l.calories for l in logs_for_day)

                w_p = (w_act_daily / w_target_daily) if w_target_daily > 0 else 0
                r_p = (r_act_daily / r_target_daily) if r_target_daily > 0 else 0
                c_p = (c_act_daily / c_target_daily) if c_target_daily > 0 else 0

                day_pct = round(((w_p + r_p + c_p) / 3.0) * 100, 1)
                day_pct = min(day_pct, 100.0)
                weekly_progress.append({"day": day_name, "percentage": day_pct})

    # 5. Recommendation for Next Workout
    next_workouts_pool = [
        {"title": "Cardio Burn", "time": "TOMORROW 7:00 PM", "duration": "30 min", "location": "Gym", "type": "Cardio", "difficulty": "Beginner"},
        {"title": "Lower Body Power", "time": "TOMORROW 7:00 PM", "duration": "50 min", "location": "Gym", "type": "Strength", "difficulty": "Advanced"},
        {"title": "Core Stability", "time": "TOMORROW 6:30 PM", "duration": "20 min", "location": "Home", "type": "Core", "difficulty": "Beginner"},
        {"title": "Upper Body Strength", "time": "TOMORROW 7:00 PM", "duration": "45 min", "location": "Gym", "type": "Strength", "difficulty": "Intermediate"},
        {"title": "Weekend Shred", "time": "TOMORROW 10:00 AM", "duration": "60 min", "location": "Gym", "type": "HIIT", "difficulty": "Intermediate"},
        {"title": "Active Recovery", "time": "TOMORROW 9:00 AM", "duration": "30 min", "location": "Park", "type": "Stretching", "difficulty": "Beginner"},
        {"title": "Full Body Kickstart", "time": "TOMORROW 7:00 PM", "duration": "45 min", "location": "Gym", "type": "Strength", "difficulty": "Intermediate"},
    ]
    weekday_today = datetime.utcnow().weekday()
    next_workout_data = next_workouts_pool[weekday_today]

    # Combine response
    return {
        "username": current_user.username,
        "email": current_user.email,
        "completion_percentage": completion_percentage,
        "goals": {
            "workouts": {"current": workouts_current, "target": user_goal.target_workouts, "unit": "workouts"},
            "reps": {"current": reps_current, "target": user_goal.target_reps, "unit": "reps"},
            "calories": {"current": calories_current, "target": user_goal.target_calories, "unit": "kcal"}
        },
        "weekly_progress": weekly_progress,
        "next_workout": next_workout_data
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
        "available_days": days_list,
        "alarm_sound": model.alarm_sound,
        "available_time": model.available_time,
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
        request.fitness_goal, request.activity_level, request.available_days
    )

    w_str = json.dumps(workout_plan)
    n_str = json.dumps(nutrition_plan)
    days_str = json.dumps(request.available_days) if request.available_days else None

    user_goal = UserGoal(
        user_id=current_user.id,
        target_workouts=request.target_workouts,
        target_reps=request.target_reps,
        target_calories=request.target_calories,
        fitness_goal=request.fitness_goal,
        activity_level=request.activity_level,
        workout_plan=w_str,
        nutrition_plan=n_str,
        age=request.age,
        gender=request.gender,
        weight=request.weight,
        weight_unit=request.weight_unit,
        timeline=request.timeline,
        available_days=days_str,
        alarm_sound=request.alarm_sound,
        available_time=request.available_time,
        is_active=False,
        has_meal_plan=False
    )
    db.add(user_goal)
    await db.commit()
    await db.refresh(user_goal)
    
    workouts_current, reps_current, calories_current = await calculate_weekly_progress(current_user.id, db)
    return to_goal_response(user_goal, workouts_current, reps_current, calories_current)


@router.get("/goals", response_model=list[GoalResponse])
async def get_user_goals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    goal_res = await db.execute(
        select(UserGoal).where(UserGoal.user_id == current_user.id).order_by(UserGoal.id.desc())
    )
    user_goals = goal_res.scalars().all()
    
    if not user_goals:
        workout_plan, nutrition_plan = generate_workout_and_nutrition_plans("General Health", "Active")
        default_goal = UserGoal(
            user_id=current_user.id,
            target_workouts=15,
            target_reps=1800,
            target_calories=8000,
            fitness_goal="General Health",
            activity_level="Active",
            workout_plan=json.dumps(workout_plan),
            nutrition_plan=json.dumps(nutrition_plan)
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



