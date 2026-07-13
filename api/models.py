from datetime import datetime, date
from sqlalchemy import String, DateTime, Date, ForeignKey, Integer, Float, Boolean, Text, UniqueConstraint
import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from api.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    profile_image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(50), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    allow_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    app_blocker: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class PWDResetOTP(Base):
    __tablename__ = "pwd_reset_otps"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    otp_code: Mapped[str] = mapped_column(String(6), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class UserGoal(Base):
    __tablename__ = "user_goals"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    target_workouts: Mapped[int] = mapped_column(default=15, nullable=False)
    target_reps: Mapped[int] = mapped_column(default=1800, nullable=False)
    target_calories: Mapped[int] = mapped_column(default=8000, nullable=False)
    fitness_goal: Mapped[str | None] = mapped_column(String(100), nullable=True)
    activity_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    workout_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    nutrition_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(50), nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_unit: Mapped[str | None] = mapped_column(String(10), default="kg", nullable=True)
    timeline: Mapped[str | None] = mapped_column(String(50), nullable=True)
    available_days: Mapped[str | None] = mapped_column(String(200), nullable=True)
    alarm_sound: Mapped[str | None] = mapped_column(String(100), nullable=True)
    available_time: Mapped[str | None] = mapped_column(String(20), nullable=True)
    food_allergies: Mapped[str | None] = mapped_column(String(500), nullable=True)
    health_conditions: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_meal_plan: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    @property
    def lastModifiedAt(self) -> datetime:
        return self.updated_at



class WorkoutLog(Base):
    __tablename__ = "workout_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "goal_id", "exercise_key", "workout_date", name="ix_workout_logs_aggregate"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    goal_id: Mapped[int | None] = mapped_column(ForeignKey("user_goals.id", ondelete="SET NULL"), nullable=True)
    exercise_name: Mapped[str] = mapped_column(String(100), nullable=False)
    exercise_key: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    workout_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    
    reps: Mapped[int] = mapped_column(default=0, nullable=False)
    calories: Mapped[int] = mapped_column(default=0, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(default=0, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(default=0, nullable=False)
    
    recommended_sets: Mapped[int] = mapped_column(default=0, nullable=False)
    recommended_reps_per_set: Mapped[int] = mapped_column(default=0, nullable=False)
    recommended_duration_seconds: Mapped[int] = mapped_column(default=0, nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    @property
    def lastModifiedAt(self) -> datetime:
        return self.updated_at

class WorkoutLogEvent(Base):
    __tablename__ = "workout_log_events"

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    workout_log_id: Mapped[int] = mapped_column(ForeignKey("workout_logs.id", ondelete="CASCADE"), nullable=False)
    reps_delta: Mapped[int] = mapped_column(default=0, nullable=False)
    duration_seconds_delta: Mapped[int] = mapped_column(default=0, nullable=False)
    calories_delta: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    primary_muscle: Mapped[str] = mapped_column(String(50), nullable=False)
    exercise_type: Mapped[str] = mapped_column(String(50), nullable=False)
    location_type: Mapped[str | None] = mapped_column(String(50), default="both", nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(200), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(200), nullable=True)
    muscles_worked_pct: Mapped[str | None] = mapped_column(String(500), nullable=True)
    suggested_workouts: Mapped[str | None] = mapped_column(String(500), nullable=True)
    instructions: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    safety_tips: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    @property
    def lastModifiedAt(self) -> datetime:
        return self.updated_at



