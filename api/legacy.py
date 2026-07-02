from __future__ import annotations

import json
import os

import cv2
import mediapipe as mp
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

router = APIRouter(tags=["legacy"])

mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
DB_FILE = "users_db.json"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
if not os.path.exists(DB_FILE):
    with open(DB_FILE, "w") as f:
        json.dump({}, f)


def load_users():
    with open(DB_FILE, "r") as f:
        return json.load(f)


def save_users(users):
    with open(DB_FILE, "w") as f:
        json.dump(users, f, indent=4)


def calculate_angle(a, b, c):
    a, b, c = np.array(a), np.array(b), np.array(c)
    radians = np.arctan2(c[1] - b[1], c[0] - b[0]) - np.arctan2(a[1] - b[1], a[0] - b[0])
    angle = np.abs(radians * 180.0 / np.pi)
    return 360.0 - angle if angle > 180.0 else angle


@router.post("/signup")
async def signup(username: str = Form(...), password: str = Form(...)):
    users = load_users()
    if username in users:
        raise HTTPException(status_code=400, detail="Username already exists.")
    users[username] = {"password": password}
    save_users(users)
    return {"status": "success", "message": "User registered successfully!"}


@router.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    users = load_users()
    if username not in users or users[username]["password"] != password:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return {"status": "success", "message": "Login successful!"}


@router.post("/detection")
async def detection(file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".mp4", ".mov", ".avi")):
        raise HTTPException(status_code=400, detail="Invalid video format profile.")

    input_path = os.path.join(UPLOAD_DIR, file.filename)
    output_path = os.path.join(OUTPUT_DIR, f"annotated_{file.filename}")

    contents = await file.read()
    with open(input_path, "wb") as f:
        f.write(contents)

    cap = cv2.VideoCapture(input_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    rep_counter = 0
    stage = "up"

    with mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5) as pose:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(image_rgb)
            frame = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)

            if results.pose_landmarks:
                landmarks = results.pose_landmarks.landmark
                shoulder = [landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value].x,
                            landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value].y]
                elbow = [landmarks[mp_pose.PoseLandmark.LEFT_ELBOW.value].x,
                         landmarks[mp_pose.PoseLandmark.LEFT_ELBOW.value].y]
                wrist = [landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value].x,
                         landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value].y]

                angle = calculate_angle(shoulder, elbow, wrist)
                if angle < 90:
                    stage = "down"
                if angle > 160 and stage == "down":
                    stage = "up"
                    rep_counter += 1

                mp_drawing.draw_landmarks(frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)

            cv2.rectangle(frame, (10, 10), (250, 75), (0, 0, 0), -1)
            cv2.putText(frame, f"REPS: {rep_counter}", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
            out.write(frame)

    cap.release()
    out.release()

    return FileResponse(output_path, media_type="video/mp4",
                        filename=f"processed_{file.filename}")
