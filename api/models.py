from datetime import datetime, date
from sqlalchemy import String, DateTime, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from api.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(50), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
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
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    target_workouts: Mapped[int] = mapped_column(default=15, nullable=False)
    target_reps: Mapped[int] = mapped_column(default=1800, nullable=False)
    target_calories: Mapped[int] = mapped_column(default=8000, nullable=False)
    fitness_goal: Mapped[str | None] = mapped_column(String(100), nullable=True)
    activity_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    workout_plan: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    nutrition_plan: Mapped[str | None] = mapped_column(String(2000), nullable=True)



class WorkoutLog(Base):
    __tablename__ = "workout_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    exercise_name: Mapped[str] = mapped_column(String(100), nullable=False)
    reps: Mapped[int] = mapped_column(default=0, nullable=False)
    calories: Mapped[int] = mapped_column(default=0, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    primary_muscle: Mapped[str] = mapped_column(String(100), nullable=False)
    exercise_type: Mapped[str] = mapped_column(String(50), nullable=False)
    video_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    muscles_worked_pct: Mapped[str | None] = mapped_column(String(500), nullable=True)
    suggested_workouts: Mapped[str | None] = mapped_column(String(500), nullable=True)
    instructions: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    safety_tips: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)



