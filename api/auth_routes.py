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
        goal_id=request.goal_id,
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
                {"name": "Squats", "sets": 4, "reps_or_duration": "15 reps", "type": "Bodyweight"},
                {"name": "Plank", "sets": 3, "reps_or_duration": "45 sec", "type": "Bodyweight"}
            ]
            workout_name = "HIIT Fat Burner"
            duration = 30
        elif "gain" in goal or "muscle" in goal or "hypertrophy" in goal:
            exercises = [
                {"name": "Push-Ups", "sets": 4, "reps_or_duration": "20 reps", "type": "Bodyweight"},
                {"name": "Squats", "sets": 4, "reps_or_duration": "15 reps", "type": "Bodyweight"},
                {"name": "Plank", "sets": 3, "reps_or_duration": "45 sec", "type": "Bodyweight"}
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
    meal_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    if "loss" in goal or "weight" in goal:
        cal = 1600 if "sedentary" in level else (1800 if "light" in level else 2000)
        daily_totals = {"calories": cal, "protein_g": 135, "carbs_g": 165, "fats_g": 55, "fiber_g": 30}
        meals = [
            {
                "type": "Breakfast",
                "name": "Egg White Omelet with Spinach",
                "image_url": "https://images.unsplash.com/photo-1525351484163-7529414344d8?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["3 egg whites", "1 cup spinach", "1 slice whole wheat toast", "Olive oil spray"],
                "steps": ["Spray pan with olive oil.", "Sauté spinach until wilted.", "Pour in egg whites and cook until set.", "Serve with toast."],
                "health_notes": "High protein, low calorie. Spinach provides excellent iron.",
                "calories": 350,
                "protein_g": 30,
                "carbs_g": 25,
                "fats_g": 10,
                "fiber_g": 5
            },
            {
                "type": "Lunch",
                "name": "Grilled Chicken Salad",
                "image_url": "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["150g chicken breast", "Mixed greens", "Cherry tomatoes", "Light vinaigrette"],
                "steps": ["Grill chicken breast until cooked through.", "Chop greens and tomatoes.", "Toss together with vinaigrette."],
                "health_notes": "Lean protein and high volume veggies keep you full.",
                "calories": 550,
                "protein_g": 45,
                "carbs_g": 30,
                "fats_g": 15,
                "fiber_g": 8
            },
            {
                "type": "Dinner",
                "name": "Baked White Fish & Quinoa",
                "image_url": "https://images.unsplash.com/photo-1519708227418-c8fd9a32b7a2?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["150g white fish", "1/2 cup cooked quinoa", "Steamed broccoli"],
                "steps": ["Bake fish at 400F for 15 mins.", "Steam broccoli.", "Serve over warm quinoa."],
                "health_notes": "Light easily digestible protein for the evening.",
                "calories": 700,
                "protein_g": 60,
                "carbs_g": 110,
                "fats_g": 30,
                "fiber_g": 17
            }
        ]
    elif "gain" in goal or "muscle" in goal or "hypertrophy" in goal:
        cal = 2400 if "sedentary" in level else (2700 if "light" in level else 3000)
        daily_totals = {"calories": cal, "protein_g": 160, "carbs_g": 350, "fats_g": 80, "fiber_g": 35}
        meals = [
            {
                "type": "Breakfast",
                "name": "Protein Oatmeal",
                "image_url": "https://images.unsplash.com/photo-1517673132405-a56a62b18caf?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["1 cup oats", "2 scoops whey protein", "1 tbsp peanut butter", "1 banana"],
                "steps": ["Cook oats with water or milk.", "Stir in protein powder while warm.", "Top with sliced banana and peanut butter."],
                "health_notes": "Dense calories for muscle building and energy.",
                "calories": 700,
                "protein_g": 45,
                "carbs_g": 80,
                "fats_g": 20,
                "fiber_g": 10
            },
            {
                "type": "Lunch",
                "name": "Beef & Rice Bowl",
                "image_url": "https://images.unsplash.com/photo-1543339308-43e59d6b73a6?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["200g lean beef mince", "1.5 cups jasmine rice", "Green beans", "Soy sauce"],
                "steps": ["Brown beef in a skillet.", "Steam rice and beans.", "Combine and drizzle with soy sauce."],
                "health_notes": "High carbs to replenish glycogen post-workout.",
                "calories": 900,
                "protein_g": 55,
                "carbs_g": 130,
                "fats_g": 25,
                "fiber_g": 10
            },
            {
                "type": "Dinner",
                "name": "Grilled Salmon & Sweet Potato",
                "image_url": "https://images.unsplash.com/photo-1467003909585-2f8a72700288?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["200g salmon filet", "1 large sweet potato", "Roasted asparagus"],
                "steps": ["Grill salmon for 10 mins.", "Bake sweet potato until soft.", "Roast asparagus with a pinch of salt."],
                "health_notes": "Rich in omega-3s for joint health and recovery.",
                "calories": 800,
                "protein_g": 60,
                "carbs_g": 140,
                "fats_g": 35,
                "fiber_g": 15
            }
        ]
    else:
        cal = 1800 if "sedentary" in level else (2100 if "light" in level else 2400)
        daily_totals = {"calories": cal, "protein_g": 120, "carbs_g": 260, "fats_g": 60, "fiber_g": 28}
        meals = [
            {
                "type": "Breakfast",
                "name": "Greek Yogurt Bowl",
                "image_url": "https://images.unsplash.com/photo-1493770348161-369560ae357d?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["1 cup Greek yogurt", "1 tbsp honey", "Chia seeds", "Mixed berries"],
                "steps": ["Scoop yogurt into a bowl.", "Top with berries and seeds.", "Drizzle with honey."],
                "health_notes": "Probiotics for gut health.",
                "calories": 400,
                "protein_g": 25,
                "carbs_g": 50,
                "fats_g": 10,
                "fiber_g": 8
            },
            {
                "type": "Lunch",
                "name": "Turkey Breast Wrap",
                "image_url": "https://images.unsplash.com/photo-1626804475297-41607ea0d5eb?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["Whole wheat tortilla", "Sliced turkey breast", "Avocado", "Lettuce and tomato"],
                "steps": ["Lay tortilla flat.", "Layer turkey, avocado, and veggies.", "Roll tightly and slice in half."],
                "health_notes": "Balanced macronutrients for sustained midday energy.",
                "calories": 600,
                "protein_g": 40,
                "carbs_g": 80,
                "fats_g": 20,
                "fiber_g": 10
            },
            {
                "type": "Dinner",
                "name": "Chicken & Mediterranean Veggies",
                "image_url": "https://images.unsplash.com/photo-1532550907401-a500c9a57435?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["150g chicken breast", "Zucchini", "Bell peppers", "Olive oil"],
                "steps": ["Chop veggies and toss in olive oil.", "Roast alongside chicken at 400F for 25 mins."],
                "health_notes": "Rich in vitamins and antioxidants.",
                "calories": 800,
                "protein_g": 55,
                "carbs_g": 130,
                "fats_g": 30,
                "fiber_g": 10
            }
        ]
        
    nutrition_plan = {
        "daily_totals": daily_totals,
        "days": []
    }
    for day in meal_days:
        day_meals = []
        for m in meals:
            m_copy = m.copy()
            m_copy["completed"] = False
            day_meals.append(m_copy)
        nutrition_plan["days"].append({
            "day": day,
            "actual_totals": {"calories": 0, "protein_g": 0, "carbs_g": 0, "fats_g": 0, "fiber_g": 0},
            "meals": day_meals
        })
        
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
        .where(UserGoal.user_id == current_user.id, UserGoal.has_meal_plan == True, UserGoal.is_active == True)
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


ALTERNATIVE_MEALS = {
    "loss": {
        "Breakfast": [
            {
                "type": "Breakfast",
                "name": "Avocado Toast with Poached Egg",
                "image_url": "https://images.unsplash.com/photo-1525351484163-7529414344d8?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["1 slice whole wheat bread", "1/2 avocado", "1 poached egg", "Salt and pepper"],
                "steps": ["Toast the bread.", "Mash avocado and spread on toast.", "Top with poached egg.", "Season to taste."],
                "health_notes": "Healthy fats from avocado and high-quality protein from egg.",
                "calories": 300,
                "protein_g": 12,
                "carbs_g": 20,
                "fats_g": 18,
                "fiber_g": 6
            },
            {
                "type": "Breakfast",
                "name": "Chia Seed Pudding",
                "image_url": "https://images.unsplash.com/photo-1517673132405-a56a62b18caf?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["3 tbsp chia seeds", "1 cup almond milk", "1 tsp honey", "Mixed berries"],
                "steps": ["Mix chia seeds, almond milk, and honey in a jar.", "Refrigerate overnight.", "Top with fresh berries before serving."],
                "health_notes": "Rich in fiber and omega-3 fatty acids.",
                "calories": 250,
                "protein_g": 6,
                "carbs_g": 35,
                "fats_g": 9,
                "fiber_g": 11
            },
            {
                "type": "Breakfast",
                "name": "Berry Protein Smoothie",
                "image_url": "https://images.unsplash.com/photo-1553530666-ba11a7da3888?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["1 cup mixed berries", "1 scoop vanilla protein powder", "1 cup almond milk", "1 tbsp chia seeds"],
                "steps": ["Blend all ingredients until smooth.", "Pour into a glass and serve chilled."],
                "health_notes": "Antioxidant rich berries combined with recovery whey protein.",
                "calories": 280,
                "protein_g": 25,
                "carbs_g": 30,
                "fats_g": 5,
                "fiber_g": 8
            },
            {
                "type": "Breakfast",
                "name": "Spinach & Mushroom Omelet",
                "image_url": "https://images.unsplash.com/photo-1525351484163-7529414344d8?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["3 egg whites", "1 whole egg", "1/2 cup spinach", "1/4 cup sliced mushrooms", "1 slice whole grain toast"],
                "steps": ["Sauté spinach and mushrooms in a pan.", "Whisk eggs and pour into pan.", "Cook until solid, fold, and serve with toast."],
                "health_notes": "Very low calorie density and extremely high satiety.",
                "calories": 240,
                "protein_g": 20,
                "carbs_g": 6,
                "fats_g": 16,
                "fiber_g": 2
            },
            {
                "type": "Breakfast",
                "name": "Greek Yogurt Parfait",
                "image_url": "https://images.unsplash.com/photo-1488477181946-6428a0291777?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["1 cup low fat Greek yogurt", "1/2 cup strawberries", "2 tbsp low sugar granola", "1 tsp stevia or honey"],
                "steps": ["Layer Greek yogurt, strawberries, and granola in a glass.", "Drizzle with honey and serve."],
                "health_notes": "Probiotic-rich breakfast with muscle-sparing protein content.",
                "calories": 220,
                "protein_g": 18,
                "carbs_g": 25,
                "fats_g": 4,
                "fiber_g": 3
            },
            {
                "type": "Breakfast",
                "name": "Smoked Salmon Scramble",
                "image_url": "https://images.unsplash.com/photo-1525351484163-7529414344d8?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["3 eggs", "50g smoked salmon", "Dill and chives", "1/2 cup cucumber slices"],
                "steps": ["Whisk eggs and cook in a pan on medium-low.", "Stir in smoked salmon and herbs just before egg sets.", "Serve with cucumber slices."],
                "health_notes": "High omega-3 profile, ideal for hormone health during fat loss.",
                "calories": 290,
                "protein_g": 26,
                "carbs_g": 2,
                "fats_g": 20,
                "fiber_g": 0
            }
        ],
        "Lunch": [
            {
                "type": "Lunch",
                "name": "Turkey and Hummus Wrap",
                "image_url": "https://images.unsplash.com/photo-1626804475297-41607ea0d5eb?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["1 whole wheat tortilla", "100g sliced turkey breast", "2 tbsp hummus", "Spinach and cucumber"],
                "steps": ["Spread hummus on the tortilla.", "Layer turkey and fresh vegetables.", "Roll tightly and serve."],
                "health_notes": "High protein, low fat, and packed with vitamins.",
                "calories": 400,
                "protein_g": 35,
                "carbs_g": 40,
                "fats_g": 12,
                "fiber_g": 7
            },
            {
                "type": "Lunch",
                "name": "Quinoa Salad Bowl",
                "image_url": "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["1 cup cooked quinoa", "Black beans", "Sweet corn", "Lime-cilantro dressing"],
                "steps": ["Combine quinoa, beans, and corn in a bowl.", "Toss with dressing.", "Serve chilled."],
                "health_notes": "Fiber-rich and plant-based protein source.",
                "calories": 450,
                "protein_g": 15,
                "carbs_g": 75,
                "fats_g": 10,
                "fiber_g": 12
            },
            {
                "type": "Lunch",
                "name": "Tuna Salad Lettuce Cups",
                "image_url": "https://images.unsplash.com/photo-1543339308-43e59d6b73a6?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["1 can drained light tuna", "1 tbsp Greek yogurt", "Celery", "4 large romaine lettuce leaves"],
                "steps": ["Mix tuna, Greek yogurt, and chopped celery in a bowl.", "Spoon into romaine leaves and serve."],
                "health_notes": "Very low carb, high protein meal that cuts calories while keeping muscles full.",
                "calories": 320,
                "protein_g": 28,
                "carbs_g": 8,
                "fats_g": 16,
                "fiber_g": 2
            },
            {
                "type": "Lunch",
                "name": "Lemon Grilled Chicken Salad",
                "image_url": "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["150g chicken breast", "Mixed greens", "Lemon juice", "Olive oil dressing"],
                "steps": ["Grill chicken breast until cooked.", "Toss greens, lemon juice, and olive oil.", "Slice chicken and place on top."],
                "health_notes": "Classic clean diet staple for accelerating metabolic rate.",
                "calories": 380,
                "protein_g": 40,
                "carbs_g": 15,
                "fats_g": 14,
                "fiber_g": 5
            },
            {
                "type": "Lunch",
                "name": "Lentil & Veggie Soup",
                "image_url": "https://images.unsplash.com/photo-1547592165-e1d17fed6005?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["1 cup brown lentils", "Carrots and celery", "Vegetable broth", "Spinach"],
                "steps": ["Simmer lentils, carrots, and celery in broth for 25 mins.", "Stir in spinach at the end.", "Serve hot."],
                "health_notes": "Very filling plant meal with prebiotic fiber for fat burning support.",
                "calories": 300,
                "protein_g": 18,
                "carbs_g": 48,
                "fats_g": 4,
                "fiber_g": 14
            },
            {
                "type": "Lunch",
                "name": "Mediterranean Chickpea Salad",
                "image_url": "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["1 cup chickpeas", "Cherry tomatoes", "Cucumber", "Feta cheese", "Lemon juice"],
                "steps": ["Toss chickpeas, chopped tomatoes, and cucumbers.", "Crumble feta over it and splash with lemon juice."],
                "health_notes": "Balanced vegetarian lunch with low glycemic index profile.",
                "calories": 360,
                "protein_g": 14,
                "carbs_g": 52,
                "fats_g": 12,
                "fiber_g": 10
            }
        ],
        "Dinner": [
            {
                "type": "Dinner",
                "name": "Tofu Vegetable Stir-Fry",
                "image_url": "https://images.unsplash.com/photo-1532550907401-a500c9a57435?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["150g firm tofu", "Mixed stir-fry veggies", "1 tbsp low-sodium soy sauce", "Olive oil"],
                "steps": ["Cube tofu and pan-fry until golden.", "Sauté veggies in a splash of olive oil.", "Combine and stir in soy sauce."],
                "health_notes": "Low calorie, mineral-rich, and entirely plant-based.",
                "calories": 350,
                "protein_g": 20,
                "carbs_g": 30,
                "fats_g": 15,
                "fiber_g": 8
            },
            {
                "type": "Dinner",
                "name": "Baked Salmon with Asparagus",
                "image_url": "https://images.unsplash.com/photo-1467003909585-2f8a72700288?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["150g salmon filet", "1 bunch asparagus", "Lemon slices", "Olive oil"],
                "steps": ["Preheat oven to 400F.", "Place salmon and asparagus on a baking sheet.", "Drizzle with oil, top with lemon, and bake for 12-15 mins."],
                "health_notes": "Omega-3 rich dinner for cell repair and metabolic health.",
                "calories": 500,
                "protein_g": 40,
                "carbs_g": 10,
                "fats_g": 35,
                "fiber_g": 4
            },
            {
                "type": "Dinner",
                "name": "Garlic Butter Shrimp with Zoodles",
                "image_url": "https://images.unsplash.com/photo-1539750797207-44f772e80968?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["150g raw shrimp", "2 medium zucchini (spiralized)", "1 tbsp butter", "Garlic"],
                "steps": ["Sauté garlic in butter.", "Cook shrimp until pink, then stir in zucchini noodles for 2 minutes.", "Serve immediately."],
                "health_notes": "Extremely low-calorie meal with plenty of clean muscle-saving protein.",
                "calories": 310,
                "protein_g": 30,
                "carbs_g": 12,
                "fats_g": 16,
                "fiber_g": 3
            },
            {
                "type": "Dinner",
                "name": "Grilled Chicken with Steamed Broccoli",
                "image_url": "https://images.unsplash.com/photo-1532550907401-a500c9a57435?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["180g chicken breast", "2 cups broccoli florets", "1 tsp olive oil", "Garlic powder"],
                "steps": ["Grill chicken seasoned with garlic powder.", "Steam broccoli until tender and drizzle with oil.", "Serve together."],
                "health_notes": "Classic fitness staple for maximizing lean body mass configuration.",
                "calories": 420,
                "protein_g": 45,
                "carbs_g": 20,
                "fats_g": 10,
                "fiber_g": 6
            },
            {
                "type": "Dinner",
                "name": "Baked White Fish with Herbs",
                "image_url": "https://images.unsplash.com/photo-1519708227418-c8fd9a32b7a2?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["150g cod or haddock", "1 cup cherry tomatoes", "Fresh parsley", "Lemon juice"],
                "steps": ["Bake fish and cherry tomatoes at 375F for 18 minutes.", "Squeeze lemon juice and top with fresh parsley.", "Serve."],
                "health_notes": "Very light dinner, easily digestible to improve sleep cycle recovery.",
                "calories": 330,
                "protein_g": 32,
                "carbs_g": 8,
                "fats_g": 12,
                "fiber_g": 3
            },
            {
                "type": "Dinner",
                "name": "Turkey Burger Lettuce Wrap",
                "image_url": "https://images.unsplash.com/photo-1626804475297-41607ea0d5eb?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["150g ground turkey patty", "2 large iceberg lettuce leaves", "Tomato slice", "Red onion"],
                "steps": ["Pan-fry turkey patty until cooked.", "Wrap in lettuce leaves along with tomato and red onion.", "Serve."],
                "health_notes": "Low calorie hamburger alternative offering pure protein.",
                "calories": 380,
                "protein_g": 34,
                "carbs_g": 12,
                "fats_g": 18,
                "fiber_g": 4
            }
        ]
    },
    "gain": {
        "Breakfast": [
            {
                "type": "Breakfast",
                "name": "Scrambled Eggs & Whole Wheat Bagel",
                "image_url": "https://images.unsplash.com/photo-1525351484163-7529414344d8?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["3 whole eggs", "1 whole wheat bagel", "1 tbsp butter", "Spinach"],
                "steps": ["Scramble eggs in butter.", "Toast bagel.", "Serve together with fresh spinach."],
                "health_notes": "Calorie dense, high protein, and loaded with essential nutrients.",
                "calories": 650,
                "protein_g": 35,
                "carbs_g": 60,
                "fats_g": 25,
                "fiber_g": 6
            },
            {
                "type": "Breakfast",
                "name": "Peanut Butter Banana Toast",
                "image_url": "https://images.unsplash.com/photo-1517673132405-a56a62b18caf?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["2 slices thick whole grain bread", "2 tbsp peanut butter", "1 banana", "Chia seeds"],
                "steps": ["Toast the bread.", "Spread peanut butter evenly.", "Top with sliced banana and sprinkle chia seeds."],
                "health_notes": "High healthy fats and complex carbs for energy.",
                "calories": 550,
                "protein_g": 18,
                "carbs_g": 70,
                "fats_g": 25,
                "fiber_g": 12
            },
            {
                "type": "Breakfast",
                "name": "High Protein Oatmeal (Whey)",
                "image_url": "https://images.unsplash.com/photo-1517673132405-a56a62b18caf?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["1.5 cups oats", "1.5 scoops chocolate protein powder", "1 cup milk", "1/2 cup blueberries"],
                "steps": ["Cook oats in milk.", "Stir in protein powder off heat.", "Top with blueberries and serve."],
                "health_notes": "Slow-release carbs and premium proteins to sustain muscle building.",
                "calories": 600,
                "protein_g": 40,
                "carbs_g": 75,
                "fats_g": 14,
                "fiber_g": 9
            },
            {
                "type": "Breakfast",
                "name": "Meat Lover's Egg Scramble",
                "image_url": "https://images.unsplash.com/photo-1525351484163-7529414344d8?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["4 whole eggs", "50g cooked turkey bacon", "50g diced chicken sausage", "1/2 cup cheddar cheese"],
                "steps": ["Scramble eggs in pan.", "Fold in cooked meats and top with cheese to melt.", "Serve warm."],
                "health_notes": "Extremely calorie and protein dense for mass gainer phase.",
                "calories": 700,
                "protein_g": 48,
                "carbs_g": 15,
                "fats_g": 48,
                "fiber_g": 2
            },
            {
                "type": "Breakfast",
                "name": "Power Protein Pancakes",
                "image_url": "https://images.unsplash.com/photo-1493770348161-369560ae357d?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["1 cup protein pancake mix", "1 whole egg", "1 tbsp syrup", "1/2 cup raspberries"],
                "steps": ["Prepare pancakes on griddle using the mix and egg.", "Top with syrup and raspberries.", "Serve."],
                "health_notes": "Dense carbohydrates paired with quick-acting amino acids.",
                "calories": 650,
                "protein_g": 38,
                "carbs_g": 85,
                "fats_g": 12,
                "fiber_g": 8
            },
            {
                "type": "Breakfast",
                "name": "Cottage Cheese & Fruit Bowl",
                "image_url": "https://images.unsplash.com/photo-1488477181946-6428a0291777?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["1.5 cups full fat cottage cheese", "1 sliced apple", "1/4 cup walnuts", "2 tbsp honey"],
                "steps": ["Place cottage cheese in a large bowl.", "Top with apple slices and walnuts.", "Drizzle honey on top and eat."],
                "health_notes": "Slow-release casein protein ideal to prevent morning muscle catabolism.",
                "calories": 500,
                "protein_g": 32,
                "carbs_g": 55,
                "fats_g": 10,
                "fiber_g": 6
            }
        ],
        "Lunch": [
            {
                "type": "Lunch",
                "name": "Tuna Pasta Salad",
                "image_url": "https://images.unsplash.com/photo-1543339308-43e59d6b73a6?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["150g canned tuna", "1.5 cups cooked whole wheat pasta", "1 tbsp olive oil mayonnaise", "Peas"],
                "steps": ["Boil and drain pasta.", "Mix tuna, peas, and mayo in a bowl.", "Toss with pasta and refrigerate."],
                "health_notes": "Excellent carb-to-protein ratio for muscle building.",
                "calories": 750,
                "protein_g": 48,
                "carbs_g": 95,
                "fats_g": 18,
                "fiber_g": 9
            },
            {
                "type": "Lunch",
                "name": "Turkey & Avocado Sandwich",
                "image_url": "https://images.unsplash.com/photo-1626804475297-41607ea0d5eb?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["4 slices turkey breast", "2 slices whole grain bread", "1/2 avocado", "Swiss cheese"],
                "steps": ["Assemble sandwich with turkey, cheese, and mashed avocado.", "Grill slightly if desired."],
                "health_notes": "Healthy fats and fast digesting proteins.",
                "calories": 600,
                "protein_g": 38,
                "carbs_g": 50,
                "fats_g": 26,
                "fiber_g": 10
            },
            {
                "type": "Lunch",
                "name": "Beef & Jasmine Rice Bowl",
                "image_url": "https://images.unsplash.com/photo-1543339308-43e59d6b73a6?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["200g lean beef mince", "1.5 cups jasmine rice", "Green beans", "Soy sauce"],
                "steps": ["Brown beef in a skillet.", "Steam rice and beans.", "Combine and drizzle with soy sauce."],
                "health_notes": "High carbs to replenish glycogen post-workout.",
                "calories": 850,
                "protein_g": 55,
                "carbs_g": 110,
                "fats_g": 22,
                "fiber_g": 6
            },
            {
                "type": "Lunch",
                "name": "Grilled Chicken with Sweet Potato",
                "image_url": "https://images.unsplash.com/photo-1532550907401-a500c9a57435?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["200g chicken breast", "1 large baked sweet potato", "1 cup green beans"],
                "steps": ["Grill chicken breast until cooked.", "Bake sweet potato and serve with steamed green beans."],
                "health_notes": "Clean bulking meal containing essential complex carbohydrates.",
                "calories": 700,
                "protein_g": 50,
                "carbs_g": 90,
                "fats_g": 12,
                "fiber_g": 8
            },
            {
                "type": "Lunch",
                "name": "Salmon & Brown Rice Plate",
                "image_url": "https://images.unsplash.com/photo-1467003909585-2f8a72700288?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["180g salmon filet", "1.5 cups brown rice", "Roasted carrots"],
                "steps": ["Pan-sear salmon.", "Cook brown rice and roast carrots at 400F for 20 mins.", "Combine on a plate."],
                "health_notes": "Packed with healthy omega-3 fatty acids for joint lubrication.",
                "calories": 800,
                "protein_g": 45,
                "carbs_g": 85,
                "fats_g": 28,
                "fiber_g": 7
            },
            {
                "type": "Lunch",
                "name": "Loaded Quinoa & Steak Bowl",
                "image_url": "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["180g flank steak", "1.5 cups cooked quinoa", "1/2 cup black beans", "1/2 avocado"],
                "steps": ["Grill steak and slice thin.", "Arrange quinoa, steak slices, black beans, and avocado in a bowl.", "Serve."],
                "health_notes": "Premium micronutrient density for athletic strength phases.",
                "calories": 900,
                "protein_g": 58,
                "carbs_g": 100,
                "fats_g": 32,
                "fiber_g": 11
            }
        ],
        "Dinner": [
            {
                "type": "Dinner",
                "name": "Teriyaki Chicken and Rice",
                "image_url": "https://images.unsplash.com/photo-1532550907401-a500c9a57435?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["200g chicken thigh", "1.5 cups white jasmine rice", "Teriyaki sauce", "Broccoli"],
                "steps": ["Pan-fry chicken thighs until cooked through.", "Toss with teriyaki sauce.", "Serve with steamed rice and broccoli."],
                "health_notes": "Rich in protein and fast carbs to accelerate post-workout recovery.",
                "calories": 850,
                "protein_g": 52,
                "carbs_g": 110,
                "fats_g": 22,
                "fiber_g": 6
            },
            {
                "type": "Dinner",
                "name": "Ribeye Steak & Loaded Potato",
                "image_url": "https://images.unsplash.com/photo-1543339308-43e59d6b73a6?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["200g ribeye steak", "1 large russet potato", "Sour cream", "Chives"],
                "steps": ["Sear steak in a hot skillet to desired doneness.", "Bake potato, slice open, and top with sour cream and chives."],
                "health_notes": "High protein, zinc, and iron for muscle synthesis.",
                "calories": 950,
                "protein_g": 58,
                "carbs_g": 70,
                "fats_g": 48,
                "fiber_g": 8
            },
            {
                "type": "Dinner",
                "name": "Pork Chops with Roasted Potatoes",
                "image_url": "https://images.unsplash.com/photo-1543339308-43e59d6b73a6?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["200g pork chops", "1.5 cups baby potatoes (halved)", "Olive oil", "Rosemary"],
                "steps": ["Pan-sear pork chops with herbs.", "Toss potatoes in oil and rosemary, roast at 400F for 25 mins.", "Serve."],
                "health_notes": "Clean high protein density that breaks up chicken boredom.",
                "calories": 800,
                "protein_g": 46,
                "carbs_g": 65,
                "fats_g": 30,
                "fiber_g": 7
            },
            {
                "type": "Dinner",
                "name": "Salmon Pasta in Garlic Cream",
                "image_url": "https://images.unsplash.com/photo-1467003909585-2f8a72700288?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["150g cooked salmon", "1.5 cups penne pasta", "1/4 cup heavy cream", "Garlic and parsley"],
                "steps": ["Boil penne pasta.", "Warm cream and garlic in a pan, toss with pasta.", "Flake salmon and stir in with parsley.", "Serve."],
                "health_notes": "Excellent calorie surplus profile to support heavy leg-day recovery.",
                "calories": 900,
                "protein_g": 50,
                "carbs_g": 105,
                "fats_g": 34,
                "fiber_g": 6
            },
            {
                "type": "Dinner",
                "name": "Beef Stir-Fry with Egg Noodles",
                "image_url": "https://images.unsplash.com/photo-1532550907401-a500c9a57435?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["200g beef sirloin strips", "1.5 cups egg noodles", "Bell peppers", "Stir-fry sauce"],
                "steps": ["Sauté beef and peppers.", "Boil noodles and combine in pan.", "Stir in sauce for 2 minutes and serve."],
                "health_notes": "High carbohydrate load to quickly fill depleted glycogen stores.",
                "calories": 880,
                "protein_g": 54,
                "carbs_g": 95,
                "fats_g": 28,
                "fiber_g": 8
            },
            {
                "type": "Dinner",
                "name": "Grilled Turkey Breast with Rice",
                "image_url": "https://images.unsplash.com/photo-1626804475297-41607ea0d5eb?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["200g turkey breast", "1.5 cups white rice", "Roasted cauliflower"],
                "steps": ["Grill turkey breast.", "Boil rice and steam cauliflower.", "Serve together."],
                "health_notes": "Very clean muscle gainer profile with trace fats.",
                "calories": 750,
                "protein_g": 48,
                "carbs_g": 90,
                "fats_g": 18,
                "fiber_g": 5
            }
        ]
    },
    "general": {
        "Breakfast": [
            {
                "type": "Breakfast",
                "name": "Fruit Smoothie Bowl",
                "image_url": "https://images.unsplash.com/photo-1493770348161-369560ae357d?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["1 cup frozen berries", "1 banana", "1/2 cup almond milk", "Granola"],
                "steps": ["Blend berries, banana, and almond milk until smooth.", "Pour into a bowl and top with granola."],
                "health_notes": "Vitamins, antioxidants, and a quick energy boost.",
                "calories": 350,
                "protein_g": 8,
                "carbs_g": 65,
                "fats_g": 6,
                "fiber_g": 9
            },
            {
                "type": "Breakfast",
                "name": "Scrambled Eggs with Veggies",
                "image_url": "https://images.unsplash.com/photo-1525351484163-7529414344d8?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["2 eggs", "Bell peppers", "Onions", "1 slice whole wheat toast"],
                "steps": ["Sauté chopped peppers and onions.", "Whisk in eggs and scramble.", "Serve with toast."],
                "health_notes": "Balanced protein and micronutrients.",
                "calories": 380,
                "protein_g": 20,
                "carbs_g": 30,
                "fats_g": 16,
                "fiber_g": 5
            },
            {
                "type": "Breakfast",
                "name": "Overnight Oats with Honey",
                "image_url": "https://images.unsplash.com/photo-1517673132405-a56a62b18caf?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["1 cup rolled oats", "1 cup almond milk", "1 tbsp honey", "Walnuts"],
                "steps": ["Mix oats, almond milk, and honey in a jar.", "Leave in fridge overnight.", "Top with walnuts and eat."],
                "health_notes": "Excellent dietary fiber source supporting heart health.",
                "calories": 400,
                "protein_g": 12,
                "carbs_g": 65,
                "fats_g": 8,
                "fiber_g": 8
            },
            {
                "type": "Breakfast",
                "name": "Whole Wheat Pancakes with Berries",
                "image_url": "https://images.unsplash.com/photo-1493770348161-369560ae357d?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["1 cup whole wheat pancake mix", "1 egg", "1/2 cup fresh blueberries"],
                "steps": ["Prepare pancakes on skillet.", "Top with blueberries and serve."],
                "health_notes": "Complex carb profile with zero artificial sugars.",
                "calories": 420,
                "protein_g": 14,
                "carbs_g": 75,
                "fats_g": 6,
                "fiber_g": 8
            },
            {
                "type": "Breakfast",
                "name": "Toast with Hummus and Tomatoes",
                "image_url": "https://images.unsplash.com/photo-1525351484163-7529414344d8?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["2 slices rye bread", "3 tbsp hummus", "Cherry tomatoes", "Olive oil"],
                "steps": ["Toast rye bread.", "Spread hummus, top with sliced tomatoes and drizzle olive oil.", "Serve."],
                "health_notes": "Mediterranean diet inspired, vegan-friendly breakfast option.",
                "calories": 360,
                "protein_g": 12,
                "carbs_g": 45,
                "fats_g": 14,
                "fiber_g": 7
            },
            {
                "type": "Breakfast",
                "name": "Avocado and Cottage Cheese Toast",
                "image_url": "https://images.unsplash.com/photo-1488477181946-6428a0291777?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["1 slice sourdough bread", "1/2 avocado", "1/2 cup cottage cheese"],
                "steps": ["Toast sourdough bread.", "Spread cottage cheese, top with sliced avocado.", "Season with black pepper and serve."],
                "health_notes": "Balanced fats and proteins that release energy steadily.",
                "calories": 390,
                "protein_g": 18,
                "carbs_g": 35,
                "fats_g": 16,
                "fiber_g": 6
            }
        ],
        "Lunch": [
            {
                "type": "Lunch",
                "name": "Chickpea Salad Wrap",
                "image_url": "https://images.unsplash.com/photo-1626804475297-41607ea0d5eb?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["1 cup mashed chickpeas", "1 tbsp light mayo", "Celery", "Whole wheat wrap"],
                "steps": ["Mix chickpeas, celery, and mayo.", "Spread onto wrap and roll up."],
                "health_notes": "Plant-based protein, high fiber.",
                "calories": 480,
                "protein_g": 16,
                "carbs_g": 60,
                "fats_g": 14,
                "fiber_g": 12
            },
            {
                "type": "Lunch",
                "name": "Mediterranean Lentil Salad",
                "image_url": "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["1 cup cooked brown lentils", "Cucumber", "Feta cheese", "Olive oil & lemon"],
                "steps": ["Toss lentils, chopped cucumber, and feta.", "Drizzle with olive oil and lemon juice."],
                "health_notes": "Heart-healthy fats and clean proteins.",
                "calories": 420,
                "protein_g": 18,
                "carbs_g": 50,
                "fats_g": 15,
                "fiber_g": 11
            },
            {
                "type": "Lunch",
                "name": "Chicken Caesar Salad (Light)",
                "image_url": "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["120g chicken breast", "2 cups romaine lettuce", "1 tbsp light Caesar dressing", "Parmesan"],
                "steps": ["Grill and slice chicken breast.", "Toss romaine lettuce with dressing.", "Combine and sprinkle cheese on top."],
                "health_notes": "High volume lunch with balanced protein.",
                "calories": 460,
                "protein_g": 32,
                "carbs_g": 20,
                "fats_g": 24,
                "fiber_g": 4
            },
            {
                "type": "Lunch",
                "name": "Quinoa & Veggie Stuffed Peppers",
                "image_url": "https://images.unsplash.com/photo-1547592165-e1d17fed6005?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["2 bell peppers", "1 cup cooked quinoa", "Mixed black beans and corn"],
                "steps": ["Cut peppers in half and clean.", "Mix quinoa, beans, and corn; stuff into peppers.", "Bake at 375F for 20 minutes."],
                "health_notes": "Completely vegetarian, loaded with vitamins and clean carbs.",
                "calories": 410,
                "protein_g": 14,
                "carbs_g": 65,
                "fats_g": 10,
                "fiber_g": 9
            },
            {
                "type": "Lunch",
                "name": "Turkey Breast & Cheese Sandwich",
                "image_url": "https://images.unsplash.com/photo-1626804475297-41607ea0d5eb?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["100g sliced turkey breast", "1 slice provolone", "2 slices wheat bread", "Mustard"],
                "steps": ["Assemble sandwich with turkey, cheese, lettuce, and mustard.", "Serve immediately."],
                "health_notes": "Quick and classic lunch with simple macros.",
                "calories": 450,
                "protein_g": 28,
                "carbs_g": 42,
                "fats_g": 14,
                "fiber_g": 5
            },
            {
                "type": "Lunch",
                "name": "Black Bean and Corn Bowl",
                "image_url": "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["1 cup black beans", "1 cup corn", "Cilantro", "Red onion", "Olive oil dressing"],
                "steps": ["Mix black beans, corn, chopped onion, and cilantro.", "Toss with olive oil dressing and serve."],
                "health_notes": "Excellent dietary fiber profile for gut health.",
                "calories": 430,
                "protein_g": 15,
                "carbs_g": 68,
                "fats_g": 12,
                "fiber_g": 11
            }
        ],
        "Dinner": [
            {
                "type": "Dinner",
                "name": "Turkey Meatballs & Spaghetti Squash",
                "image_url": "https://images.unsplash.com/photo-1532550907401-a500c9a57435?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["150g turkey meatballs", "1 medium spaghetti squash", "Marinara sauce"],
                "steps": ["Bake spaghetti squash, scrape out strands.", "Warm meatballs in marinara sauce.", "Serve meatballs and sauce over squash."],
                "health_notes": "Low carb, high protein alternative to pasta.",
                "calories": 550,
                "protein_g": 38,
                "carbs_g": 40,
                "fats_g": 22,
                "fiber_g": 8
            },
            {
                "type": "Dinner",
                "name": "Lemon Herb Grilled Chicken",
                "image_url": "https://images.unsplash.com/photo-1519708227418-c8fd9a32b7a2?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["150g chicken breast", "Zucchini noodles", "Pesto sauce", "Cherry tomatoes"],
                "steps": ["Marinate and grill chicken breast.", "Sauté zucchini noodles with pesto and tomatoes.", "Slice chicken and place on top."],
                "health_notes": "Light, clean, low sodium dinner.",
                "calories": 500,
                "protein_g": 45,
                "carbs_g": 15,
                "fats_g": 28,
                "fiber_g": 4
            },
            {
                "type": "Dinner",
                "name": "Baked Cod with Mixed Roasted Veggies",
                "image_url": "https://images.unsplash.com/photo-1519708227418-c8fd9a32b7a2?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["150g cod filet", "1 cup cherry tomatoes", "1 cup sliced zucchini", "Olive oil"],
                "steps": ["Place cod and veggies on a baking sheet, drizzle with olive oil.", "Bake at 400F for 18 minutes.", "Serve."],
                "health_notes": "Rich in lean protein and essential minerals.",
                "calories": 480,
                "protein_g": 32,
                "carbs_g": 35,
                "fats_g": 18,
                "fiber_g": 7
            },
            {
                "type": "Dinner",
                "name": "Teriyaki Tofu Bowl with Brown Rice",
                "image_url": "https://images.unsplash.com/photo-1532550907401-a500c9a57435?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["150g tofu", "1 cup brown rice", "Teriyaki sauce", "Broccoli"],
                "steps": ["Pan-sear tofu and cook brown rice.", "Steam broccoli.", "Assemble in a bowl and drizzle with teriyaki sauce."],
                "health_notes": "Balanced vegetarian dinner option.",
                "calories": 520,
                "protein_g": 22,
                "carbs_g": 78,
                "fats_g": 14,
                "fiber_g": 9
            },
            {
                "type": "Dinner",
                "name": "Beef & Broccoli Stir-Fry (Light)",
                "image_url": "https://images.unsplash.com/photo-1532550907401-a500c9a57435?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["150g beef flank strips", "2 cups broccoli", "1 tbsp soy sauce", "Ginger"],
                "steps": ["Sauté beef flank strips with ginger.", "Add broccoli and soy sauce, cover and cook for 5 minutes.", "Serve."],
                "health_notes": "High iron and protein dinner choice.",
                "calories": 580,
                "protein_g": 40,
                "carbs_g": 45,
                "fats_g": 22,
                "fiber_g": 6
            },
            {
                "type": "Dinner",
                "name": "Shrimp Scampi with Whole Wheat Pasta",
                "image_url": "https://images.unsplash.com/photo-1539750797207-44f772e80968?q=80&w=400&auto=format&fit=crop",
                "ingredients": ["150g shrimp", "1 cup whole wheat spaghetti", "1 tbsp butter", "Garlic", "Lemon"],
                "steps": ["Boil spaghetti.", "Sauté garlic and shrimp in butter, splash with lemon.", "Toss with pasta and serve."],
                "health_notes": "Delicious high protein seafood dish.",
                "calories": 540,
                "protein_g": 34,
                "carbs_g": 65,
                "fats_g": 14,
                "fiber_g": 6
            }
        ]
    }
}


def get_alternative_meal(goal_str: str, meal_type: str, current_meal_name: str, swap_to_name: str | None = None) -> dict:
    g = goal_str.lower().strip()
    if "loss" in g or "weight" in g:
        category = "loss"
    elif "gain" in g or "muscle" in g or "hypertrophy" in g:
        category = "gain"
    else:
        category = "general"

    mt = meal_type.capitalize().strip()
    if mt not in ["Breakfast", "Lunch", "Dinner"]:
        mt = "Breakfast"

    options = ALTERNATIVE_MEALS.get(category, {}).get(mt, [])
    if swap_to_name:
        for opt in options:
            if opt["name"].lower() == swap_to_name.lower():
                return opt

    for opt in options:
        if opt["name"].lower() != current_meal_name.lower():
            return opt

    if options:
        return options[0]
    return {
        "type": mt,
        "name": "Healthy Alternative Meal",
        "image_url": "https://images.unsplash.com/photo-1493770348161-369560ae357d?q=80&w=400&auto=format&fit=crop",
        "ingredients": ["Various healthy ingredients"],
        "steps": ["Prepare and enjoy."],
        "health_notes": "Balanced nutritious meal.",
        "calories": 400,
        "protein_g": 20,
        "carbs_g": 40,
        "fats_g": 15,
        "fiber_g": 5
    }


def perform_swap_logic(nut_plan: dict, day_name: str, meal_type: str, fitness_goal: str, swap_to_name: str | None = None) -> dict:
    days = nut_plan.get("days", [])
    target_day = None
    for d in days:
        if d.get("day", "").lower() == day_name.lower():
            target_day = d
            break
    
    if not target_day:
        return nut_plan

    meals = target_day.get("meals", [])
    target_meal = None
    for m in meals:
        if m.get("type", "").lower() == meal_type.lower():
            target_meal = m
            break

    if not target_meal:
        return nut_plan

    current_meal_name = target_meal.get("name", "")
    new_meal = get_alternative_meal(fitness_goal, meal_type, current_meal_name, swap_to_name=swap_to_name)
    target_meal.update(new_meal)
    target_meal["completed"] = False

    # Recalculate actual_totals for the day
    actual_totals = {
        "calories": 0,
        "protein_g": 0,
        "carbs_g": 0,
        "fats_g": 0,
        "fiber_g": 0
    }
    for m in meals:
        if m.get("completed", False):
            actual_totals["calories"] += m.get("calories", 0)
            actual_totals["protein_g"] += m.get("protein_g", 0)
            actual_totals["carbs_g"] += m.get("carbs_g", 0)
            actual_totals["fats_g"] += m.get("fats_g", 0)
            actual_totals["fiber_g"] += m.get("fiber_g", 0)
    target_day["actual_totals"] = actual_totals

    return nut_plan


from api.schemas import SwapMealRequest

@router.post("/meal-plans/swap-meal")
async def swap_meal_plan_meal(
    request: SwapMealRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if request.goal_id is not None:
        result = await db.execute(
            select(UserGoal).where(UserGoal.id == request.goal_id, UserGoal.user_id == current_user.id)
        )
        user_goal = result.scalars().first()
        if not user_goal:
            raise HTTPException(status_code=404, detail="Meal plan not found")
        
        if not user_goal.nutrition_plan:
            raise HTTPException(status_code=400, detail="Meal plan does not contain a nutrition plan")

        try:
            nut_plan = json.loads(user_goal.nutrition_plan)
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to parse saved nutrition plan")

        updated_plan = perform_swap_logic(
            nut_plan, request.day, request.meal_type, user_goal.fitness_goal or "General Health", swap_to_name=request.swap_to_name
        )
        
        user_goal.nutrition_plan = json.dumps(updated_plan)
        await db.commit()
        await db.refresh(user_goal)

        from api.schemas import MealPlanResponse
        return MealPlanResponse(
            goal_id=user_goal.id,
            fitness_goal=user_goal.fitness_goal,
            nutrition_plan=updated_plan,
            created_at=user_goal.created_at
        )

    elif request.nutrition_plan is not None:
        fitness_goal = request.nutrition_plan.get("fitness_goal", "General Health")
        updated_plan = perform_swap_logic(
            request.nutrition_plan, request.day, request.meal_type, fitness_goal, swap_to_name=request.swap_to_name
        )
        return {
            "nutrition_plan": updated_plan
        }
    else:
        raise HTTPException(status_code=400, detail="Either goal_id or nutrition_plan must be provided")


from api.schemas import SwapOptionsRequest

@router.post("/meal-plans/swap-options", response_model=list[dict])
async def get_meal_swap_options(
    request: SwapOptionsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    fitness_goal = "General Health"
    nut_plan = None
    
    if request.goal_id is not None:
        result = await db.execute(
            select(UserGoal).where(UserGoal.id == request.goal_id, UserGoal.user_id == current_user.id)
        )
        user_goal = result.scalars().first()
        if not user_goal:
            raise HTTPException(status_code=404, detail="Meal plan not found")
        fitness_goal = user_goal.fitness_goal or "General Health"
        if user_goal.nutrition_plan:
            try:
                nut_plan = json.loads(user_goal.nutrition_plan)
            except Exception:
                pass
        
    elif request.nutrition_plan is not None:
        nut_plan = request.nutrition_plan
        fitness_goal = nut_plan.get("fitness_goal", "General Health")

    g = fitness_goal.lower().strip()
    if "loss" in g or "weight" in g:
        category = "loss"
    elif "gain" in g or "muscle" in g or "hypertrophy" in g:
        category = "gain"
    else:
        category = "general"

    mt = request.meal_type.capitalize().strip()
    if mt not in ["Breakfast", "Lunch", "Dinner"]:
        mt = "Breakfast"

    options = ALTERNATIVE_MEALS.get(category, {}).get(mt, [])

    # Extract current meal details to find closest options
    current_meal = None
    if nut_plan:
        days = nut_plan.get("days", [])
        for d in days:
            if d.get("day", "").lower() == request.day.lower():
                for m in d.get("meals", []):
                    if m.get("type", "").lower() == mt.lower():
                        current_meal = m
                        break
                break

    if current_meal:
        current_name = current_meal.get("name", "").lower()
        current_cals = current_meal.get("calories", 0)
        current_protein = current_meal.get("protein_g", 0)
        current_carbs = current_meal.get("carbs_g", 0)

        # Exclude the current meal itself so it doesn't suggest itself
        candidates = [opt for opt in options if opt["name"].lower() != current_name]

        # Sort by proximity in calories and macros
        def get_dist(opt):
            c_diff = abs(opt.get("calories", 0) - current_cals)
            p_diff = abs(opt.get("protein_g", 0) - current_protein)
            carb_diff = abs(opt.get("carbs_g", 0) - current_carbs)
            return c_diff + 2 * p_diff + carb_diff

        candidates.sort(key=get_dist)
        return candidates[:5]
    else:
        return options[:5]


@router.post("/meal-plans/{goal_id}/activate", response_model=MealPlanResponse)
async def activate_user_meal_plan(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(UserGoal).where(UserGoal.id == goal_id, UserGoal.user_id == current_user.id))
    user_goal = result.scalars().first()
    if not user_goal:
        raise HTTPException(status_code=404, detail="Meal plan not found")
        
    user_goal.is_active = True
    await db.commit()
    await db.refresh(user_goal)
    
    from api.schemas import MealPlanResponse
    nut_plan = {}
    if user_goal.nutrition_plan:
        try:
            nut_plan = json.loads(user_goal.nutrition_plan)
        except Exception:
            pass
            
    return MealPlanResponse(
        goal_id=user_goal.id,
        fitness_goal=user_goal.fitness_goal,
        nutrition_plan=nut_plan,
        created_at=user_goal.created_at
    )


from api.schemas import CompleteMealRequest

@router.post("/meal-plans/complete-meal", response_model=MealPlanResponse)
async def complete_meal_plan_meal(
    request: CompleteMealRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(UserGoal).where(UserGoal.id == request.goal_id, UserGoal.user_id == current_user.id)
    )
    user_goal = result.scalars().first()
    if not user_goal:
        raise HTTPException(status_code=404, detail="Meal plan not found")
        
    if not user_goal.nutrition_plan:
        raise HTTPException(status_code=400, detail="Meal plan does not contain a nutrition plan")

    try:
        nut_plan = json.loads(user_goal.nutrition_plan)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to parse saved nutrition plan")

    # Locate day and meal
    days = nut_plan.get("days", [])
    target_day = None
    for d in days:
        if d.get("day", "").lower() == request.day.lower():
            target_day = d
            break
            
    if not target_day:
        raise HTTPException(status_code=404, detail=f"Day '{request.day}' not found in nutrition plan")

    meals = target_day.get("meals", [])
    target_meal = None
    for m in meals:
        if m.get("type", "").lower() == request.meal_type.lower():
            target_meal = m
            break
            
    if not target_meal:
        raise HTTPException(status_code=404, detail=f"Meal type '{request.meal_type}' not found in day '{request.day}'")

    # Update completed status
    target_meal["completed"] = request.completed

    # Recalculate actual_totals for the day
    actual_totals = {
        "calories": 0,
        "protein_g": 0,
        "carbs_g": 0,
        "fats_g": 0,
        "fiber_g": 0
    }
    for m in meals:
        if m.get("completed", False):
            actual_totals["calories"] += m.get("calories", 0)
            actual_totals["protein_g"] += m.get("protein_g", 0)
            actual_totals["carbs_g"] += m.get("carbs_g", 0)
            actual_totals["fats_g"] += m.get("fats_g", 0)
            actual_totals["fiber_g"] += m.get("fiber_g", 0)
            
    target_day["actual_totals"] = actual_totals

    user_goal.nutrition_plan = json.dumps(nut_plan)
    await db.commit()
    await db.refresh(user_goal)

    from api.schemas import MealPlanResponse
    return MealPlanResponse(
        goal_id=user_goal.id,
        fitness_goal=user_goal.fitness_goal,
        nutrition_plan=nut_plan,
        created_at=user_goal.created_at
    )


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
