from __future__ import annotations

from typing import Optional

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision


class MediaPipePoseLandmarker:
    # Wraps MediaPipe Tasks PoseLandmarker. MediaPipe internally runs person
    # detection, rotated-ROI alignment, landmark inference, tracking and
    # smoothing, so this returns ready-to-use landmarks in original pixels.
    def __init__(self, task_path: str, num_poses: int = 1):
        options = vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=task_path),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=num_poses,
        )
        self.landmarker = vision.PoseLandmarker.create_from_options(options)

    def estimate(self, frame_bgr, timestamp_ms: int) -> Optional[np.ndarray]:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect_for_video(mp_image, int(timestamp_ms))
        if not result.pose_landmarks:
            return None

        h, w = frame_bgr.shape[:2]
        pose = result.pose_landmarks[0]
        out = np.zeros((len(pose), 4), dtype=np.float32)
        for i, lm in enumerate(pose):
            out[i] = (lm.x * w, lm.y * h, lm.z, lm.visibility)
        return out

    def close(self):
        self.landmarker.close()
