from __future__ import annotations

import logging
import time

from app.config import settings
from cv.backends.base import PoseBackend
from pose.detector import PersonDetector
from pose.landmark import PoseLandmarker
from video.processor import ProcessResult, VideoProcessor

logger = logging.getLogger(__name__)


class TflitePoseBackend(PoseBackend):
    """TFLite-based pose detection backend."""

    def __init__(self) -> None:
        logger.info("loading TFLite pose models")
        t0 = time.perf_counter()
        self._processor = VideoProcessor(
            PersonDetector(settings.person_detector_path),
            PoseLandmarker(settings.landmark_model_path),
        )
        logger.info(
            "TFLite models ready duration_ms=%.0f",
            (time.perf_counter() - t0) * 1000,
        )

    @property
    def name(self) -> str:
        return "tflite"

    def process(self, input_path: str, output_path: str, exercise: str) -> ProcessResult:
        return self._processor.process(input_path, output_path, exercise)
