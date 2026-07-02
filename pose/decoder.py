from __future__ import annotations

import numpy as np

DETECTOR_INPUT = 224
LANDMARK_INPUT = 256

# SSD anchor options for the BlazePose person detector (produce 2254 anchors).
_ANCHOR_STRIDES = [8, 16, 32, 32, 32]
_ANCHOR_INPUT = 224


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -60.0, 60.0)))


def generate_anchors():
    # MediaPipe SsdAnchorsCalculator: one anchor centre per feature-map cell,
    # doubled per cell (base + interpolated scale). Consecutive equal strides
    # share a feature map, stacking their anchors on the same grid.
    anchors = []
    n = len(_ANCHOR_STRIDES)
    i = 0
    while i < n:
        stride = _ANCHOR_STRIDES[i]
        fm = _ANCHOR_INPUT // stride

        repeats = 0
        j = i
        while j < n and _ANCHOR_STRIDES[j] == stride:
            repeats += 2  # base + interpolated aspect ratio
            j += 1

        for y in range(fm):
            y_center = (y + 0.5) / fm
            for x in range(fm):
                x_center = (x + 0.5) / fm
                for _ in range(repeats):
                    anchors.append((x_center, y_center))
        i = j
    return np.array(anchors, dtype=np.float32)


def decode_boxes(raw_boxes, anchors):
    # raw_boxes: (num_anchors, 12) = [x, y, w, h, then 4 keypoints (x, y)].
    # fixed_anchor_size -> anchor w = h = 1, so scale is just the input size.
    scale = float(DETECTOR_INPUT)
    x_center = raw_boxes[:, 0] / scale + anchors[:, 0]
    y_center = raw_boxes[:, 1] / scale + anchors[:, 1]
    w = raw_boxes[:, 2] / scale
    h = raw_boxes[:, 3] / scale

    boxes = np.zeros((raw_boxes.shape[0], 4), dtype=np.float32)
    boxes[:, 0] = x_center - w / 2.0  # xmin  (normalised 0..1)
    boxes[:, 1] = y_center - h / 2.0  # ymin
    boxes[:, 2] = x_center + w / 2.0  # xmax
    boxes[:, 3] = y_center + h / 2.0  # ymax
    return boxes


def decode_scores(raw_scores):
    return _sigmoid(np.clip(raw_scores.reshape(-1), -100.0, 100.0))


def non_max_suppression(boxes, scores, iou_threshold=0.3):
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    order = scores.argsort()[::-1]

    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
        order = order[1:][iou <= iou_threshold]
    return keep


def decode_landmarks(raw_landmarks, crop_box):
    # raw_landmarks: (195,) -> 39 landmarks x (x, y, z, visibility, presence).
    # x, y are in 256-input pixels; map them back into original-image pixels
    # using the crop rectangle the landmark model was actually run on.
    lm = raw_landmarks.reshape(-1, 5)
    x1, y1, x2, y2 = crop_box
    crop_w = x2 - x1
    crop_h = y2 - y1

    out = np.zeros((lm.shape[0], 4), dtype=np.float32)
    out[:, 0] = x1 + (lm[:, 0] / LANDMARK_INPUT) * crop_w  # original x (px)
    out[:, 1] = y1 + (lm[:, 1] / LANDMARK_INPUT) * crop_h  # original y (px)
    out[:, 2] = lm[:, 2]                                   # z (relative depth)
    out[:, 3] = _sigmoid(lm[:, 3])                         # visibility
    return out
