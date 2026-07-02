from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np

from .base import TFLiteModel
from .decoder import (
    DETECTOR_INPUT,
    decode_boxes,
    decode_scores,
    generate_anchors,
    non_max_suppression,
)


class PersonDetector:
    def __init__(self, model_path: str, score_threshold: float = 0.5,
                 crop_margin: float = 0.25):
        self.model = TFLiteModel(model_path)
        self.anchors = generate_anchors()
        self.score_threshold = score_threshold
        self.crop_margin = crop_margin

    def _preprocess(self, frame):
        img = cv2.resize(frame, (DETECTOR_INPUT, DETECTOR_INPUT))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32)
        img = img / 127.5 - 1.0  # detector expects [-1, 1]
        return img[np.newaxis, ...]

    def detect(self, frame) -> Optional[Tuple[int, int, int, int]]:
        h, w = frame.shape[:2]
        outputs = self.model.infer(self._preprocess(frame))
        raw_boxes = self.model.output_by_last_dim(outputs, 12)[0]
        raw_scores = self.model.output_by_last_dim(outputs, 1, ndim=3)[0]

        boxes = decode_boxes(raw_boxes, self.anchors)
        scores = decode_scores(raw_scores)

        mask = scores >= self.score_threshold
        if not np.any(mask):
            return None
        boxes, scores = boxes[mask], scores[mask]

        keep = non_max_suppression(boxes, scores)
        if not keep:
            return None
        best = boxes[keep[0]]

        # Expand the tight detection box so the whole body reaches the
        # landmark model, then clamp to image bounds and convert to pixels.
        bw = best[2] - best[0]
        bh = best[3] - best[1]
        x1 = (best[0] - self.crop_margin * bw) * w
        y1 = (best[1] - self.crop_margin * bh) * h
        x2 = (best[2] + self.crop_margin * bw) * w
        y2 = (best[3] + self.crop_margin * bh) * h

        x1 = max(0, int(x1)); y1 = max(0, int(y1))
        x2 = min(w, int(x2)); y2 = min(h, int(y2))
        if x2 <= x1 or y2 <= y1:
            return None
        return x1, y1, x2, y2
