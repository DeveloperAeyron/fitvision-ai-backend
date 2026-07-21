from __future__ import annotations

import logging
import time

from app.config import settings
from cv.backends.base import PoseBackend
from mp_pipeline import MediaPipeVideoProcessor
from video.processor import ProcessResult

logger = logging.getLogger(__name__)


class MediaPipePoseBackend(PoseBackend):
    """MediaPipe-based pose detection backend."""

    def __init__(self) -> None:
        logger.info("loading MediaPipe pose landmarker")
        t0 = time.perf_counter()
        self._processor = MediaPipeVideoProcessor(settings.mediapipe_task_path)
        logger.info(
            "MediaPipe landmarker ready duration_ms=%.0f",
            (time.perf_counter() - t0) * 1000,
        )

    @property
    def name(self) -> str:
        return "mediapipe"

    def process(self, input_path: str, output_path: str, exercise: str) -> ProcessResult:
        return self._processor.process(input_path, output_path, exercise)
