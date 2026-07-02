from __future__ import annotations

import numpy as np


def calculate_angle(point_a, point_b, point_c) -> float:
    a = np.array(point_a[:2], dtype=np.float32)
    b = np.array(point_b[:2], dtype=np.float32)
    c = np.array(point_c[:2], dtype=np.float32)

    ba = a - b
    bc = c - b
    cosine = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-9)
    return float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))
