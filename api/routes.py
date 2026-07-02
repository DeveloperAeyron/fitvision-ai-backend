from __future__ import annotations

import base64
import binascii
import os
import tempfile
from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from pose.detector import PersonDetector
from pose.landmark import PoseLandmarker
from rep_counter.exercises import EXERCISES
from video.processor import VideoProcessor

PERSON_DETECTOR_PATH = "weights/pose_person_detector_f16.tflite"
LANDMARK_MODEL_PATH = "weights/pose_landmark_detector_full_f16_inf.tflite"

router = APIRouter()


class CountRepsRequest(BaseModel):
    video: str
    exercise: str = "pushup"


class CountRepsResponse(BaseModel):
    exercise: str
    reps: int
    video: str


@lru_cache(maxsize=1)
def get_processor() -> VideoProcessor:
    # Built once and reused; loading the interpreters per request is expensive.
    detector = PersonDetector(PERSON_DETECTOR_PATH)
    landmarker = PoseLandmarker(LANDMARK_MODEL_PATH)
    return VideoProcessor(detector, landmarker)


@router.post("/count-reps", response_model=CountRepsResponse)
def count_reps(request: CountRepsRequest) -> CountRepsResponse:
    exercise = request.exercise.lower().strip()
    if exercise not in EXERCISES:
        raise HTTPException(400, f"Unsupported exercise. Choose from {sorted(EXERCISES)}.")

    try:
        video_bytes = base64.b64decode(request.video, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "Invalid base64 video payload.")
    if not video_bytes:
        raise HTTPException(400, "Empty video payload.")

    in_fd, in_path = tempfile.mkstemp(suffix=".mp4")
    out_fd, out_path = tempfile.mkstemp(suffix=".mp4")
    os.close(in_fd)
    os.close(out_fd)

    try:
        with open(in_path, "wb") as f:
            f.write(video_bytes)

        result = get_processor().process(in_path, out_path, exercise)

        with open(out_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    finally:
        for path in (in_path, out_path):
            if os.path.exists(path):
                os.remove(path)

    return CountRepsResponse(exercise=result.exercise, reps=result.reps, video=encoded)
