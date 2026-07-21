from __future__ import annotations

from abc import ABC, abstractmethod

from video.processor import ProcessResult


class PoseBackend(ABC):
    """Strategy interface for pose-detection video processors."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier returned in API responses (e.g. 'tflite')."""

    @abstractmethod
    def process(self, input_path: str, output_path: str, exercise: str) -> ProcessResult:
        """Run pose detection and rep counting on a video file."""
