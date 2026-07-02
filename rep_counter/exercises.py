from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

# Each exercise is defined by joint triplets whose middle joint is the vertex.
# A rep = the tracked angle drops below `flexed_angle` (DOWN) and then rises
# above `extended_angle` (UP). Left/right triplets let us pick the more
# visible side. Adding a new exercise means adding an ExerciseConfig here only.


@dataclass(frozen=True)
class ExerciseConfig:
    name: str
    triplets: List[Tuple[str, str, str]]
    flexed_angle: float
    extended_angle: float
    start_state: str = "up"


EXERCISES = {
    "pushup": ExerciseConfig(
        name="pushup",
        triplets=[
            ("left_shoulder", "left_elbow", "left_wrist"),
            ("right_shoulder", "right_elbow", "right_wrist"),
        ],
        flexed_angle=90.0,
        extended_angle=160.0,
    ),
    "squat": ExerciseConfig(
        name="squat",
        triplets=[
            ("left_hip", "left_knee", "left_ankle"),
            ("right_hip", "right_knee", "right_ankle"),
        ],
        flexed_angle=90.0,
        extended_angle=160.0,
    ),
    "situp": ExerciseConfig(
        name="situp",
        triplets=[
            ("left_shoulder", "left_hip", "left_knee"),
            ("right_shoulder", "right_hip", "right_knee"),
        ],
        flexed_angle=70.0,
        extended_angle=140.0,
    ),
}


def get_exercise(name: str) -> ExerciseConfig:
    key = name.lower().strip()
    if key not in EXERCISES:
        raise ValueError(
            f"Unknown exercise '{name}'. Supported: {sorted(EXERCISES)}"
        )
    return EXERCISES[key]
