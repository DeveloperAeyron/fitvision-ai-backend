from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from .decoder import LANDMARK_INPUT

_TARGET_ANGLE = math.pi / 2.0  # BlazePose aligns the person to point "up".


@dataclass
class ROI:
    cx: float
    cy: float
    size: float          # side length of the square crop, in original pixels
    rotation: float      # radians; person's in-image rotation (0 = upright)


def _rotation(start, end):
    # Angle that rotates the start->end vector onto the target (upward) axis.
    return _TARGET_ANGLE - math.atan2(-(end[1] - start[1]), end[0] - start[0])


def roi_from_keypoints(kp0, kp1, scale=1.5):
    # kp0 = mid-hip (crop centre), kp1 = full-body scale/rotation point.
    cx, cy = float(kp0[0]), float(kp0[1])
    size = 2.0 * math.hypot(kp1[0] - kp0[0], kp1[1] - kp0[1]) * scale
    return ROI(cx, cy, size, _rotation(kp0, kp1))


def roi_from_landmarks(landmarks_px, scale=1.5):
    # Tracking ROI derived from the previous frame's landmarks, so we can skip
    # re-detection. Centre = mid-hip, orientation = mid-hip -> mid-shoulder,
    # size = span of the visible body around the centre.
    l_sh, r_sh = landmarks_px[11], landmarks_px[12]
    l_hip, r_hip = landmarks_px[23], landmarks_px[24]
    mid_hip = ((l_hip[0] + r_hip[0]) / 2.0, (l_hip[1] + r_hip[1]) / 2.0)
    mid_sh = ((l_sh[0] + r_sh[0]) / 2.0, (l_sh[1] + r_sh[1]) / 2.0)

    pts = landmarks_px[:33, :2]
    radius = np.max(np.hypot(pts[:, 0] - mid_hip[0], pts[:, 1] - mid_hip[1]))
    size = 2.0 * radius * scale
    return ROI(mid_hip[0], mid_hip[1], size, _rotation(mid_hip, mid_sh))


def _corners(roi: ROI):
    cos, sin = math.cos(roi.rotation), math.sin(roi.rotation)
    half = roi.size / 2.0
    # Upright-local corners (top-left, top-right, bottom-left) rotated into the frame.
    local = [(-half, -half), (half, -half), (-half, half)]
    return np.array(
        [[roi.cx + lx * cos - ly * sin, roi.cy + lx * sin + ly * cos]
         for lx, ly in local],
        dtype=np.float32,
    )


def roi_transforms(roi: ROI, out_size=LANDMARK_INPUT):
    # M warps the rotated ROI to an upright out_size square; inv maps landmark
    # pixels from that square back to original-image pixels.
    src = _corners(roi)
    dst = np.array([[0, 0], [out_size, 0], [0, out_size]], dtype=np.float32)
    M = cv2.getAffineTransform(src, dst)
    inv = cv2.invertAffineTransform(M)
    return M, inv


def extract_crop(frame, roi: ROI, out_size=LANDMARK_INPUT):
    M, inv = roi_transforms(roi, out_size)
    crop = cv2.warpAffine(frame, M, (out_size, out_size), flags=cv2.INTER_LINEAR,
                          borderValue=(128, 128, 128))
    return crop, inv


def project_landmarks(landmarks, inv):
    # landmarks[:, :2] are in the upright crop's pixel space -> original pixels.
    xy = landmarks[:, :2]
    ones = np.ones((xy.shape[0], 1), dtype=np.float32)
    projected = (np.hstack([xy, ones]) @ inv.T)
    out = landmarks.copy()
    out[:, 0] = projected[:, 0]
    out[:, 1] = projected[:, 1]
    return out
