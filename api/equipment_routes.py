from __future__ import annotations

import base64
import binascii
import logging
import tempfile
import os

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from cv.equipment import get_equipment_detector

logger = logging.getLogger(__name__)

router = APIRouter(tags=["equipment"])


class DetectEquipmentRequest(BaseModel):
    image: str = Field(description="Base64-encoded image (JPEG/PNG)")


class EquipmentDetectionItem(BaseModel):
    label: str
    confidence: float
    box: list[float]


class DetectEquipmentResponse(BaseModel):
    detections: list[EquipmentDetectionItem]
    labels: list[str]


def _decode_image(payload: str) -> np.ndarray:
    try:
        image_bytes = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "Invalid base64 image payload.")
    if not image_bytes:
        raise HTTPException(400, "Empty image payload.")

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(400, "Could not decode image.")
    return image


@router.post("/detect-equipment", response_model=DetectEquipmentResponse)
def detect_equipment(request: DetectEquipmentRequest) -> DetectEquipmentResponse:
    detector = get_equipment_detector()
    if not detector.ready:
        raise HTTPException(503, "Equipment detection model is not available.")

    image = _decode_image(request.image)
    detections = detector.detect(image)
    items = [
        EquipmentDetectionItem(**detector.to_dict(det))
        for det in detections
    ]
    labels = detector.detect_unique_labels(image)

    logger.info("detect-equipment found %d objects, %d unique labels", len(items), len(labels))
    return DetectEquipmentResponse(detections=items, labels=labels)


class DetectEquipmentVideoRequest(BaseModel):
    video: str = Field(description="Base64-encoded video (mp4)")
    sample_every: int = Field(default=30, ge=1, le=300, description="Sample every N frames")


@router.post("/detect-equipment-video", response_model=DetectEquipmentResponse)
def detect_equipment_video(request: DetectEquipmentVideoRequest) -> DetectEquipmentResponse:
    detector = get_equipment_detector()
    if not detector.ready:
        raise HTTPException(503, "Equipment detection model is not available.")

    try:
        video_bytes = base64.b64decode(request.video, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "Invalid base64 video payload.")
    if not video_bytes:
        raise HTTPException(400, "Empty video payload.")

    in_fd, in_path = tempfile.mkstemp(suffix=".mp4")
    os.close(in_fd)

    merged: dict[str, EquipmentDetectionItem] = {}
    try:
        with open(in_path, "wb") as f:
            f.write(video_bytes)

        cap = cv2.VideoCapture(in_path)
        if not cap.isOpened():
            raise HTTPException(400, "Could not open video.")

        frame_idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_idx % request.sample_every == 0:
                for det in detector.detect(frame):
                    existing = merged.get(det.label)
                    item = EquipmentDetectionItem(**detector.to_dict(det))
                    if existing is None or item.confidence > existing.confidence:
                        merged[det.label] = item
            frame_idx += 1
        cap.release()
    finally:
        if os.path.exists(in_path):
            os.remove(in_path)

    items = sorted(merged.values(), key=lambda d: d.confidence, reverse=True)
    labels = [item.label for item in items]
    return DetectEquipmentResponse(detections=items, labels=labels)
