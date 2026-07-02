from __future__ import annotations

from typing import Dict, Optional, Tuple

from .angles import calculate_angle
from .exercises import get_exercise


class RepCounter:
    # Exercise-agnostic, online rep counter. Fixed angle thresholds (e.g.
    # elbow <90 / >160) don't survive real footage: a side-view push-up elbow
    # may only open to ~150 in 2D projection. Instead the counter learns the
    # angle's range of motion on the fly and places hysteresis thresholds
    # relative to it, so it adapts to camera view and exercise automatically.
    def __init__(self, exercise: str = "pushup", visibility_threshold: float = 0.3,
                 enter_frac: float = 0.30, exit_frac: float = 0.30,
                 envelope_decay: float = 0.01):
        self.config = get_exercise(exercise)
        self.visibility_threshold = visibility_threshold
        self.enter_frac = enter_frac
        self.exit_frac = exit_frac
        self.envelope_decay = envelope_decay

        self.rep_count = 0
        self.current_state = "up"
        self.previous_state = "up"
        self.last_angle: Optional[float] = None
        self._lo: Optional[float] = None
        self._hi: Optional[float] = None

    def _measure(self, landmarks: Dict[str, Tuple[float, float, float]]) -> Optional[float]:
        best_angle = None
        best_vis = -1.0
        for a, b, c in self.config.triplets:
            if a not in landmarks or b not in landmarks or c not in landmarks:
                continue
            vis = min(landmarks[a][2], landmarks[b][2], landmarks[c][2])
            if vis < self.visibility_threshold:
                continue
            if vis > best_vis:
                best_vis = vis
                best_angle = calculate_angle(landmarks[a], landmarks[b], landmarks[c])
        return best_angle

    def update(self, landmarks: Dict[str, Tuple[float, float, float]]) -> int:
        angle = self._measure(landmarks)
        if angle is None:
            return self.rep_count
        self.last_angle = angle

        if self._lo is None:
            self._lo = self._hi = angle
            return self.rep_count

        # Expand the envelope to new extremes instantly, contract it slowly so
        # stale extremes decay and the range tracks the current motion.
        self._hi = max(angle, self._hi) + (angle - max(angle, self._hi)) * self.envelope_decay
        self._lo = min(angle, self._lo) + (angle - min(angle, self._lo)) * self.envelope_decay

        rng = self._hi - self._lo
        if rng < self.config.min_range:
            return self.rep_count

        down_th = self._lo + self.enter_frac * rng
        up_th = self._hi - self.exit_frac * rng

        self.previous_state = self.current_state
        if angle < down_th:
            self.current_state = "down"
        elif angle > up_th and self.current_state == "down":
            self.rep_count += 1
            self.current_state = "up"
        return self.rep_count
