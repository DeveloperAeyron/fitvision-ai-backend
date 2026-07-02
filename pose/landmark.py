from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np

from .base import TFLiteModel
from .decoder import LANDMARK_INPUT, decode_landmarks


class PoseLandmarker:
    def __init__(self, model_path: str, presence_threshold: float = 0.5):
        self.model = TFLiteModel(model_path)
        self.presence_threshold = presence_threshold

    def _preprocess(self, crop):
        img = cv2.resize(crop, (LANDMARK_INPUT, LANDMARK_INPUT))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32)
        img = img / 255.0  # landmark model expects [0, 1]
        return img[np.newaxis, ...]

    def estimate(self, frame, crop_box: Tuple[int, int, int, int]) -> Optional[np.ndarray]:
        x1, y1, x2, y2 = crop_box
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        outputs = self.model.infer(self._preprocess(crop))
        raw_landmarks = self.model.output_by_last_dim(outputs, 195)[0]
        presence = float(self.model.output_by_last_dim(outputs, 1, ndim=2)[0, 0])
        if presence < self.presence_threshold:
            return None

        return decode_landmarks(raw_landmarks, crop_box)
