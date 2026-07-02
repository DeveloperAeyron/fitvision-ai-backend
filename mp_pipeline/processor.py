from __future__ import annotations

import cv2

from pose.skeleton import landmarks_to_dict
from rep_counter.counter import RepCounter
from video.annotator import annotate_frame
from video.processor import ProcessResult
from .landmarker import MediaPipePoseLandmarker


class MediaPipeVideoProcessor:
    def __init__(self, task_path: str):
        self.task_path = task_path

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
        # Fresh landmarker per video: VIDEO mode requires timestamps that
        # increase monotonically over the instance's whole lifetime.
        landmarker = MediaPipePoseLandmarker(self.task_path)

        frames = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                timestamp_ms = int(frames * 1000.0 / fps)
                frames += 1

                landmarks = landmarker.estimate(frame, timestamp_ms)
                if landmarks is not None:
                    counter.update(landmarks_to_dict(landmarks))

                annotate_frame(frame, landmarks, counter.rep_count,
                               exercise, counter.last_angle)
                writer.write(frame)
        finally:
            cap.release()
            writer.release()
            landmarker.close()

        return ProcessResult(exercise=exercise, reps=counter.rep_count, frames=frames)
