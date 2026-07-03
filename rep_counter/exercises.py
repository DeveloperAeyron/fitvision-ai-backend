from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional, Tuple

Metric = Literal["angle", "hip_drop"]
Flexion = Literal["decreasing", "increasing"]


# An exercise is defined by joint triplets (middle joint = vertex) whose angle
# flexes and extends once per rep, or by an alternate metric such as hip_drop
# for front-facing squats where knee angles are often unreliable in 2D.
@dataclass(frozen=True)
class ExerciseConfig:
    name: str
    triplets: List[Tuple[str, str, str]]
    metric: Metric = "angle"
    flexion: Flexion = "decreasing"
    min_range: float = 30.0
    enter_frac: float = 0.30
    exit_frac: float = 0.30
    average_sides: bool = True
    smooth_window: int = 5
    min_valid: Optional[float] = 50.0
    max_valid: Optional[float] = 175.0


EXERCISES = {
    "pushup": ExerciseConfig(
        name="pushup",
        triplets=[
            ("left_shoulder", "left_elbow", "left_wrist"),
            ("right_shoulder", "right_elbow", "right_wrist"),
        ],
        min_range=30.0,
    ),
    "squat": ExerciseConfig(
        name="squat",
        triplets=[
            ("left_hip", "left_knee", "left_ankle"),
            ("right_hip", "right_knee", "right_ankle"),
        ],
        # Front/side squats: hip vertical drop tracks depth better than knee
        # angle when legs are occluded or seen head-on.
        metric="hip_drop",
        flexion="increasing",
        min_range=0.04,
        enter_frac=0.30,
        exit_frac=0.30,
        smooth_window=7,
        min_valid=None,
        max_valid=None,
    ),
    "situp": ExerciseConfig(
        name="situp",
        triplets=[
            ("left_shoulder", "left_hip", "left_knee"),
            ("right_shoulder", "right_hip", "right_knee"),
        ],
        min_range=30.0,
    ),
}


def get_exercise(name: str) -> ExerciseConfig:
    key = name.lower().strip()
    if key not in EXERCISES:
        raise ValueError(f"Unknown exercise '{name}'. Supported: {sorted(EXERCISES)}")
    return EXERCISES[key]
