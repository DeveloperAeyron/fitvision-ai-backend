import cv2
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pose.detector import PersonDetector
from pose.landmark import PoseLandmarker
from pose.skeleton import landmarks_to_dict
from rep_counter.counter import RepCounter
from video.annotator import annotate_frame

def main():
    exercise_name = "lunge"
    video_path = os.path.normpath("raw_videos/lunge.mp4")
    if not os.path.exists(video_path):
        print(f"Error: {video_path} does not exist.")
        return

    print(f"Loading MediaPipe models and KNN {exercise_name} classifier...")
    detector = PersonDetector("weights/pose_person_detector_f16.tflite")
    landmarker = PoseLandmarker("weights/pose_landmark_detector_full_f16_inf.tflite")
    counter = RepCounter(exercise=exercise_name)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Failed to open video: {video_path}")
        return

    # Setup video writer
    fps = int(cap.get(cv2.CAP_PROP_FPS) or 30)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out_path = f"{exercise_name}_output_11.mp4"
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(out_path, fourcc, fps, (w, h))

    print(f"Processing video... Press 'q' to stop early. Output will be saved to {out_path}")
    roi = None
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
            
        # Detect person and extract landmarks
        landmarks = landmarker.estimate(frame, roi) if roi else None
        if landmarks is None:
            roi = detector.detect(frame)
            landmarks = landmarker.estimate(frame, roi) if roi else None
            
        rep_count = counter.rep_count
        if landmarks is not None:
            landmarks_dict = landmarks_to_dict(landmarks)
            rep_count = counter.update(landmarks_dict, h)
            roi = detector.detect(frame)
            
        annotated = annotate_frame(frame.copy(), landmarks, rep_count, exercise_name.capitalize(), counter.last_angle)
        
        out.write(annotated)
        cv2.imshow(f"{exercise_name.capitalize()} Test (KNN + MediaPipe)", annotated)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    out.release()
    cv2.destroyAllWindows()
    print(f"Done! Saved annotated video to {out_path}")

if __name__ == "__main__":
    main()
