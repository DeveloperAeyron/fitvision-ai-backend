from __future__ import annotations

import base64
import binascii
import os
import tempfile
from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from rep_counter.exercises import EXERCISES
from video.transcode import transcode_for_web

PERSON_DETECTOR_PATH = "weights/pose_person_detector_f16.tflite"
LANDMARK_MODEL_PATH = "weights/pose_landmark_detector_full_f16_inf.tflite"
MEDIAPIPE_TASK_PATH = "weights/pose_landmarker_custom.task"

router = APIRouter(tags=["rep-counting"])


class CountRepsRequest(BaseModel):
    video: str
    exercise: str = "pushup"


class CountRepsResponse(BaseModel):
    exercise: str
    reps: int
    backend: str
    video: str


@lru_cache(maxsize=1)
def _tflite_processor():
    # Built once and reused; loading the interpreters per request is expensive.
    from pose.detector import PersonDetector
    from pose.landmark import PoseLandmarker
    from video.processor import VideoProcessor
    return VideoProcessor(PersonDetector(PERSON_DETECTOR_PATH),
                          PoseLandmarker(LANDMARK_MODEL_PATH))


@lru_cache(maxsize=1)
def _mediapipe_processor():
    from mp_pipeline import MediaPipeVideoProcessor
    return MediaPipeVideoProcessor(MEDIAPIPE_TASK_PATH)


def _count_reps(request: CountRepsRequest, processor, backend: str) -> CountRepsResponse:
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
    web_path: str | None = None

    try:
        with open(in_path, "wb") as f:
            f.write(video_bytes)

        result = processor.process(in_path, out_path, exercise)

        web_path = transcode_for_web(out_path)
        with open(web_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    finally:
        for path in (in_path, out_path, web_path):
            if path and os.path.exists(path):
                os.remove(path)

    return CountRepsResponse(exercise=result.exercise, reps=result.reps,
                             backend=backend, video=encoded)


@router.post("/count-reps", response_model=CountRepsResponse)
def count_reps(request: CountRepsRequest) -> CountRepsResponse:
    return _count_reps(request, _tflite_processor(), "tflite")


@router.post("/count-reps-mediapipe", response_model=CountRepsResponse)
def count_reps_mediapipe(request: CountRepsRequest) -> CountRepsResponse:
    return _count_reps(request, _mediapipe_processor(), "mediapipe")
