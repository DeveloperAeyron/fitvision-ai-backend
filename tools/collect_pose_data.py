import os
import sys
# Add workspace root to sys.path so we can import pose and rep_counter modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import csv
import cv2
import numpy as np
from pose.detector import PersonDetector
from pose.landmark import PoseLandmarker
from pose.skeleton import landmarks_to_dict
from rep_counter.angles import calculate_angle

PERSON_DETECTOR_PATH = "weights/pose_person_detector_f16.tflite"
LANDMARK_MODEL_PATH = "weights/pose_landmark_detector_full_f16_inf.tflite"

def calculate_bbox_ratio(landmarks):
    important_landmarks = [
        "left_shoulder", "right_shoulder",
        "left_elbow", "right_elbow",
        "left_wrist", "right_wrist",
        "left_hip", "right_hip",
        "left_knee", "right_knee",
        "left_ankle", "right_ankle"
    ]
    xs = []
    ys = []
    for key in important_landmarks:
        if key in landmarks and landmarks[key][2] >= 0.3:
            xs.append(landmarks[key][0])
            ys.append(landmarks[key][1])
    if not xs or not ys:
        return 1.0
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    return height / (width + 1e-5)

def extract_features(landmarks):
    # Calculate critical angles
    # Elbow angles
    left_elbow = calculate_angle(landmarks["left_shoulder"], landmarks["left_elbow"], landmarks["left_wrist"]) if "left_shoulder" in landmarks and "left_elbow" in landmarks and "left_wrist" in landmarks else 180.0
    right_elbow = calculate_angle(landmarks["right_shoulder"], landmarks["right_elbow"], landmarks["right_wrist"]) if "right_shoulder" in landmarks and "right_elbow" in landmarks and "right_wrist" in landmarks else 180.0

    # Knee angles
    left_knee = calculate_angle(landmarks["left_hip"], landmarks["left_knee"], landmarks["left_ankle"]) if "left_hip" in landmarks and "left_knee" in landmarks and "left_ankle" in landmarks else 180.0
    right_knee = calculate_angle(landmarks["right_hip"], landmarks["right_knee"], landmarks["right_ankle"]) if "right_hip" in landmarks and "right_knee" in landmarks and "right_ankle" in landmarks else 180.0

    # Hip angles
    left_hip = calculate_angle(landmarks["left_shoulder"], landmarks["left_hip"], landmarks["left_knee"]) if "left_shoulder" in landmarks and "left_hip" in landmarks and "left_knee" in landmarks else 180.0
    right_hip = calculate_angle(landmarks["right_shoulder"], landmarks["right_hip"], landmarks["right_knee"]) if "right_shoulder" in landmarks and "right_hip" in landmarks and "right_knee" in landmarks else 180.0

    bbox_ratio = calculate_bbox_ratio(landmarks)

    return [
        left_elbow, right_elbow,
        left_knee, right_knee,
        left_hip, right_hip,
        bbox_ratio
    ]

def main():
    print("Initializing pose detectors...")
    detector = PersonDetector(PERSON_DETECTOR_PATH)
    landmarker = PoseLandmarker(LANDMARK_MODEL_PATH)

    dataset_dir = "raw_videos"
    output_csv = "pose_features.csv"

    fieldnames = [
        "left_elbow", "right_elbow",
        "left_knee", "right_knee",
        "left_hip", "right_hip",
        "bbox_ratio",
        "exercise_label", "state_label"
    ]

    with open(output_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(fieldnames)

        exercises = ["pushup", "squat", "situp"]
        for exercise in exercises:
            folder_path = os.path.join(dataset_dir, exercise)
            if not os.path.exists(folder_path):
                continue

            video_files = [v for v in os.listdir(folder_path) if v.endswith((".mp4", ".avi", ".mov", ".3gp"))]
            if not video_files:
                print(f"No videos found in {folder_path}. Skip.")
                continue

            print(f"Processing '{exercise}' videos...")
            for video_file in video_files:
                video_path = os.path.join(folder_path, video_file)
                print(f"  Reading {video_file}...")
                cap = cv2.VideoCapture(video_path)
                if not cap.isOpened():
                    print(f"  Error opening {video_file}")
                    continue

                roi = None
                while True:
                    ok, frame = cap.read()
                    if not ok:
                          break

                    # Detect and estimate
                    landmarks = landmarker.estimate(frame, roi) if roi else None
                    if landmarks is None:
                        roi = detector.detect(frame)
                        landmarks = landmarker.estimate(frame, roi) if roi else None

                    if landmarks is not None:
                        landmarks_dict = landmarks_to_dict(landmarks)
                        # Extract joint angles & bbox ratio
                        features = extract_features(landmarks_dict)

                        # Auto-label based on joint angles
                        left_el, right_el, left_kn, right_kn, left_hp, right_hp, bbox_ratio = features
                        state_label = "transition"

                        # Simple rule-based labeling bootstrap
                        if exercise == "pushup":
                            avg_elbow = (left_el + right_el) / 2.0
                            if avg_elbow > 140.0:
                                state_label = "up"
                            elif avg_elbow < 115.0:
                                state_label = "down"
                        elif exercise == "squat":
                            avg_knee = (left_kn + right_kn) / 2.0
                            if avg_knee > 145.0:
                                state_label = "up"
                            elif avg_knee < 115.0:
                                state_label = "down"
                        elif exercise == "situp":
                            avg_hip = (left_hp + right_hp) / 2.0
                            if avg_hip > 140.0:
                                state_label = "up"
                              # Situps require flexion (e.g. angle around 60-90)
                            elif avg_hip < 100.0:
                                state_label = "down"

                        writer.writerow(features + [exercise, state_label])
                        roi = detector.detect(frame) # Keep track dynamically
                    else:
                        roi = None
                cap.release()
    print(f"Data collection completed! Labeled features exported to '{output_csv}'")

if __name__ == "__main__":
    main()
