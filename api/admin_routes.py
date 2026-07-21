from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from api.database import get_db
from api.exercise_routes import to_exercise_response
from api.models import Exercise
from api.schemas import ExerciseCreate, ExerciseResponse, ExerciseUpdate

from api.plan_config import (
    CONFIG_FILES,
    MODEL_SLOTS,
    ROOT_DIR,
    build_nutrition_plan,
    clear_config_cache,
    get_config,
    list_config_keys,
    save_config,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def verify_admin_key(x_admin_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("ADMIN_API_KEY", "fitvision-admin-dev")
    if not x_admin_key or x_admin_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing admin API key")


class PreviewPlanRequest(BaseModel):
    fitness_goal: str = "Weight Loss"
    activity_level: str = "Active"


class ConfigUpdateRequest(BaseModel):
    data: dict[str, Any]


@router.get("/config")
async def list_configs(_: None = Depends(verify_admin_key)):
    return {"configs": list_config_keys()}


@router.get("/config/{config_key}")
async def read_config(config_key: str, _: None = Depends(verify_admin_key)):
    if config_key not in CONFIG_FILES:
        raise HTTPException(status_code=404, detail="Unknown config")
    return get_config(config_key)


@router.put("/config/{config_key}")
async def update_config(
    config_key: str,
    body: ConfigUpdateRequest,
    _: None = Depends(verify_admin_key),
):
    if config_key not in CONFIG_FILES:
        raise HTTPException(status_code=404, detail="Unknown config")
    if not isinstance(body.data, dict):
        raise HTTPException(status_code=400, detail="Config body must be a JSON object")
    save_config(config_key, body.data)
    return {"message": "Config saved", "key": config_key}


@router.post("/config/reload")
async def reload_configs(_: None = Depends(verify_admin_key)):
    clear_config_cache()
    return {"message": "Config cache cleared"}


@router.post("/config/preview")
async def preview_plan(
    request: PreviewPlanRequest,
    _: None = Depends(verify_admin_key),
):
    nutrition_plan = build_nutrition_plan(request.fitness_goal, request.activity_level)
    return {
        "fitness_goal": request.fitness_goal,
        "activity_level": request.activity_level,
        "nutrition_plan": nutrition_plan,
    }


@router.get("/models")
async def list_models(_: None = Depends(verify_admin_key)):
    items = []
    for slot, meta in MODEL_SLOTS.items():
        path = ROOT_DIR / meta["path"]
        if path.exists():
            stat = path.stat()
            items.append({
                "slot": slot,
                "label": meta["label"],
                "filename": meta["filename"],
                "size_bytes": stat.st_size,
                "updated_at": stat.st_mtime,
            })
        else:
            items.append({
                "slot": slot,
                "label": meta["label"],
                "filename": meta["filename"],
                "size_bytes": 0,
                "updated_at": None,
            })
    return {"models": items}


@router.post("/models/{slot}")
async def upload_model(
    slot: str,
    file: UploadFile = File(...),
    _: None = Depends(verify_admin_key),
):
    if slot not in MODEL_SLOTS:
        raise HTTPException(status_code=404, detail="Unknown model slot")

    meta = MODEL_SLOTS[slot]
    dest = ROOT_DIR / meta["path"]
    dest.parent.mkdir(parents=True, exist_ok=True)

    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        with open(tmp, "wb") as out:
            shutil.copyfileobj(file.file, out)
        tmp.replace(dest)
    except Exception as exc:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc

    stat = dest.stat()
    return {
        "message": "Model uploaded",
        "slot": slot,
        "filename": meta["filename"],
        "size_bytes": stat.st_size,
    }


@router.get("/models/{slot}/download")
async def download_model(slot: str, _: None = Depends(verify_admin_key)):
    if slot not in MODEL_SLOTS:
        raise HTTPException(status_code=404, detail="Unknown model slot")

    meta = MODEL_SLOTS[slot]
    path = ROOT_DIR / meta["path"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Model file not found")

    from fastapi.responses import FileResponse

    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=meta["filename"],
    )


def _serialize_exercise_fields(request: ExerciseCreate | ExerciseUpdate) -> dict[str, str | None]:
    import json

    return {
        "muscles_worked_pct": json.dumps(request.muscles_worked_pct) if request.muscles_worked_pct else None,
        "suggested_workouts": ",".join(request.suggested_workouts) if request.suggested_workouts else None,
        "instructions": "\n".join(request.instructions) if request.instructions else None,
        "safety_tips": "\n".join(request.safety_tips) if request.safety_tips else None,
    }


@router.get("/exercises", response_model=list[ExerciseResponse])
async def admin_list_exercises(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_key),
):
    result = await db.execute(select(Exercise).order_by(Exercise.title))
    return [to_exercise_response(e) for e in result.scalars().all()]


@router.post("/exercises", response_model=ExerciseResponse, status_code=status.HTTP_201_CREATED)
async def admin_create_exercise(
    request: ExerciseCreate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_key),
):
    existing = await db.execute(select(Exercise).where(Exercise.title == request.title))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="An exercise with this title already exists.")

    serialized = _serialize_exercise_fields(request)
    exercise = Exercise(
        title=request.title,
        primary_muscle=request.primary_muscle,
        exercise_type=request.exercise_type,
        difficulty_level=request.difficulty_level,
        equipment_required=request.equipment_required,
        location_type=request.location_type,
        video_url=request.video_url,
        image_url=request.image_url,
        **serialized,
    )
    db.add(exercise)
    await db.commit()
    await db.refresh(exercise)
    return to_exercise_response(exercise)


@router.put("/exercises/{exercise_id}", response_model=ExerciseResponse)
async def admin_update_exercise(
    exercise_id: int,
    request: ExerciseUpdate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_key),
):
    result = await db.execute(select(Exercise).where(Exercise.id == exercise_id))
    exercise = result.scalars().first()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    if exercise.title != request.title:
        title_check = await db.execute(select(Exercise).where(Exercise.title == request.title))
        if title_check.scalars().first():
            raise HTTPException(status_code=400, detail="Another exercise with this title already exists.")

    serialized = _serialize_exercise_fields(request)
    exercise.title = request.title
    exercise.primary_muscle = request.primary_muscle
    exercise.exercise_type = request.exercise_type
    exercise.difficulty_level = request.difficulty_level
    exercise.equipment_required = request.equipment_required
    exercise.location_type = request.location_type
    exercise.video_url = request.video_url
    exercise.image_url = request.image_url
    exercise.muscles_worked_pct = serialized["muscles_worked_pct"]
    exercise.suggested_workouts = serialized["suggested_workouts"]
    exercise.instructions = serialized["instructions"]
    exercise.safety_tips = serialized["safety_tips"]

    await db.commit()
    await db.refresh(exercise)
    return to_exercise_response(exercise)


@router.delete("/exercises/{exercise_id}")
async def admin_delete_exercise(
    exercise_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_key),
):
    result = await db.execute(select(Exercise).where(Exercise.id == exercise_id))
    exercise = result.scalars().first()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    await db.delete(exercise)
    await db.commit()
    return {"message": "Exercise deleted successfully"}
