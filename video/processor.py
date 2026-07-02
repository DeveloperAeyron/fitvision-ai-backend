from __future__ import annotations

from dataclasses import dataclass

import cv2

from pose.detector import PersonDetector
from pose.landmark import PoseLandmarker
from pose.skeleton import landmarks_to_dict
from rep_counter.counter import RepCounter
from .annotator import annotate_frame


@dataclass
class ProcessResult:
    exercise: str
    reps: int
    frames: int


class VideoProcessor:
    def __init__(self, detector: PersonDetector, landmarker: PoseLandmarker):
        self.detector = detector
        self.landmarker = landmarker

    def process(self, input_path: str, output_path: str, exercise: str) -> ProcessResult:
        counter = RepCounter(exercise)

        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video: {input_path}")

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        frames = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                frames += 1

                landmarks = None
                bbox = self.detector.detect(frame)
                if bbox is not None:
                    landmarks = self.landmarker.estimate(frame, bbox)
                    if landmarks is not None:
                        counter.update(landmarks_to_dict(landmarks))

                annotate_frame(frame, landmarks, counter.rep_count,
                               exercise, counter.last_angle)
                writer.write(frame)
        finally:
            cap.release()
            writer.release()

        return ProcessResult(exercise=exercise, reps=counter.rep_count, frames=frames)
