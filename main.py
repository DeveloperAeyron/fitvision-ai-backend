import os
import io
import cv2
import numpy as np
import mediapipe as mp
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="FitVision Rep Counter Server", version="1.5.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize standard MediaPipe drawing utils for the video annotations
mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose

# Make sure temporary directories exist for staging video files
UPLOAD_DIR = "/kaggle/working/uploads" if 'KAGGLR_URL' in os.environ else "uploads"
OUTPUT_DIR = "/kaggle/working/outputs" if 'KAGGLR_URL' in os.environ else "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def calculate_angle(a, b, c):
    """Calculates the interior flexion angle at pivot joint 'b'."""
    a = np.array(a)
    b = np.array(b)
    c = np.array(c)
    
    radians = np.arctan2(c[1] - b[1], c[0] - b[0]) - np.arctan2(a[1] - b[1], a[0] - b[0])
    angle = np.abs(radians * 180.0 / np.pi)
    
    if angle > 180.0:
        angle = 360.0 - angle
    return angle

@app.post("/api/v1/process-workout")
async def process_workout(file: UploadFile = File(...)):
    """
    Video Processing Endpoint:
    Accepts an incoming video file, loops over every frame to calculate 
    the active exercise angles, writes the rep counts live onto the frame,
    and returns a rendered video file payload back to the client.
    """
    if not file.filename.lower().endswith(('.mp4', '.mov', '.avi')):
        raise HTTPException(status_code=400, detail="Invalid video format profile.")

    input_path = os.path.join(UPLOAD_DIR, file.filename)
    output_path = os.path.join(OUTPUT_DIR, f"annotated_{file.filename}")

    # Save incoming upload bytes safely onto local disk storage
    try:
        contents = await file.read()
        with open(input_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stage upload asset: {str(e)}")

    # Initialize video capture pointers
    cap = cv2.VideoCapture(input_path)
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps    = cap.get(cv2.CAP_PROP_FPS) if cap.get(cv2.CAP_PROP_FPS) > 0 else 30

    # Configure VideoWriter using standard MP4V container codec matching mobile profiles
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    # Repetition Counter State Machine variables
    rep_counter = 0
    stage = "up"  # Initial assume state tracking

    # Spin up the underlying MediaPipe Pose Engine instance
    with mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5) as pose:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            # Convert BGR frames safely into standard MediaPipe RGB alignment matrix
            image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image_rgb.flags.writeable = False
            
            # Execute pose estimation inference vectors
            results = pose.process(image_rgb)
            
            image_rgb.flags.writeable = True
            # Revert color spaces back seamlessly for final OpenCV encoding exports
            frame = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)

            try:
                if results.pose_landmarks:
                    landmarks = results.pose_landmarks.landmark
                    
                    # Target Left Side joint indices: 11 = Shoulder, 13 = Elbow, 15 = Wrist
                    shoulder = [landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value].x,
                                landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value].y]
                    elbow = [landmarks[mp_pose.PoseLandmark.LEFT_ELBOW.value].x,
                             landmarks[mp_pose.PoseLandmark.LEFT_ELBOW.value].y]
                    wrist = [landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value].x,
                             landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value].y]

                    # Map raw joints into mathematical degree variables
                    elbow_angle = calculate_angle(shoulder, elbow, wrist)

                    # --- DETAILED PUSHUP STATE ENGINE ---
                    # 1. User flexes deeply past lower boundary limit
                    if elbow_angle < 90:
                        stage = "down"
                    # 2. User pushes fully back up to initial extension limit while inside 'down' loop context
                    if elbow_angle > 160 and stage == "down":
                        stage = "up"
                        rep_counter += 1

                    # Draw the tracking metrics live onto the current processing frame
                    cv2.putText(frame, f"Angle: {int(elbow_angle)}", 
                                (int(elbow[0]*width), int(elbow[1]*height) - 10), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                    # Superimpose the skeleton connections overlay
                    mp_drawing.draw_landmarks(
                        frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS,
                        mp_drawing.DrawingSpec(color=(245,117,66), thickness=2, circle_radius=2), 
                        mp_drawing.DrawingSpec(color=(245,66,230), thickness=2, circle_radius=2)
                    )
            except Exception as joint_err:
                pass # Gracefully skip frame if visual occlusions temporarily break coordinate arrays

            # Render global counter metrics box on the top left corner layer
            cv2.rectangle(frame, (10, 10), (250, 80), (0, 0, 0), -1)
            cv2.putText(frame, f"REPS: {rep_counter}", (20, 55), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)

            # Write out the processed frame layout array into file container storage
            out.write(frame)

    cap.release()
    out.release()

    # Stream the completely annotated video asset directly back to Waleed's mobile client app
    return FileResponse(output_path, media_type="video/mp4", filename=f"processed_{file.filename}")