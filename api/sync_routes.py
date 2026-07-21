"""Public sync catalog — one place for mobile to check what changed."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from api.database import get_db
from api.models import Exercise
from api.plan_config import (
    CONFIG_FILES,
    MODEL_SLOTS,
    ROOT_DIR,
    get_config_mtime,
)

router = APIRouter(prefix="/sync", tags=["sync"])

# Admin-editable resources mapped to the public APIs that consume them.
SYNC_RESOURCES: list[dict] = [
    {
        "key": "exercises",
        "label": "Exercises",
        "apis": ["GET /exercises"],
        "source": "database",
    },
    {
        "key": "goal-options",
        "label": "Goal options",
        "apis": [
            "GET /goals/options",
            "GET /goals/fitness-goals",
            "GET /goals/activity-levels",
            "GET /goals/timelines",
        ],
        "source": "config",
        "config_key": "goal-options",
    },
    {
        "key": "meal-plan-templates",
        "label": "Meal plan templates",
        "apis": ["POST /goals", "POST /meals", "POST /goals/{goal_id}/meal-plan"],
        "source": "config",
        "config_key": "meal-plan-templates",
    },
    {
        "key": "alternative-meals",
        "label": "Alternative meals",
        "apis": ["POST /meal-plans/swap-options", "POST /meal-plans/swap-meal"],
        "source": "config",
        "config_key": "alternative-meals",
    },
    {
        "key": "workout-plan-rules",
        "label": "Workout plan rules",
        "apis": ["POST /goals"],
        "source": "config",
        "config_key": "workout-plan-rules",
    },
    {
        "key": "exercise-rep-model",
        "label": "Exercise rep model (TCN)",
        "apis": ["POST /count-reps", "POST /count-reps-mediapipe"],
        "source": "model",
        "model_slot": "exercise-rep",
    },
    {
        "key": "equipment-model",
        "label": "Equipment detection model",
        "apis": ["POST /detect-equipment", "POST /detect-equipment-video"],
        "source": "model",
        "model_slot": "equipment",
    },
]


def _model_mtime(slot: str) -> datetime | None:
    meta = MODEL_SLOTS.get(slot)
    if not meta:
        return None
    path = ROOT_DIR / meta["path"]
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


async def _exercises_mtime(db: AsyncSession) -> datetime | None:
    result = await db.execute(select(func.max(Exercise.updated_at)))
    return result.scalar()


async def build_sync_catalog(db: AsyncSession) -> dict:
    exercises_ts = await _exercises_mtime(db)
    resources: list[dict] = []
    all_times: list[datetime] = []

    for spec in SYNC_RESOURCES:
        ts: datetime | None = None
        source = spec["source"]

        if source == "database":
            ts = exercises_ts
        elif source == "config":
            ts = get_config_mtime(spec["config_key"])
        elif source == "model":
            ts = _model_mtime(spec["model_slot"])

        if ts is not None:
            all_times.append(ts)

        entry = {
            "key": spec["key"],
            "label": spec["label"],
            "apis": spec["apis"],
            "source": source,
            "lastModifiedAt": _iso(ts),
        }
        if source == "config":
            entry["filename"] = CONFIG_FILES.get(spec["config_key"])
        elif source == "model":
            entry["filename"] = MODEL_SLOTS.get(spec["model_slot"], {}).get("filename")

        resources.append(entry)

    latest = max(all_times) if all_times else None
    latest_iso = _iso(latest)

    return {
        "lastModifiedAt": latest_iso,
        "last_modified": latest_iso,  # backward-compatible alias
        "resources": resources,
    }


@router.get("/catalog")
async def get_sync_catalog(db: AsyncSession = Depends(get_db)):
    """Return every admin-editable resource with its public API paths and lastModifiedAt."""
    return await build_sync_catalog(db)
