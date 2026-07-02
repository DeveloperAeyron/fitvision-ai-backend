from __future__ import annotations

from typing import Dict, Optional, Tuple

from .angles import calculate_angle
from .exercises import get_exercise


class RepCounter:
    def __init__(self, exercise: str = "pushup", visibility_threshold: float = 0.3):
        self.config = get_exercise(exercise)
        self.visibility_threshold = visibility_threshold

        self.rep_count = 0
        self.current_state = self.config.start_state
        self.previous_state = self.config.start_state
        self.last_angle: Optional[float] = None

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
        self.previous_state = self.current_state

        if angle < self.config.flexed_angle:
            self.current_state = "down"
        elif angle > self.config.extended_angle:
            # Count only on the down -> up transition to avoid double counting.
            if self.current_state == "down":
                self.rep_count += 1
            self.current_state = "up"

        return self.rep_count
