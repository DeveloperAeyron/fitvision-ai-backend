from datetime import datetime, date
from pydantic import BaseModel, EmailStr, Field

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)
    gender: str | None = None
    date_of_birth: date | None = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str | None = None
    gender: str | None = None
    date_of_birth: date | None = None
    allow_notifications: bool = True
    app_blocker: bool = False
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class UserProfileUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    gender: str | None = None
    date_of_birth: date | None = None
    allow_notifications: bool | None = None
    app_blocker: bool | None = None

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
    goal_id: int | None = None
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
    lastModifiedAt: datetime | None = None


class ExerciseBase(BaseModel):
    title: str
    primary_muscle: str
    exercise_type: str
    location_type: str | None = "both"
    video_url: str | None = None
    muscles_worked_pct: dict[str, float] | None = None
    suggested_workouts: list[str] | None = None
    instructions: list[str] | None = None
    safety_tips: list[str] | None = None


class ExerciseCreate(ExerciseBase):
    pass


class ExerciseUpdate(ExerciseBase):
    pass


class ExerciseResponse(ExerciseBase):
    id: int
    created_at: datetime
    lastModifiedAt: datetime | None = None

    class Config:
        from_attributes = True


class GoalCreateRequest(BaseModel):
    fitness_goal: str
    activity_level: str
    age: int | None = None
    gender: str | None = None
    weight: float | None = None
    weight_unit: str | None = "kg"
    timeline: str | None = None
    days: list[str] | None = None
    alarm_sound: str | None = None
    time_of_day: str | None = None


class MealCreateRequest(BaseModel):
    fitness_goal: str
    activity_level: str
    age: int | None = None
    gender: str | None = None
    weight: float | None = None
    weight_unit: str | None = "kg"
    food_allergies: str | None = None
    health_conditions: str | None = None
    notes: str | None = None


class GoalMetricProgress(BaseModel):
    current: int
    target: int
    unit: str


class GoalProgress(BaseModel):
    workouts: GoalMetricProgress
    reps: GoalMetricProgress
    calories: GoalMetricProgress
    completion_percentage: float


class GoalResponse(BaseModel):
    id: int
    target_workouts: int
    target_reps: int
    target_calories: int
    fitness_goal: str
    activity_level: str
    workout_plan: list[dict]
    nutrition_plan: dict
    progress: GoalProgress
    age: int | None = None
    gender: str | None = None
    weight: float | None = None
    weight_unit: str | None = None
    timeline: str | None = None
    days: list[str] | None = None
    alarm_sound: str | None = None
    time_of_day: str | None = None
    is_active: bool
    has_meal_plan: bool
    image_url: str | None = "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?q=80&w=400&auto=format&fit=crop"
    created_at: datetime
    lastModifiedAt: datetime | None = None

    class Config:
        from_attributes = True


class MealPlanResponse(BaseModel):
    goal_id: int
    fitness_goal: str | None = None
    nutrition_plan: dict
    image_url: str | None = "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?q=80&w=400&auto=format&fit=crop"
    created_at: datetime
    lastModifiedAt: datetime | None = None

    class Config:
        from_attributes = True


class SwapMealRequest(BaseModel):
    goal_id: int | None = None
    nutrition_plan: dict | None = None
    day: str
    meal_type: str
    swap_to_name: str | None = None


class SwapOptionsRequest(BaseModel):
    goal_id: int | None = None
    nutrition_plan: dict | None = None
    day: str
    meal_type: str


class CompleteMealRequest(BaseModel):
    goal_id: int
    day: str
    meal_type: str
    completed: bool = True
