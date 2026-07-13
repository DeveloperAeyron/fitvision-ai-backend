"""
Migration script for workout logs.
IMPORTANT: Run this migration script BEFORE deploying the new application code.
SQLAlchemy's create_all() does not alter existing tables to add new columns or constraints.
"""

import asyncio
import os
import sys

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:password@localhost:5432/fitvision"
)
engine = create_async_engine(DATABASE_URL, echo=True)

async def run_migration():
    print("Starting migration...")
    async with engine.begin() as conn:
        print("1. Adding new nullable columns to workout_logs...")
        for query in [
            "ALTER TABLE workout_logs ADD COLUMN IF NOT EXISTS exercise_key VARCHAR(100);",
            "ALTER TABLE workout_logs ADD COLUMN IF NOT EXISTS workout_date DATE;",
            "ALTER TABLE workout_logs ADD COLUMN IF NOT EXISTS duration_seconds INTEGER;",
            "ALTER TABLE workout_logs ADD COLUMN IF NOT EXISTS recommended_sets INTEGER;",
            "ALTER TABLE workout_logs ADD COLUMN IF NOT EXISTS recommended_reps_per_set INTEGER;",
            "ALTER TABLE workout_logs ADD COLUMN IF NOT EXISTS recommended_duration_seconds INTEGER;",
            "ALTER TABLE workout_logs ADD COLUMN IF NOT EXISTS is_completed BOOLEAN;"
        ]:
            await conn.execute(text(query))

        print("2. Backfilling existing data...")
        await conn.execute(text("""
            UPDATE workout_logs 
            SET 
                exercise_key = COALESCE(NULLIF(exercise_key, ''), BTRIM(REGEXP_REPLACE(LOWER(exercise_name), '\\s+', ' ', 'g'))),
                workout_date = COALESCE(workout_date, DATE(created_at)),
                duration_seconds = COALESCE(duration_seconds, duration_minutes * 60),
                recommended_sets = COALESCE(recommended_sets, 0),
                recommended_reps_per_set = COALESCE(recommended_reps_per_set, 0),
                recommended_duration_seconds = COALESCE(recommended_duration_seconds, 0),
                is_completed = COALESCE(is_completed, true)
            WHERE exercise_key IS NULL 
               OR exercise_key = '' 
               OR workout_date IS NULL
               OR duration_seconds IS NULL
               OR recommended_sets IS NULL
               OR recommended_reps_per_set IS NULL
               OR recommended_duration_seconds IS NULL
               OR is_completed IS NULL;
        """))

        print("3. Merging duplicates...")
        # To merge, we will sum reps, calories, and duration_seconds (and duration_minutes),
        # keep the earliest created_at and latest updated_at for each group of (user_id, goal_id, exercise_key, workout_date).
        merge_query = """
        WITH duplicates AS (
            SELECT 
                MIN(id) as keep_id,
                user_id, 
                goal_id, 
                exercise_key, 
                workout_date,
                SUM(reps) as sum_reps,
                SUM(calories) as sum_calories,
                SUM(duration_minutes) as sum_duration_minutes,
                SUM(duration_seconds) as sum_duration_seconds,
                MIN(created_at) as min_created_at,
                MAX(updated_at) as max_updated_at
            FROM workout_logs
            GROUP BY user_id, goal_id, exercise_key, workout_date
            HAVING COUNT(*) > 1
        )
        UPDATE workout_logs w
        SET 
            reps = d.sum_reps,
            calories = d.sum_calories,
            duration_minutes = d.sum_duration_minutes,
            duration_seconds = d.sum_duration_seconds,
            created_at = d.min_created_at,
            updated_at = d.max_updated_at
        FROM duplicates d
        WHERE w.id = d.keep_id;
        """
        await conn.execute(text(merge_query))

        print("4. Deleting merged duplicate rows...")
        delete_query = """
        WITH duplicates AS (
            SELECT MIN(id) as keep_id, user_id, goal_id, exercise_key, workout_date
            FROM workout_logs
            GROUP BY user_id, goal_id, exercise_key, workout_date
            HAVING COUNT(*) > 1
        )
        DELETE FROM workout_logs w
        USING duplicates d
        WHERE w.user_id = d.user_id 
          AND w.exercise_key = d.exercise_key 
          AND w.workout_date = d.workout_date 
          AND (w.goal_id = d.goal_id OR (w.goal_id IS NULL AND d.goal_id IS NULL))
          AND w.id != d.keep_id;
        """
        await conn.execute(text(delete_query))

        print("5. Making required columns non-null...")
        for col in ["exercise_key", "workout_date", "duration_seconds", "recommended_sets", "recommended_reps_per_set", "recommended_duration_seconds", "is_completed"]:
            await conn.execute(text(f"ALTER TABLE workout_logs ALTER COLUMN {col} SET NOT NULL;"))
            
        print("6. Adding unique constraint if not exists...")
        await conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 
                    FROM pg_constraint 
                    WHERE conname = 'ix_workout_logs_aggregate'
                ) THEN
                    ALTER TABLE workout_logs 
                    ADD CONSTRAINT ix_workout_logs_aggregate 
                    UNIQUE (user_id, goal_id, exercise_key, workout_date);
                END IF;
            END
            $$;
        """))

        print("7. Creating workout_log_events table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS workout_log_events (
                session_id UUID PRIMARY KEY,
                workout_log_id INTEGER NOT NULL REFERENCES workout_logs(id) ON DELETE CASCADE,
                reps_delta INTEGER NOT NULL DEFAULT 0,
                duration_seconds_delta INTEGER NOT NULL DEFAULT 0,
                calories_delta INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
            );
        """))

    print("Migration complete!")

if __name__ == "__main__":
    asyncio.run(run_migration())
