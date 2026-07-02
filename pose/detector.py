from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from .base import TFLiteModel
from .decoder import (
    DETECTOR_INPUT,
    decode_boxes,
    decode_keypoints,
    decode_scores,
    generate_anchors,
    letterbox,
    non_max_suppression,
    unletterbox_points,
)
from .roi import ROI, roi_from_keypoints


class PersonDetector:
    def __init__(self, model_path: str, score_threshold: float = 0.5,
                 roi_scale: float = 1.5):
        self.model = TFLiteModel(model_path)
        self.anchors = generate_anchors()
        self.score_threshold = score_threshold
        self.roi_scale = roi_scale

    def detect(self, frame) -> Optional[ROI]:
        canvas, scale, pad_x, pad_y = letterbox(frame, DETECTOR_INPUT)
        inp = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32)
        inp = (inp / 127.5 - 1.0)[np.newaxis, ...]

        outputs = self.model.infer(inp)
        raw = self.model.output_by_last_dim(outputs, 12)[0]
        scores = decode_scores(self.model.output_by_last_dim(outputs, 1, ndim=3)[0])

        mask = scores >= self.score_threshold
        if not np.any(mask):
            return None
        boxes = decode_boxes(raw, self.anchors)[mask]
        keypoints = decode_keypoints(raw, self.anchors)[mask]
        scores = scores[mask]

        keep = non_max_suppression(boxes, scores)
        if not keep:
            return None

        kp = unletterbox_points(keypoints[keep[0]], scale, pad_x, pad_y)
        return roi_from_keypoints(kp[0], kp[1], scale=self.roi_scale)
