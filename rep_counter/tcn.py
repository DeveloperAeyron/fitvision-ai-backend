from __future__ import annotations

import logging
import zipfile
from collections import Counter, deque
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# First 28 BlazePose landmarks → normalized (x, y) pairs = 56 features.
NUM_KEYPOINTS = 28
WINDOW_SIZE = 30
FEATURE_DIM = NUM_KEYPOINTS * 2

# 7-class output: per-exercise up/down/other (matches TCN training labels).
TCN_CLASSES = (
    "pushup_up",
    "pushup_down",
    "squat_up",
    "squat_down",
    "situp_up",
    "situp_down",
    "other",
)

_model: object | None = None
_model_path: Path | None = None


def default_tcn_path() -> Path:
    try:
        from app.config import settings
        return Path(settings.tcn_model_path)
    except ImportError:
        return Path(__file__).resolve().parent.parent / "weights" / "TCN-exercise.pt"


def landmarks_to_tcn_features(landmarks: np.ndarray) -> np.ndarray:
    """Convert a (33, 4) landmark array into a 56-dim normalized feature vector."""
    pts = landmarks[:NUM_KEYPOINTS, :2].astype(np.float32)

    left_hip = landmarks[23, :2]
    right_hip = landmarks[24, :2]
    center = (left_hip + right_hip) / 2.0

    left_shoulder = landmarks[11, :2]
    right_shoulder = landmarks[12, :2]
    scale = (
        np.linalg.norm(left_shoulder - left_hip)
        + np.linalg.norm(right_shoulder - right_hip)
    ) / 2.0
    scale = max(float(scale), 1e-6)

    normalized = (pts - center) / scale
    return normalized.reshape(FEATURE_DIM)


def load_tcn_model(model_path: Path | None = None):
    """Load the Keras TCN model (saved as a zip archive with a .pt extension)."""
    global _model, _model_path

    path = Path(model_path) if model_path else default_tcn_path()
    if _model is not None and _model_path == path:
        return _model

    if not path.exists():
        logger.warning("TCN model not found at %s", path)
        return None

    try:
        import tensorflow as tf
    except ImportError:
        logger.warning("TensorFlow unavailable — TCN rep counter disabled")
        return None

    extract_dir = path.parent / ".tcn_cache"
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(path) as archive:
            archive.extractall(extract_dir)
        model = tf.keras.models.load_model(str(extract_dir))
        _model = model
        _model_path = path
        logger.info("Loaded TCN rep model from %s", path)
        return model
    except Exception as exc:
        logger.error("Failed to load TCN model from %s: %s", path, exc)
        return None


def predict_tcn_state(model, sequence: np.ndarray) -> int:
    """Run inference on a (1, 30, 56) sequence; return class index."""
    probs = model.predict(sequence, verbose=0)[0]
    return int(np.argmax(probs))


class TCNRepTracker:
    """Sliding-window TCN rep counter for a single exercise."""

    def __init__(self, exercise: str, model_path: Path | None = None):
        self.exercise = exercise.lower().strip()
        self.model = load_tcn_model(model_path)
        self.enabled = self.model is not None
        self.rep_count = 0
        self.current_state = "up"
        self.frames_since_last_rep = 99
        self._buffer: deque[np.ndarray] = deque(maxlen=WINDOW_SIZE)
        self._pred_history: deque[str] = deque(maxlen=5)

    def _parse_class(self, class_idx: int) -> tuple[str, str] | None:
        if class_idx < 0 or class_idx >= len(TCN_CLASSES):
            return None
        label = TCN_CLASSES[class_idx]
        if label == "other":
            return None
        exercise, state = label.rsplit("_", 1)
        return exercise, state

    def update(self, landmarks: np.ndarray) -> int:
        if not self.enabled:
            return self.rep_count

        self._buffer.append(landmarks_to_tcn_features(landmarks))
        if len(self._buffer) < WINDOW_SIZE:
            return self.rep_count

        sequence = np.array(self._buffer, dtype=np.float32)[np.newaxis, ...]
        class_idx = predict_tcn_state(self.model, sequence)
        parsed = self._parse_class(class_idx)
        if parsed is None:
            return self.rep_count

        exercise, state = parsed
        if exercise != self.exercise:
            return self.rep_count

        self._pred_history.append(state)
        smoothed = Counter(self._pred_history).most_common(1)[0][0]
        self.frames_since_last_rep += 1

        if smoothed == "down":
            self.current_state = "down"
        elif smoothed == "up" and self.current_state == "down":
            if self.frames_since_last_rep >= 15:
                self.rep_count += 1
                self.frames_since_last_rep = 0
            self.current_state = "up"

        return self.rep_count
