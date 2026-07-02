from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from pose.detector import PersonDetector
from pose.landmark import PoseLandmarker
from pose.roi import ROI, roi_from_landmarks
from pose.skeleton import landmarks_to_dict
from pose.smoothing import LandmarkSmoother
from rep_counter.counter import RepCounter
from .annotator import annotate_frame

_TORSO = [11, 12, 23, 24]  # shoulders + hips


@dataclass
class ProcessResult:
    exercise: str
    reps: int
    frames: int


class VideoProcessor:
    def __init__(self, detector: PersonDetector, landmarker: PoseLandmarker,
                 track_visibility: float = 0.5):
        self.detector = detector
        self.landmarker = landmarker
        self.track_visibility = track_visibility

    def _next_roi(self, landmarks: np.ndarray) -> Optional[ROI]:
        # Track from landmarks only while the torso is confidently visible;
        # otherwise force a fresh detection on the next frame.
        if np.mean(landmarks[_TORSO, 3]) < self.track_visibility:
            return None
        return roi_from_landmarks(landmarks)

    def process(self, input_path: str, output_path: str, exercise: str) -> ProcessResult:
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video: {input_path}")

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

        writer = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*"mp4v"),
                                 fps, (width, height))
        counter = RepCounter(exercise)
        smoother = LandmarkSmoother(fps)
        roi: Optional[ROI] = None

        frames = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                frames += 1

                landmarks = self.landmarker.estimate(frame, roi) if roi else None
                if landmarks is None:  # first frame or tracking lost -> re-detect
                    roi = self.detector.detect(frame)
                    landmarks = self.landmarker.estimate(frame, roi) if roi else None

                if landmarks is not None:
                    landmarks = smoother.apply(landmarks)
                    counter.update(landmarks_to_dict(landmarks))
                    roi = self._next_roi(landmarks)
                else:
                    roi = None

                annotate_frame(frame, landmarks, counter.rep_count,
                               exercise, counter.last_angle)
                writer.write(frame)
        finally:
            cap.release()
            writer.release()

        return ProcessResult(exercise=exercise, reps=counter.rep_count, frames=frames)
