from datetime import datetime, date
from pydantic import BaseModel, EmailStr, Field

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)
    gender: str | None = None
    date_of_birth: date | None = None

class UserLogin(BaseModel):
    username_or_email: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    gender: str | None = None
    date_of_birth: date | None = None
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: str | None = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6)


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)


class GoogleLoginRequest(BaseModel):
    id_token: str


class WorkoutLogCreate(BaseModel):
    exercise_name: str
    reps: int
    calories: int
    duration_minutes: int
    created_at: datetime | None = None



class GoalMetric(BaseModel):
    current: int
    target: int
    unit: str | None = None


class DashboardGoals(BaseModel):
    workouts: GoalMetric
    reps: GoalMetric
    calories: GoalMetric


class WeeklyProgressDay(BaseModel):
    day: str
    percentage: float


class NextWorkoutInfo(BaseModel):
    title: str
    time: str
    duration: str
    location: str
    type: str
    difficulty: str


class DashboardResponse(BaseModel):
    username: str
    email: str
    completion_percentage: float
    goals: DashboardGoals
    weekly_progress: list[WeeklyProgressDay]
    next_workout: NextWorkoutInfo



