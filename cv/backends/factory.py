from __future__ import annotations

from functools import lru_cache
from typing import Callable

from cv.backends.base import PoseBackend
from cv.backends.mediapipe import MediaPipePoseBackend
from cv.backends.tflite import TflitePoseBackend

BackendFactory = Callable[[], PoseBackend]

_REGISTRY: dict[str, BackendFactory] = {
    "tflite": TflitePoseBackend,
    "mediapipe": MediaPipePoseBackend,
}


def list_backends() -> list[str]:
    return sorted(_REGISTRY)


@lru_cache(maxsize=None)
def get_backend(name: str) -> PoseBackend:
    """Return a cached backend instance (models load once per process)."""
    factory = _REGISTRY.get(name)
    if factory is None:
        raise KeyError(
            f"Unknown backend {name!r}. Available: {', '.join(list_backends())}"
        )
    return factory()
