from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from .base import TFLiteModel
from .decoder import LANDMARK_INPUT, decode_landmarks
from .roi import ROI, extract_crop, project_landmarks


class PoseLandmarker:
    def __init__(self, model_path: str, presence_threshold: float = 0.5):
        self.model = TFLiteModel(model_path)
        self.presence_threshold = presence_threshold

    def estimate(self, frame, roi: ROI) -> Optional[np.ndarray]:
        # Returns all 39 landmarks in original-image pixels as (39, 4)
        # [x, y, z, visibility], or None if no pose is present in the ROI.
        crop, inv = extract_crop(frame, roi, LANDMARK_INPUT)

        inp = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32)
        inp = (inp / 255.0)[np.newaxis, ...]

        outputs = self.model.infer(inp)
        presence = float(self.model.output_by_last_dim(outputs, 1, ndim=2)[0, 0])
        if presence < self.presence_threshold:  # flag is already a probability
            return None

        raw_landmarks = self.model.output_by_last_dim(outputs, 195)[0]
        landmarks = decode_landmarks(raw_landmarks)
        return project_landmarks(landmarks, inv)
