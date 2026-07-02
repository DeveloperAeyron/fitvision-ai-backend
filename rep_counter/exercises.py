from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


# An exercise is defined by joint triplets (middle joint = vertex) whose angle
# flexes and extends once per rep. The counter tracks that angle's range of
# motion adaptively, so a new exercise only needs its triplets and a minimum
# ROM below which motion is treated as noise.
@dataclass(frozen=True)
class ExerciseConfig:
    name: str
    triplets: List[Tuple[str, str, str]]
    min_range: float = 30.0


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
        min_range=35.0,
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
