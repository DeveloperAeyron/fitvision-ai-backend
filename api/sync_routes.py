"""Public sync catalog — one place for mobile to check what changed."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app.config import settings
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


def _model_path(slot: str):
    meta = MODEL_SLOTS.get(slot)
    if not meta:
        return None
    path = ROOT_DIR / meta["path"]
    return path if path.exists() else None


def _model_mtime(slot: str) -> datetime | None:
    path = _model_path(slot)
    if path is None:
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _to_utc_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    aware = _to_utc_aware(dt)
    return aware.isoformat() if aware else None


async def _exercises_mtime(db: AsyncSession) -> datetime | None:
    result = await db.execute(select(func.max(Exercise.updated_at)))
    return result.scalar()


def resolve_public_base_url(request: Request | None = None) -> str:
    configured = settings.public_base_url.strip().rstrip("/")
    if configured:
        return configured
    if request is not None:
        return str(request.base_url).rstrip("/")
    return "https://fitvision.medaide.org"


def _absolute_download_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


async def build_sync_catalog(db: AsyncSession, *, base_url: str | None = None) -> dict:
    base = (base_url or resolve_public_base_url()).rstrip("/")
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
            all_times.append(_to_utc_aware(ts))

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
            slot = spec["model_slot"]
            meta = MODEL_SLOTS.get(slot, {})
            entry["filename"] = meta.get("filename")
            entry["downloadUrl"] = _absolute_download_url(
                base, f"sync/models/{slot}/download"
            )
            model_path = _model_path(slot)
            if model_path is not None:
                entry["sizeBytes"] = model_path.stat().st_size

        resources.append(entry)

    latest = max(all_times) if all_times else None
    latest_iso = _iso(latest)

    return {
        "lastModifiedAt": latest_iso,
        "last_modified": latest_iso,  # backward-compatible alias
        "resources": resources,
    }


@router.get("/catalog")
async def get_sync_catalog(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Return every admin-editable resource with its public API paths and lastModifiedAt."""
    return await build_sync_catalog(db, base_url=resolve_public_base_url(request))


@router.get("/models/{slot}/download")
async def download_sync_model(slot: str):
    """Public model download for mobile offline sync."""
    if slot not in MODEL_SLOTS:
        raise HTTPException(status_code=404, detail="Unknown model slot")

    meta = MODEL_SLOTS[slot]
    path = _model_path(slot)
    if path is None:
        raise HTTPException(status_code=404, detail="Model file not found")

    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=meta["filename"],
    )
