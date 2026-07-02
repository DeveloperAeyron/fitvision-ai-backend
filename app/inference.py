import os
import torch
from ultralytics import YOLO

class GymInferenceEngine:
    def __init__(self, weights_path="weights/best.pt"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        if os.path.exists(weights_path):
            self.model = YOLO(weights_path)
        else:
            self.model = YOLO("yolo26m.pt")
        self.model.to(self.device)

    def predict_scene(self, frame):
        """Processes an image array and returns bounding box configurations."""
        results = self.model.predict(source=frame, imgsz=640, verbose=False)
        return results[0]