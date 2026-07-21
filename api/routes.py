from __future__ import annotations

import base64
import binascii
import logging
import os
import tempfile
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from cv.backends import get_backend
from rep_counter.exercises import EXERCISES
from video.transcode import transcode_for_web

logger = logging.getLogger(__name__)

router = APIRouter(tags=["rep-counting"])


class CountRepsRequest(BaseModel):
    video: str
    exercise: str = "pushup"


class CountRepsResponse(BaseModel):
    exercise: str
    reps: int
    backend: str
    video: str


def _count_reps(request: CountRepsRequest, backend_name: str) -> CountRepsResponse:
    exercise = request.exercise.lower().strip()
    if exercise not in EXERCISES:
        raise HTTPException(400, f"Unsupported exercise. Choose from {sorted(EXERCISES)}.")

    try:
        video_bytes = base64.b64decode(request.video, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "Invalid base64 video payload.")
    if not video_bytes:
        raise HTTPException(400, "Empty video payload.")

    backend = get_backend(backend_name)
    t0 = time.perf_counter()
    logger.info(
        "count-reps start backend=%s exercise=%s input_bytes=%d",
        backend.name, exercise, len(video_bytes),
    )

    in_fd, in_path = tempfile.mkstemp(suffix=".mp4")
    out_fd, out_path = tempfile.mkstemp(suffix=".mp4")
    os.close(in_fd)
    os.close(out_fd)
    web_path: str | None = None

    try:
        with open(in_path, "wb") as f:
            f.write(video_bytes)

        result = backend.process(in_path, out_path, exercise)

        web_path = transcode_for_web(out_path)
        with open(web_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
    except RuntimeError as exc:
        logger.error(
            "count-reps failed backend=%s exercise=%s: %s",
            backend.name, exercise, exc,
        )
        raise HTTPException(400, str(exc))
    finally:
        for path in dict.fromkeys((in_path, out_path, web_path)):
            if path and os.path.exists(path):
                os.remove(path)

    logger.info(
        "count-reps done backend=%s exercise=%s reps=%d frames=%d "
        "output_bytes=%d duration_ms=%.0f",
        backend.name, exercise, result.reps, result.frames,
        len(encoded), (time.perf_counter() - t0) * 1000,
    )

    return CountRepsResponse(
        exercise=result.exercise,
        reps=result.reps,
        backend=backend.name,
        video=encoded,
    )


@router.post("/count-reps", response_model=CountRepsResponse)
def count_reps(request: CountRepsRequest) -> CountRepsResponse:
    return _count_reps(request, "tflite")


@router.post("/count-reps-mediapipe", response_model=CountRepsResponse)
def count_reps_mediapipe(request: CountRepsRequest) -> CountRepsResponse:
    return _count_reps(request, "mediapipe")
