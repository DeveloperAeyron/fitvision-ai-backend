from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .angles import calculate_angle
from .exercises import get_exercise


class RepCounter:
    # Exercise-agnostic, online rep counter. Fixed angle thresholds (e.g.
    # elbow <90 / >160) don't survive real footage: a side-view push-up elbow
    # may only open to ~150 in 2D projection. Instead the counter learns the
    # angle's range of motion on the fly and places hysteresis thresholds
    # relative to it, so it adapts to camera view and exercise automatically.
    def __init__(self, exercise: str = "pushup", visibility_threshold: float = 0.3,
                 envelope_decay: float = 0.01):
        self.config = get_exercise(exercise)
        self.visibility_threshold = visibility_threshold
        self.envelope_decay = envelope_decay

        self.rep_count = 0
        self.current_state = "up"
        self.previous_state = "up"
        self.last_angle: Optional[float] = None
        self._lo: Optional[float] = None
        self._hi: Optional[float] = None
        self._smooth_buf: List[float] = []

    def _measure_angle(self, landmarks: Dict[str, Tuple[float, float, float]]) -> Optional[float]:
        angles: List[float] = []
        for a, b, c in self.config.triplets:
            if a not in landmarks or b not in landmarks or c not in landmarks:
                continue
            vis = min(landmarks[a][2], landmarks[b][2], landmarks[c][2])
            if vis < self.visibility_threshold:
                continue
            angle = calculate_angle(landmarks[a], landmarks[b], landmarks[c])
            if self.config.min_valid is not None and angle < self.config.min_valid:
                continue
            if self.config.max_valid is not None and angle > self.config.max_valid:
                continue
            angles.append(angle)

        if not angles:
            return None
        if self.config.average_sides:
            return sum(angles) / len(angles)
        return angles[0]

    def _measure_hip_drop(self, landmarks: Dict[str, Tuple[float, float, float]],
                          frame_height: int) -> Optional[float]:
        ys: List[float] = []
        for key in ("left_hip", "right_hip"):
            if key not in landmarks:
                continue
            x, y, vis = landmarks[key]
            if vis < self.visibility_threshold:
                continue
            ys.append(y)
        if not ys:
            return None
        return (sum(ys) / len(ys)) / frame_height

    def _smooth(self, value: float) -> float:
        window = self.config.smooth_window
        if window <= 1:
            return value
        self._smooth_buf.append(value)
        if len(self._smooth_buf) > window:
            self._smooth_buf.pop(0)
        return sum(self._smooth_buf) / len(self._smooth_buf)

    def _measure(self, landmarks: Dict[str, Tuple[float, float, float]],
                 frame_height: Optional[int]) -> Optional[float]:
        if self.config.metric == "hip_drop":
            if frame_height is None:
                return None
            return self._measure_hip_drop(landmarks, frame_height)
        return self._measure_angle(landmarks)

    def update(self, landmarks: Dict[str, Tuple[float, float, float]],
               frame_height: Optional[int] = None) -> int:
        raw = self._measure(landmarks, frame_height)
        if raw is None:
            return self.rep_count

        value = self._smooth(raw)
        self.last_angle = value

        if self._lo is None:
            self._lo = self._hi = value
            return self.rep_count

        # Expand the envelope to new extremes instantly, contract it slowly so
        # stale extremes decay and the range tracks the current motion.
        self._hi = max(value, self._hi) + (value - max(value, self._hi)) * self.envelope_decay
        self._lo = min(value, self._lo) + (value - min(value, self._lo)) * self.envelope_decay

        rng = self._hi - self._lo
        if rng < self.config.min_range:
            return self.rep_count

        if self.config.flexion == "decreasing":
            down_th = self._lo + self.config.enter_frac * rng
            up_th = self._hi - self.config.exit_frac * rng
            if value < down_th:
                self.current_state = "down"
            elif value > up_th and self.current_state == "down":
                self.rep_count += 1
                self.current_state = "up"
        else:
            down_th = self._hi - self.config.enter_frac * rng
            up_th = self._lo + self.config.exit_frac * rng
            if value > down_th:
                self.current_state = "down"
            elif value < up_th and self.current_state == "down":
                self.rep_count += 1
                self.current_state = "up"

        self.previous_state = self.current_state
        return self.rep_count
