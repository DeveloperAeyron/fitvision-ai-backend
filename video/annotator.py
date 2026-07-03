from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from pose.skeleton import draw_skeleton


def annotate_frame(frame, landmarks: Optional[np.ndarray], rep_count: int,
                   exercise: str, angle: Optional[float] = None):
    if landmarks is not None:
        draw_skeleton(frame, landmarks)

    h, w = frame.shape[:2]
    text = f"Reps: {rep_count}"
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 1.2
    thickness = 3
    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)

    # Rep count anchored to the bottom-right corner.
    x = w - tw - 20
    y = h - 20
    cv2.rectangle(frame, (x - 12, y - th - 12), (x + tw + 12, y + baseline + 8),
                  (0, 0, 0), -1)
    cv2.putText(frame, text, (x, y), font, scale, (0, 255, 0), thickness, cv2.LINE_AA)

    label = exercise.upper()
    if angle is not None:
        if exercise.lower() == "squat" and angle <= 2.0:
            label += f"  {angle * 100:.0f}% depth"
        else:
            label += f"  {angle:.0f}deg"
    cv2.putText(frame, label, (20, 40), font, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    return frame
