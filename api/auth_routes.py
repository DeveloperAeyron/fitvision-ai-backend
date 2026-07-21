from datetime import datetime, timedelta, date
import logging
import os
import random
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import httpx
import secrets

from api.database import get_db
from api.models import User, PWDResetOTP, UserGoal, WorkoutLog, WorkoutLogEvent
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
    WorkoutLogResponse,
    GoalCreateRequest,
    GoalResponse,
    MealCreateRequest,
    MealPlanResponse,
    WorkoutProgressRequest,
    WorkoutProgressResponse,
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
    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "622634184380-1bstt5af3mai3124ne0llm1b42qfrha4.apps.googleusercontent.com")
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
    # Fetch active goal
    goal_res = await db.execute(select(UserGoal).where(UserGoal.user_id == current_user.id, UserGoal.is_active == True))
    active_goal = goal_res.scalars().first()

    if not active_goal:
        return {
            "username": current_user.full_name or current_user.username,
            "email": current_user.email,
            "completion_percentage": 0.0,
            "goals": {
                "workouts": {"current": 0, "target": 0, "unit": "workouts"},
                "reps": {"current": 0, "target": 0, "unit": "reps"},
                "calories": {"current": 0, "target": 0, "unit": "kcal"}
            },
            "weekly_progress": [
                {"day": "Mon", "percentage": 0.0},
                {"day": "Tue", "percentage": 0.0},
                {"day": "Wed", "percentage": 0.0},
                {"day": "Thu", "percentage": 0.0},
                {"day": "Fri", "percentage": 0.0},
                {"day": "Sat", "percentage": 0.0},
                {"day": "Sun", "percentage": 0.0}
            ],
            "next_workout": None,
            "lastModifiedAt": datetime.utcnow()
        }

    # Query this week's workout logs for the active goal
    today = datetime.utcnow().date()
    start_of_week = datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time())
    end_of_week = start_of_week + timedelta(days=7)

    logs_result = await db.execute(
        select(WorkoutLog).where(
            WorkoutLog.user_id == current_user.id,
            WorkoutLog.goal_id == active_goal.id,
            WorkoutLog.workout_date >= start_of_week.date(),
            WorkoutLog.workout_date < end_of_week.date()
        )
    )
    logs = logs_result.scalars().all()

    workouts_current = sum(1 for log in logs if log.is_completed)
    reps_current = sum(log.reps for log in logs)
    calories_current = sum(log.calories for log in logs)

    target_workouts = active_goal.target_workouts
    target_reps = active_goal.target_reps
    target_calories = active_goal.target_calories

    w_pct = (workouts_current / target_workouts) if target_workouts > 0 else 0
    r_pct = (reps_current / target_reps) if target_reps > 0 else 0
    c_pct = (calories_current / target_calories) if target_calories > 0 else 0
    
    completion_percentage = round(((min(w_pct, 1.0) + min(r_pct, 1.0) + min(c_pct, 1.0)) / 3.0) * 100.0, 1)

    # Calculate weekly progress (calories per day / daily target calories)
    daily_target_calories = target_calories / 7.0 if target_calories > 0 else 2000.0
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    progress_by_day = {day: 0.0 for day in day_names}

    for log in logs:
        day_idx = log.workout_date.weekday()
        day_str = day_names[day_idx]
        progress_by_day[day_str] += log.calories

    weekly_progress = []
    for day in day_names:
        pct = (progress_by_day[day] / daily_target_calories) * 100.0 if daily_target_calories > 0 else 0.0
        weekly_progress.append({"day": day, "percentage": min(round(pct, 1), 100.0)})

    # Next workout
    next_workout = None
    if active_goal.workout_plan:
        import json
        try:
            w_plan = json.loads(active_goal.workout_plan)
            # Find the workout for today or next day
            today_day_str = today.strftime("%A") # "Monday"
            days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            today_idx = days_order.index(today_day_str)
            
            # Reorder w_plan to start from today
            ordered_days = days_order[today_idx:] + days_order[:today_idx]
            
            for d in ordered_days:
                workout_for_day = next((w for w in w_plan if w.get("day") == d), None)
                if workout_for_day:
                    time_str = "TODAY" if d == today_day_str else d.upper()
                    if d != today_day_str and days_order.index(d) == (today_idx + 1) % 7:
                        time_str = "TOMORROW"
                    
                    time_val = active_goal.available_time or "7:00 PM"
                    
                    next_workout = {
                        "title": workout_for_day.get("workout_name", "Workout"),
                        "time": f"{time_str} {time_val}",
                        "duration": f"{workout_for_day.get('duration_minutes', 45)} min",
                        "location": "Gym",
                        "type": "Strength" if "Hypertrophy" in workout_for_day.get("workout_name", "") else "Cardio",
                        "difficulty": active_goal.activity_level or "Intermediate"
                    }
                    break
        except Exception as e:
            pass

    return {
        "username": current_user.full_name or current_user.username,
        "email": current_user.email,
        "completion_percentage": completion_percentage,
        "goals": {
            "workouts": {"current": workouts_current, "target": target_workouts, "unit": "workouts"},
            "reps": {"current": reps_current, "target": target_reps, "unit": "reps"},
            "calories": {"current": calories_current, "target": target_calories, "unit": "kcal"}
        },
        "weekly_progress": weekly_progress,
        "next_workout": next_workout,
        "lastModifiedAt": datetime.utcnow()
    }


@router.post("/workouts/log", status_code=status.HTTP_201_CREATED)
async def log_workout(
    request: WorkoutLogCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    log_time = request.created_at if request.created_at else datetime.utcnow()
    normalized_key = " ".join(request.exercise_name.casefold().split())
    new_log = WorkoutLog(
        user_id=current_user.id,
        exercise_name=request.exercise_name,
        exercise_key=normalized_key,
        workout_date=log_time.date(),
        reps=request.reps,
        calories=request.calories,
        duration_minutes=request.duration_minutes,
        duration_seconds=request.duration_minutes * 60,
        goal_id=request.goal_id,
        created_at=log_time,
        is_completed=True
    )
    db.add(new_log)
    await db.commit()
    await db.refresh(new_log)
    return {"message": "Workout logged successfully", "id": new_log.id}


@router.get("/workouts/logs", response_model=list[WorkoutLogResponse])
async def get_workout_logs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WorkoutLog)
        .where(WorkoutLog.user_id == current_user.id)
        .order_by(WorkoutLog.created_at.asc(), WorkoutLog.id.asc())
    )
    return result.scalars().all()


import math
from typing import Optional

@router.post("/workouts/progress", response_model=WorkoutProgressResponse, status_code=status.HTTP_200_OK)
async def log_workout_progress(
    request: WorkoutProgressRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy.dialects.postgresql import insert

    # 1. Validate goal ownership
    goal_result = await db.execute(select(UserGoal).where(UserGoal.id == request.goal_id, UserGoal.user_id == current_user.id))
    if not goal_result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not authorized to log progress for this goal")

    # 2. Normalize exercise key
    normalized_key = " ".join(request.exercise_name.casefold().split())

    # 3. Deltas and recommendations cannot be negative
    if request.reps_delta < 0 or request.duration_seconds_delta < 0 or request.calories_delta < 0:
        raise HTTPException(status_code=400, detail="Deltas cannot be negative")
    if request.recommended_sets < 0 or request.recommended_reps_per_set < 0 or request.recommended_duration_seconds < 0:
        raise HTTPException(status_code=400, detail="Recommendations cannot be negative")

    # 4. Require exactly one recommendation mode
    has_rep_mode = request.recommended_sets > 0 and request.recommended_reps_per_set > 0
    has_time_mode = request.recommended_duration_seconds > 0
    
    if has_rep_mode and has_time_mode:
        raise HTTPException(status_code=400, detail="Cannot mix rep and time recommendations")
    if not has_rep_mode and not has_time_mode:
        raise HTTPException(status_code=400, detail="Must provide either rep or time recommendations")
    if has_rep_mode and request.recommended_duration_seconds > 0:
        raise HTTPException(status_code=400, detail="Rep mode cannot have duration targets")
    if has_time_mode and (request.recommended_sets > 0 or request.recommended_reps_per_set > 0):
        raise HTTPException(status_code=400, detail="Time mode cannot have rep targets")

    # Find or create aggregate
    # Using a transaction for the entire operation
    async with db.begin_nested():
        # We must use INSERT ... ON CONFLICT DO NOTHING to ensure concurrency safety
        stmt = insert(WorkoutLog).values(
            user_id=current_user.id,
            goal_id=request.goal_id,
            exercise_name=request.exercise_name,
            exercise_key=normalized_key,
            workout_date=request.workout_date,
            reps=0,
            calories=0,
            duration_minutes=0,
            duration_seconds=0,
            recommended_sets=request.recommended_sets,
            recommended_reps_per_set=request.recommended_reps_per_set,
            recommended_duration_seconds=request.recommended_duration_seconds,
            is_completed=False
        ).on_conflict_do_nothing(
            index_elements=['user_id', 'goal_id', 'exercise_key', 'workout_date']
        )
        await db.execute(stmt)

        aggregate_result = await db.execute(
            select(WorkoutLog)
            .where(
                WorkoutLog.user_id == current_user.id,
                WorkoutLog.goal_id == request.goal_id,
                WorkoutLog.exercise_key == normalized_key,
                WorkoutLog.workout_date == request.workout_date
            )
            .with_for_update()
        )
        aggregate = aggregate_result.scalar_one()

        # Attempt to insert event using ON CONFLICT DO NOTHING
        event_stmt = insert(WorkoutLogEvent).values(
            session_id=request.session_id,
            workout_log_id=aggregate.id,
            reps_delta=request.reps_delta,
            duration_seconds_delta=request.duration_seconds_delta,
            calories_delta=request.calories_delta
        ).on_conflict_do_nothing(
            index_elements=['session_id']
        ).returning(WorkoutLogEvent.session_id)
        
        event_insert_result = await db.execute(event_stmt)
        inserted_session_id = event_insert_result.scalar_one_or_none()

        if not inserted_session_id:
            # Idempotent replay: load existing event and return its aggregate
            event_result = await db.execute(select(WorkoutLogEvent).where(WorkoutLogEvent.session_id == request.session_id))
            existing_event = event_result.scalar_one()
            
            agg_res = await db.execute(select(WorkoutLog).where(WorkoutLog.id == existing_event.workout_log_id))
            aggregate = agg_res.scalar_one_or_none()
            if not aggregate or aggregate.user_id != current_user.id:
                raise HTTPException(status_code=403, detail="Not authorized")
        else:
            # If aggregate existed before, reject changed recommendation values
            if (aggregate.recommended_sets != request.recommended_sets or
                aggregate.recommended_reps_per_set != request.recommended_reps_per_set or
                aggregate.recommended_duration_seconds != request.recommended_duration_seconds):
                raise HTTPException(status_code=409, detail="Conflicting recommendation values for existing aggregate")
            
            # Reject genuinely new sessions if already completed
            if aggregate.is_completed:
                raise HTTPException(status_code=409, detail="Exercise already completed for this date")

            # Update aggregate
            aggregate.reps += request.reps_delta
            aggregate.duration_seconds += request.duration_seconds_delta
            aggregate.duration_minutes = math.ceil(aggregate.duration_seconds / 60)
            aggregate.calories += request.calories_delta
            aggregate.updated_at = datetime.utcnow()

            # Recalculate completion
            rec_reps_total = aggregate.recommended_sets * aggregate.recommended_reps_per_set
            if rec_reps_total > 0 and aggregate.reps >= rec_reps_total:
                aggregate.is_completed = True
            elif aggregate.recommended_duration_seconds > 0 and aggregate.duration_seconds >= aggregate.recommended_duration_seconds:
                aggregate.is_completed = True

    await db.commit()
    await db.refresh(aggregate)

    # Calculate remaining values with minimum of zero
    rec_reps_total = aggregate.recommended_sets * aggregate.recommended_reps_per_set
    remaining_reps = max(0, rec_reps_total - aggregate.reps)
    remaining_duration = max(0, aggregate.recommended_duration_seconds - aggregate.duration_seconds)

    return WorkoutProgressResponse(
        id=aggregate.id,
        goal_id=aggregate.goal_id,
        exercise_name=aggregate.exercise_name,
        workout_date=aggregate.workout_date,
        reps=aggregate.reps,
        duration_seconds=aggregate.duration_seconds,
        duration_minutes=aggregate.duration_minutes,
        calories=aggregate.calories,
        recommended_sets=aggregate.recommended_sets,
        recommended_reps_per_set=aggregate.recommended_reps_per_set,
        recommended_reps_total=rec_reps_total,
        recommended_duration_seconds=aggregate.recommended_duration_seconds,
        remaining_reps=remaining_reps,
        remaining_duration_seconds=remaining_duration,
        is_completed=aggregate.is_completed,
        created_at=aggregate.created_at,
        updated_at=aggregate.updated_at
    )


@router.get("/goals/{goal_id}/workout-progress", response_model=list[WorkoutProgressResponse])
async def get_workout_progress(
    goal_id: int,
    workout_date: date | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    goal_result = await db.execute(select(UserGoal).where(UserGoal.id == goal_id, UserGoal.user_id == current_user.id))
    if not goal_result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not authorized to access this goal")

    query = select(WorkoutLog).where(
        WorkoutLog.user_id == current_user.id,
        WorkoutLog.goal_id == goal_id
    )
    if workout_date:
        query = query.where(WorkoutLog.workout_date == workout_date)
    
    query = query.order_by(WorkoutLog.created_at.asc())
    result = await db.execute(query)
    aggregates = result.scalars().all()
    
    response_list = []
    for agg in aggregates:
        rec_reps_total = agg.recommended_sets * agg.recommended_reps_per_set
        remaining_reps = max(0, rec_reps_total - agg.reps)
        remaining_duration = max(0, agg.recommended_duration_seconds - agg.duration_seconds)
        response_list.append(WorkoutProgressResponse(
            id=agg.id,
            goal_id=agg.goal_id,
            exercise_name=agg.exercise_name,
            workout_date=agg.workout_date,
            reps=agg.reps,
            duration_seconds=agg.duration_seconds,
            duration_minutes=agg.duration_minutes,
            calories=agg.calories,
            recommended_sets=agg.recommended_sets,
            recommended_reps_per_set=agg.recommended_reps_per_set,
            recommended_reps_total=rec_reps_total,
            recommended_duration_seconds=agg.recommended_duration_seconds,
            remaining_reps=remaining_reps,
            remaining_duration_seconds=remaining_duration,
            is_completed=agg.is_completed,
            created_at=agg.created_at,
            updated_at=agg.updated_at
        ))
    return response_list


import json

async def generate_workout_and_nutrition_plans(fitness_goal: str, activity_level: str, db: AsyncSession, available_days: list[str] | None = None):
    from api.plan_config import (
        build_nutrition_plan,
        load_workout_plan_rules,
        resolve_goal_category,
    )

    category = resolve_goal_category(fitness_goal)
    rules_config = load_workout_plan_rules()

    day_map = {
        "Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday",
        "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday",
        "Monday": "Monday", "Tuesday": "Tuesday", "Wednesday": "Wednesday",
        "Thursday": "Thursday", "Friday": "Friday", "Saturday": "Saturday", "Sunday": "Sunday",
    }

    days = []
    if available_days:
        for d in available_days:
            if d in day_map:
                days.append(day_map[d])

    if not days:
        days = rules_config["default_days"][category]

    from api.models import Exercise

    result = await db.execute(select(Exercise))
    all_exercises = result.scalars().all()

    rule = rules_config["rules"][category]
    if "equipment_filter" in rule:
        pool = [
            e for e in all_exercises
            if e.equipment_required in rule["equipment_filter"]
        ] or all_exercises
    elif "equipment_exclude" in rule:
        pool = [
            e for e in all_exercises
            if e.equipment_required not in rule["equipment_exclude"]
        ] or all_exercises
    else:
        pool = all_exercises

    exercises_per_day = rules_config.get("exercises_per_day", 4)
    workout_plan = []
    for day in days:
        daily_pool = random.sample(pool, min(exercises_per_day, len(pool))) if pool else []
        exercises = []
        for e in daily_pool:
            exercises.append({
                "name": e.title,
                "sets": rule["sets"],
                "reps_or_duration": rule["reps_or_duration"],
                "type": e.exercise_type,
                "image_url": e.image_url or "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?q=80&w=400&auto=format&fit=crop",
                "video_instruction": e.video_url or "https://example.com/default_video.mp4",
            })

        workout_plan.append({
            "day": day,
            "workout_name": rule["workout_name"],
            "duration_minutes": rule["duration_minutes"],
            "exercises": exercises,
        })

    nutrition_plan = build_nutrition_plan(fitness_goal, activity_level)
    return workout_plan, nutrition_plan


async def calculate_weekly_progress(user_id: int, goal_id: int, db: AsyncSession) -> tuple[int, int, int]:
    today = datetime.utcnow().date()
    start_of_week = datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time())
    end_of_week = start_of_week + timedelta(days=7)

    logs_result = await db.execute(
        select(WorkoutLog).where(
            WorkoutLog.user_id == user_id,
            WorkoutLog.goal_id == goal_id,
            WorkoutLog.workout_date >= start_of_week.date(),
            WorkoutLog.workout_date < end_of_week.date()
        )
    )
    logs = logs_result.scalars().all()

    actual_workouts = sum(1 for log in logs if log.is_completed)
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
        from api.plan_config import build_nutrition_plan
        w_plan = []
        n_plan = build_nutrition_plan(
            model.fitness_goal or "General Health",
            model.activity_level or "Active",
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
    workout_plan, nutrition_plan = await generate_workout_and_nutrition_plans(
        request.fitness_goal, request.activity_level, db, request.days
    )

    w_str = json.dumps(workout_plan)
    days_str = json.dumps(request.days) if request.days else None

    from api.plan_config import load_goal_options
    targets = load_goal_options()["default_targets"]

    user_goal = UserGoal(
        user_id=current_user.id,
        target_workouts=targets["target_workouts"],
        target_reps=targets["target_reps"],
        target_calories=targets["target_calories"],
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
    
    workouts_current, reps_current, calories_current = await calculate_weekly_progress(current_user.id, user_goal.id, db)
    return to_goal_response(user_goal, workouts_current, reps_current, calories_current)


@router.post("/meals", response_model=MealPlanResponse)
async def create_user_meal(
    request: MealCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from api.plan_config import build_nutrition_plan, load_goal_options

    nutrition_plan = build_nutrition_plan(request.fitness_goal, request.activity_level)
    n_str = json.dumps(nutrition_plan)
    targets = load_goal_options()["default_targets"]

    user_goal = UserGoal(
        user_id=current_user.id,
        target_workouts=targets["target_workouts"],
        target_reps=targets["target_reps"],
        target_calories=targets["target_calories"],
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
        is_active=user_goal.is_active,
        created_at=user_goal.created_at
    )



@router.get("/goals/options")
async def get_goals_options(
    current_user: User = Depends(get_current_user)
):
    from api.plan_config import load_goal_options
    options = load_goal_options()
    return {
        "fitness_goals": [g["name"] for g in options["fitness_goals"]],
        "activity_levels": [
            {"value": a["value"], "label": a["label"]}
            for a in options["activity_levels"]
        ],
        "timelines": [t["name"] for t in options["timelines"]],
        "alarm_sounds": options["alarm_sounds"],
    }


@router.get("/goals/activity-levels")
async def get_activity_levels(
    current_user: User = Depends(get_current_user)
):
    from api.plan_config import load_goal_options
    options = load_goal_options()
    return {
        "values": [
            {"id": a["id"], "name": a["label"]}
            for a in options["activity_levels"]
        ]
    }


@router.get("/goals/fitness-goals")
async def get_fitness_goals(
    current_user: User = Depends(get_current_user)
):
    from api.plan_config import load_goal_options
    return {"values": load_goal_options()["fitness_goals"]}


@router.get("/goals/timelines")
async def get_timelines(
    current_user: User = Depends(get_current_user)
):
    from api.plan_config import load_goal_options
    return {"values": load_goal_options()["timelines"]}


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
    
    responses = []
    for g in user_goals:
        workouts_current, reps_current, calories_current = await calculate_weekly_progress(current_user.id, g.id, db)
        responses.append(to_goal_response(g, workouts_current, reps_current, calories_current))
    return responses


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
    
    workouts_current, reps_current, calories_current = await calculate_weekly_progress(current_user.id, user_goal.id, db)
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
        
    if not user_goal.nutrition_plan:
        from api.plan_config import build_nutrition_plan
        nutrition_plan = build_nutrition_plan(
            user_goal.fitness_goal, user_goal.activity_level
        )
        user_goal.nutrition_plan = json.dumps(nutrition_plan)
        
    user_goal.has_meal_plan = True
    await db.commit()
    await db.refresh(user_goal)
    
    workouts_current, reps_current, calories_current = await calculate_weekly_progress(current_user.id, user_goal.id, db)
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
                is_active=g.is_active,
                created_at=g.created_at
            ).model_dump()
        )
    return meal_plans


from api.plan_config import (
    get_alternative_meal_options,
    perform_swap_logic,
)

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

    mt = request.meal_type.capitalize().strip()
    if mt not in ["Breakfast", "Lunch", "Dinner"]:
        mt = "Breakfast"

    options = get_alternative_meal_options(fitness_goal, mt)

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
        "protein": 0,
        "carbs": 0,
        "fats": 0,
        "fiber": 0
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
    request: Request,
    email: str | None = Form(None),
    gender: str | None = Form(None),
    date_of_birth: str | None = Form(None),
    allow_notifications: bool | None = Form(None),
    app_blocker: bool | None = Form(None),
    profile_image: UploadFile | None = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from api.schemas import UserResponse
    import uuid
    import shutil
    import os
    
    update_data = {}
    if email is not None: update_data["email"] = email
    if gender is not None: update_data["gender"] = gender
    if date_of_birth is not None:
        try:
            update_data["date_of_birth"] = datetime.strptime(date_of_birth, "%Y-%m-%d").date()
        except ValueError:
            pass
    if allow_notifications is not None: update_data["allow_notifications"] = allow_notifications
    if app_blocker is not None: update_data["app_blocker"] = app_blocker
    
    if profile_image:
        os.makedirs("uploads", exist_ok=True)
        filename_val = profile_image.filename or ""
        ext = os.path.splitext(filename_val)[1]
        if not ext:
            ext = ".jpg"
        filename = f"{uuid.uuid4()}{ext}"
        filepath = os.path.join("uploads", filename)
        
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(profile_image.file, buffer)
            
        base_url = str(request.base_url)
        if base_url.endswith("/"):
            base_url = base_url[:-1]
        public_url = f"{base_url}/uploads/{filename}"
        update_data["profile_image"] = public_url

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


@router.post("/contact")
async def contact_us(
    request: Request,
    email: str = Form(...),
    description: str = Form(...),
    file: UploadFile | None = File(None),
    current_user: User = Depends(get_current_user)
):
    import os
    import uuid
    import shutil
    
    public_url = None
    if file:
        os.makedirs("uploads", exist_ok=True)
        filename_val = file.filename or ""
        ext = os.path.splitext(filename_val)[1]
        if not ext:
            ext = ".jpg"
        filename = f"{uuid.uuid4()}{ext}"
        filepath = os.path.join("uploads", filename)
        
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        base_url = str(request.base_url)
        if base_url.endswith("/"):
            base_url = base_url[:-1]
        public_url = f"{base_url}/uploads/{filename}"

    # Log the message and the uploaded file URL
    logger.info(f"Contact Us message from {email}: {description} | Attached File: {public_url}")
    return {"message": "Thank you for contacting us. Your request has been received.", "file_url": public_url}

@router.get('/equipments', response_model=list[dict])
async def get_equipments(current_user: User = Depends(get_current_user)):
    from api.schemas import EquipmentResponse
    equipments = [
        EquipmentResponse(
            id=1,
            title='Cable Chest Fly Machine',
            primary_muscle='Chest',
            exercise_type='Isolation',
            best_for='Upper Body',
            video_instruction='https://example.com/cable_chest_fly.mp4',
            muscles_worked_pct={'Chest (Pectoralis Major)': 100, 'Front Deltoids': 60, 'Biceps (Stabilization)': 40, 'Core': 30},
            suggested_workouts=['Cable Chest Fly', 'High to low Cable Fly'],
            instructions=[
                'Adjust seat height so handles align mid chest.',
                'Grip handles with a slight bend in your elbows.',
                'Squeeze your chest as you bring handles together.',
                'Slowly return to the starting position with control.'
            ],
            safety_tips=[
                'Do not lock elbows during movement.',
                'Use a controlled tempo to avoid shoulder strain.',
                'Start with lighter weight to master form.'
            ]
        ),
        EquipmentResponse(
            id=2,
            title='Dumbbells',
            primary_muscle='Multiple',
            exercise_type='Free Weight',
            best_for='Full Body',
            video_instruction='https://example.com/dumbbells.mp4',
            muscles_worked_pct={'Primary Target': 100, 'Stabilizers': 50},
            suggested_workouts=['Dumbbell Bench Press', 'Dumbbell Bicep Curl'],
            instructions=[
                'Select appropriate weight.',
                'Maintain proper posture and neutral spine.',
                'Control the weight through the full range of motion.'
            ],
            safety_tips=[
                'Do not drop the weights from a height.',
                'Ensure a firm grip before lifting.'
            ]
        ),
        EquipmentResponse(
            id=3,
            title='Barbell',
            primary_muscle='Multiple',
            exercise_type='Compound',
            best_for='Full Body Strength',
            video_instruction='https://example.com/barbell.mp4',
            muscles_worked_pct={'Primary Target': 100, 'Core': 60},
            suggested_workouts=['Barbell Squats', 'Barbell Deadlift'],
            instructions=[
                'Position hands evenly on the knurling.',
                'Engage core before initiating lift.',
                'Keep the bar path strictly vertical.'
            ],
            safety_tips=[
                'Use collars to secure plates.',
                'Use a spotter for heavy lifts.'
            ]
        )
    ]
    return [eq.model_dump() for eq in equipments]

