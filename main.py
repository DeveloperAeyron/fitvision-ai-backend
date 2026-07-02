import io
import numpy as np
import cv2
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from ultralytics import YOLO
from ultralytics.utils import ThreadingLocked
from pydantic import BaseModel

app = FastAPI(title="VDS Gym Core API Engine", version="1.0.0")

# Enable global cross-origin resource requests from your mobile app frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared memory lock prevents concurrent threads from corrupting the GPU context
lock = ThreadingLocked()

@app.on_event("startup")
def load_models():
    """Initializes the master weights safely on server startup."""
    global model
    # Path to the best.pt asset downloaded from your Kaggle build
    model_path = "weights/best.pt"
    if not os.path.exists(model_path):
        # Fallback to base model if directory mapping is missing
        model = YOLO("yolo26m.pt")
    else:
        model = YOLO(model_path)
    print("🧠 Master Gym Engine Loaded Successfully!")

@lock
def execute_inference(img_matrix):
    """Executes thread-safe computer vision classification tasks."""
    results = model.predict(source=img_matrix, imgsz=640, verbose=False)
    return results[0]

@app.post("/api/v1/anchor-scene")
async def anchor_scene(file: UploadFile = File(...)):
    """
    Stage 1 API Endpoint:
    Receives an image payload from the mobile client, decodes it, 
    and returns identified machine classes to anchor the activity context.
    """
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Invalid media file format type.")
        
    try:
        # Read file stream safely into bytes
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            raise HTTPException(status_code=400, detail="Failed to decode image payload.")

        # Run the thread-safe image through the model layers
        prediction = execute_inference(frame)
        
        detections = []
        # Loop over generated bounding boxes and format JSON output structure
        for box in prediction.boxes:
            class_id = int(box.cls[0])
            class_name = prediction.names[class_id]
            confidence = float(box.conf[0])
            
            detections.append({
                "class_name": class_name,
                "class_id": class_id,
                "confidence": round(confidence, 4),
                "bbox": [round(float(coord), 2) for coord in box.xyxy[0]]
            })
            
        return {
            "status": "success",
            "detected_anchors_count": len(detections),
            "detections": detections
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference Server Error: {str(e)}")

@app.get("/api/v1/health")
def health_check():
    return {"status": "healthy", "engine": "YOLO26m-59Class"}