from __future__ import annotations

from typing import Dict, Tuple

import cv2
import numpy as np

# First 33 BlazePose landmarks (the model emits 39; the rest are auxiliary).
LANDMARK_NAMES = [
    "nose",
    "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear",
    "mouth_left", "mouth_right",
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_pinky", "right_pinky",
    "left_index", "right_index",
    "left_thumb", "right_thumb",
    "left_hip", "right_hip",
    "left_knee", "right_knee",
    "left_ankle", "right_ankle",
    "left_heel", "right_heel",
    "left_foot_index", "right_foot_index",
]

_IDX = {name: i for i, name in enumerate(LANDMARK_NAMES)}

POSE_CONNECTIONS = [
    (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21), (17, 19),
    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22), (18, 20),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (27, 29), (29, 31), (27, 31),
    (24, 26), (26, 28), (28, 30), (30, 32), (28, 32),
]


def landmarks_to_dict(landmarks: np.ndarray,
                      visibility_threshold: float = 0.0) -> Dict[str, Tuple[float, float, float]]:
    result = {}
    for i, name in enumerate(LANDMARK_NAMES):
        x, y, _z, vis = landmarks[i]
        if vis >= visibility_threshold:
            result[name] = (float(x), float(y), float(vis))
    return result


def draw_skeleton(frame, landmarks: np.ndarray, visibility_threshold: float = 0.5):
    h, w = frame.shape[:2]

    for a, b in POSE_CONNECTIONS:
        if landmarks[a][3] < visibility_threshold or landmarks[b][3] < visibility_threshold:
            continue
        pa = (int(landmarks[a][0]), int(landmarks[a][1]))
        pb = (int(landmarks[b][0]), int(landmarks[b][1]))
        cv2.line(frame, pa, pb, (0, 255, 0), 2)

    for i in range(len(LANDMARK_NAMES)):
        if landmarks[i][3] < visibility_threshold:
            continue
        p = (int(landmarks[i][0]), int(landmarks[i][1]))
        cv2.circle(frame, p, 4, (0, 0, 255), -1)
    return frame
