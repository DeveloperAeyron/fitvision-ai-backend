from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_detector: "EquipmentDetector | None" = None


def default_equipment_model_path() -> Path:
    try:
        from app.config import settings
        return Path(settings.equipment_model_path)
    except ImportError:
        return Path(__file__).resolve().parent.parent.parent / "weights" / "Equipment-detection.pt"


@dataclass
class EquipmentDetection:
    label: str
    confidence: float
    box: tuple[float, float, float, float]  # x1, y1, x2, y2 (pixels)


class EquipmentDetector:
    """YOLO-based gym equipment detector."""

    def __init__(self, model_path: Path | None = None, conf: float = 0.25):
        self.model_path = Path(model_path) if model_path else default_equipment_model_path()
        self.conf = conf
        self._model = None
        self._load()

    def _load(self) -> None:
        if not self.model_path.exists():
            logger.warning("Equipment model not found at %s", self.model_path)
            return
        try:
            from ultralytics import YOLO

            self._model = YOLO(str(self.model_path))
            logger.info("Loaded equipment detector from %s", self.model_path)
        except ImportError:
            logger.warning("ultralytics not installed — equipment detection disabled")
        except Exception as exc:
            logger.error("Failed to load equipment model: %s", exc)

    @property
    def ready(self) -> bool:
        return self._model is not None

    @property
    def class_names(self) -> dict[int, str]:
        if self._model is None:
            return {}
        return dict(self._model.names)

    def detect(self, image: np.ndarray) -> list[EquipmentDetection]:
        if self._model is None:
            return []

        results = self._model(image, conf=self.conf, verbose=False)
        detections: list[EquipmentDetection] = []

        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            names = result.names
            for box in boxes:
                cls_id = int(box.cls[0])
                label = names.get(cls_id, str(cls_id))
                # Skip junk/placeholder classes from training artifacts.
                if label.isdigit() or label.lower() in {"0", "1", "json"}:
                    continue
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append(
                    EquipmentDetection(
                        label=label,
                        confidence=float(box.conf[0]),
                        box=(x1, y1, x2, y2),
                    )
                )

        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections

    def detect_unique_labels(self, image: np.ndarray) -> list[str]:
        seen: set[str] = set()
        labels: list[str] = []
        for det in self.detect(image):
            key = det.label.strip()
            if key and key not in seen:
                seen.add(key)
                labels.append(key)
        return labels

    def to_dict(self, detection: EquipmentDetection) -> dict[str, Any]:
        return {
            "label": detection.label,
            "confidence": round(detection.confidence, 4),
            "box": [round(v, 1) for v in detection.box],
        }


def get_equipment_detector(model_path: Path | None = None) -> EquipmentDetector:
    global _detector
    path = Path(model_path) if model_path else default_equipment_model_path()
    if _detector is None or _detector.model_path != path:
        _detector = EquipmentDetector(path)
    return _detector
