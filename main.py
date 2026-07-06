from __future__ import annotations

import logging
import shutil

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from api.routes import router as count_reps_router
from api.auth_routes import router as auth_router
from api.exercise_routes import router as exercise_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

app = FastAPI(title="FitVision Pose & Rep Counting", version="3.0.0")


@app.on_event("startup")
async def create_db_tables():
    from api.database import Base, engine
    from api.models import User, PWDResetOTP, UserGoal, WorkoutLog, Exercise
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS gender VARCHAR(50)"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS date_of_birth DATE"))
        try:
            await conn.execute(text("ALTER TABLE user_goals ALTER COLUMN workout_plan TYPE VARCHAR(4000)"))
        except Exception:
            pass
        try:
            await conn.execute(text("ALTER TABLE user_goals ALTER COLUMN nutrition_plan TYPE VARCHAR(4000)"))
        except Exception:
            pass

        for col_name, col_type in [
            ("fitness_goal", "VARCHAR(100)"),
            ("activity_level", "VARCHAR(50)"),
            ("workout_plan", "VARCHAR(4000)"),
            ("nutrition_plan", "VARCHAR(4000)"),
            ("age", "INTEGER"),
            ("gender", "VARCHAR(50)"),
            ("weight", "DOUBLE PRECISION"),
            ("weight_unit", "VARCHAR(10)"),
            ("timeline", "VARCHAR(50)"),
            ("available_days", "VARCHAR(200)"),
            ("alarm_sound", "VARCHAR(100)"),
            ("available_time", "VARCHAR(20)"),
            ("is_active", "BOOLEAN DEFAULT FALSE"),
            ("has_meal_plan", "BOOLEAN DEFAULT FALSE"),
            ("created_at", "TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP")
        ]:
            try:
                await conn.execute(text(f"ALTER TABLE user_goals ADD COLUMN {col_name} {col_type}"))
            except Exception:
                pass
        
        try:
            await conn.execute(text("DROP INDEX IF EXISTS ix_user_goals_user_id CASCADE"))
        except Exception:
            pass
        try:
            await conn.execute(text("ALTER TABLE user_goals DROP CONSTRAINT IF EXISTS ix_user_goals_user_id"))
        except Exception:
            pass
        try:
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_goals_user_id ON user_goals (user_id)"))
        except Exception:
            pass


@app.on_event("startup")
def _log_startup():
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        logging.getLogger(__name__).info("ffmpeg found at %s", ffmpeg)
    else:
        logging.getLogger(__name__).warning(
            "ffmpeg not found — annotated videos will fail to transcode for browsers. "
            "Install with: brew install ffmpeg"
        )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(count_reps_router)
app.include_router(auth_router)
app.include_router(exercise_router)


@app.get("/tester", response_class=HTMLResponse)
async def read_tester():
    with open("app_test_client.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/admin", response_class=HTMLResponse)
async def read_admin():
    with open("admin_exercises.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000)
