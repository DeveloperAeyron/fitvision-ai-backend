from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings:
    """Centralized application settings (env vars override defaults)."""

    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8003"))

    person_detector_path: str = os.getenv(
        "PERSON_DETECTOR_PATH", "weights/pose_person_detector_f16.tflite"
    )
    landmark_model_path: str = os.getenv(
        "LANDMARK_MODEL_PATH", "weights/pose_landmark_detector_full_f16_inf.tflite"
    )
    mediapipe_task_path: str = os.getenv(
        "MEDIAPIPE_TASK_PATH", "weights/pose_landmarker_custom.task"
    )
    tcn_model_path: str = os.getenv("TCN_MODEL_PATH", "weights/TCN-exercise.pt")
    equipment_model_path: str = os.getenv(
        "EQUIPMENT_MODEL_PATH", "weights/Equipment-detection.pt"
    )

    uploads_dir: Path = ROOT_DIR / "uploads"
    static_dir: Path = ROOT_DIR / "static"


settings = Settings()
