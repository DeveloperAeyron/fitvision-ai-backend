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
                 envelope_decay: float = 0.02):
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

    def _is_pose_valid(self, landmarks: Dict[str, Tuple[float, float, float]]) -> bool:
        # Check torso orientation using whichever side of the body is more visible (supports side views)
        has_left = ("left_shoulder" in landmarks and "left_hip" in landmarks and
                    landmarks["left_shoulder"][2] >= self.visibility_threshold and
                    landmarks["left_hip"][2] >= self.visibility_threshold)

        has_right = ("right_shoulder" in landmarks and "right_hip" in landmarks and
                     landmarks["right_shoulder"][2] >= self.visibility_threshold and
                     landmarks["right_hip"][2] >= self.visibility_threshold)

        if not (has_left or has_right):
            return False

        if has_left and has_right:
            sh_x = (landmarks["left_shoulder"][0] + landmarks["right_shoulder"][0]) / 2.0
            sh_y = (landmarks["left_shoulder"][1] + landmarks["right_shoulder"][1]) / 2.0
            hip_x = (landmarks["left_hip"][0] + landmarks["right_hip"][0]) / 2.0
            hip_y = (landmarks["left_hip"][1] + landmarks["right_hip"][1]) / 2.0
        elif has_left:
            sh_x, sh_y, _ = landmarks["left_shoulder"]
            hip_x, hip_y, _ = landmarks["left_hip"]
        else:
            sh_x, sh_y, _ = landmarks["right_shoulder"]
            hip_x, hip_y, _ = landmarks["right_hip"]

        dx = abs(sh_x - hip_x)
        dy = abs(sh_y - hip_y)
        ratio = dy / (dx + 1e-5)

        if self.config.name == "squat":
            # Squats require vertical body orientation (dy/dx >= 0.8)
            # Prevent pushups or situps (horizontal body) from counting
            if ratio < 0.8:
                return False

        elif self.config.name == "pushup":
            # Pushups require horizontal body orientation (dy/dx <= 1.0)
            # Prevent standing/sitting exercises from counting
            if ratio > 1.0:
                return False

            # For pushups, verify that hips are not deeply bent (e.g. situp position)
            hip_angles = []
            for side in ("left", "right"):
                sh = f"{side}_shoulder"
                hp = f"{side}_hip"
                kn = f"{side}_knee"
                if (sh in landmarks and hp in landmarks and kn in landmarks and
                    landmarks[sh][2] >= self.visibility_threshold and
                    landmarks[hp][2] >= self.visibility_threshold and
                    landmarks[kn][2] >= self.visibility_threshold):
                    angle = calculate_angle(landmarks[sh], landmarks[hp], landmarks[kn])
                    hip_angles.append(angle)
            if hip_angles:
                avg_hip_angle = sum(hip_angles) / len(hip_angles)
                if avg_hip_angle < 110.0:
                    return False

        elif self.config.name == "situp":
            # Situps start horizontal and rise up, but should not be completely vertical/standing
            if ratio > 2.2:
                return False

        return True

    def update(self, landmarks: Dict[str, Tuple[float, float, float]],
               frame_height: Optional[int] = None) -> int:
        if not self._is_pose_valid(landmarks):
            return self.rep_count

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
