import os
import pickle
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
        self.pred_history: List[str] = []
        self.frames_since_last_rep = 99

        # Load ML pose classifier model if it exists
        self.model_loaded = False
        model_name = f"pose_classifier_{self.config.name}.pkl"
        model_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "weights", model_name)
        if os.path.exists(model_path):
            try:
                with open(model_path, "rb") as f:
                    data = pickle.load(f)
                    self.clf = data["model"]
                    self.clf_type = data["model_type"]
                    self.clf_classes = data["classes"]
                    self.clf_features = data.get("features", ["left_elbow", "right_elbow", "left_knee", "right_knee", "left_hip", "right_hip", "bbox_ratio"])
                    self.model_loaded = True
                    print(f"Loaded {self.clf_type} pose classifier successfully for '{self.config.name}' from {model_path}!")
            except Exception as e:
                print(f"Failed to load pose classifier for '{self.config.name}', falling back to heuristics:", e)

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
        # Get all visible key body landmarks (excluding face to prevent facial jitter from affecting bbox)
        important_landmarks = [
            "left_shoulder", "right_shoulder",
            "left_elbow", "right_elbow",
            "left_wrist", "right_wrist",
            "left_hip", "right_hip",
            "left_knee", "right_knee",
            "left_ankle", "right_ankle"
        ]
        xs = []
        ys = []
        for key in important_landmarks:
            if key in landmarks and landmarks[key][2] >= self.visibility_threshold:
                xs.append(landmarks[key][0])
                ys.append(landmarks[key][1])

        if not xs or not ys:
            return False

        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        bbox_ratio = height / (width + 1e-5)

        # Calculate average shoulder and hip vertical positions (y-coordinates)
        sh_y_list = [landmarks[k][1] for k in ("left_shoulder", "right_shoulder") if k in landmarks and landmarks[k][2] >= self.visibility_threshold]
        hip_y_list = [landmarks[k][1] for k in ("left_hip", "right_hip") if k in landmarks and landmarks[k][2] >= self.visibility_threshold]
        sh_y = sum(sh_y_list) / len(sh_y_list) if sh_y_list else 0.0
        hip_y = sum(hip_y_list) / len(hip_y_list) if hip_y_list else 0.0

        if self.config.name == "squat":
            # Squats require vertical body aspect ratio (bbox_ratio >= 1.3)
            # and shoulders to be vertically above hips (sh_y < hip_y in screen coordinates)
            # This completely blocks head-on/rear-on push-ups from registering as squats
            if bbox_ratio < 1.3:
                return False
            if sh_y_list and hip_y_list and sh_y > hip_y:
                return False

        elif self.config.name == "pushup":
            # Pushups require horizontal/semi-horizontal body orientation (bbox_ratio <= 1.5)
            # Both side-profile and head-on pushups (especially with straight arms) fall within this range
            if bbox_ratio > 1.5:
                return False

            # Verify that hips are not deeply bent (e.g. sit-up position)
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
            # Situps require a horizontal or semi-seated aspect ratio (bbox_ratio <= 1.5)
            if bbox_ratio > 1.5:
                return False

        return True

    def _extract_features(self, landmarks: Dict[str, Tuple[float, float, float]]) -> List[float]:
        # Extract features matching the 7 feature columns of train_classifier.py
        left_elbow = calculate_angle(landmarks["left_shoulder"], landmarks["left_elbow"], landmarks["left_wrist"]) if "left_shoulder" in landmarks and "left_elbow" in landmarks and "left_wrist" in landmarks else 180.0
        right_elbow = calculate_angle(landmarks["right_shoulder"], landmarks["right_elbow"], landmarks["right_wrist"]) if "right_shoulder" in landmarks and "right_elbow" in landmarks and "right_wrist" in landmarks else 180.0

        left_knee = calculate_angle(landmarks["left_hip"], landmarks["left_knee"], landmarks["left_ankle"]) if "left_hip" in landmarks and "left_knee" in landmarks and "left_ankle" in landmarks else 180.0
        right_knee = calculate_angle(landmarks["right_hip"], landmarks["right_knee"], landmarks["right_ankle"]) if "right_hip" in landmarks and "right_knee" in landmarks and "right_ankle" in landmarks else 180.0

        left_hip = calculate_angle(landmarks["left_shoulder"], landmarks["left_hip"], landmarks["left_knee"]) if "left_shoulder" in landmarks and "left_hip" in landmarks and "left_knee" in landmarks else 180.0
        right_hip = calculate_angle(landmarks["right_shoulder"], landmarks["right_hip"], landmarks["right_knee"]) if "right_shoulder" in landmarks and "right_hip" in landmarks and "right_knee" in landmarks else 180.0

        # Bounding box aspect ratio
        important_landmarks = [
            "left_shoulder", "right_shoulder",
            "left_elbow", "right_elbow",
            "left_wrist", "right_wrist",
            "left_hip", "right_hip",
            "left_knee", "right_knee",
            "left_ankle", "right_ankle"
        ]
        xs = []
        ys = []
        for key in important_landmarks:
            if key in landmarks and landmarks[key][2] >= self.visibility_threshold:
                xs.append(landmarks[key][0])
                ys.append(landmarks[key][1])
        if not xs or not ys:
            bbox_ratio = 1.0
        else:
            width = max(xs) - min(xs)
            height = max(ys) - min(ys)
            bbox_ratio = height / (width + 1e-5)

        all_feats = {
            "left_elbow": left_elbow,
            "right_elbow": right_elbow,
            "left_knee": left_knee,
            "right_knee": right_knee,
            "left_hip": left_hip,
            "right_hip": right_hip,
            "bbox_ratio": bbox_ratio
        }

        return [all_feats[f] for f in self.clf_features]

    def update(self, landmarks: Dict[str, Tuple[float, float, float]],
               frame_height: Optional[int] = None) -> int:
        if not self._is_pose_valid(landmarks):
            return self.rep_count

        if self.model_loaded:
            try:
                features = self._extract_features(landmarks)
                
                # Silence sklearn UserWarning about feature names
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", category=UserWarning)
                    pred = self.clf.predict([features])[0]

                # 1. Rolling window of predictions (size 5) to smooth out frame jitters
                self.pred_history.append(pred)
                if len(self.pred_history) > 5:
                    self.pred_history.pop(0)

                # Take majority vote (mode)
                from collections import Counter
                smoothed_pred = Counter(self.pred_history).most_common(1)[0][0]

                self.frames_since_last_rep += 1

                # The classifier output states are direct: 'up', 'down', 'transition'
                if smoothed_pred == "down":
                    self.current_state = "down"
                elif smoothed_pred == "up" and self.current_state == "down":
                    # Enforce a minimum cooldown of 15 frames (~0.5s at 30fps) between counted reps
                    if self.frames_since_last_rep >= 15:
                        self.rep_count += 1
                        self.frames_since_last_rep = 0
                    self.current_state = "up"

                # Keep last_angle updated for UI annotations
                raw = self._measure(landmarks, frame_height)
                if raw is not None:
                    self.last_angle = self._smooth(raw)

                self.previous_state = self.current_state
                return self.rep_count
            except Exception as e:
                print("Model prediction error, falling back to heuristics:", e)

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
