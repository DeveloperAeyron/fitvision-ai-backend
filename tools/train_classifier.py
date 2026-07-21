import pandas as pd
import numpy as np
import pickle
import os
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
from sklearn.metrics import classification_report, accuracy_score

EXERCISE_FEATURES = {
    "pushup": ["left_elbow", "right_elbow", "bbox_ratio"],
    "squat": ["left_knee", "right_knee", "left_hip", "right_hip", "bbox_ratio"],
    "situp": ["left_hip", "right_hip", "bbox_ratio"],
    "pullup": ["left_elbow", "right_elbow", "bbox_ratio"],
    "jumping_jack": ["left_shoulder_abd", "right_shoulder_abd", "left_knee", "right_knee", "bbox_ratio"],
}

def main():
    csv_file = "pose_features.csv"
    if not os.path.exists(csv_file):
        print(f"Error: CSV file '{csv_file}' not found. Please run collect_pose_data.py first.")
        return

    print(f"Loading dataset from '{csv_file}'...")
    df = pd.read_csv(csv_file)
    df = df.dropna()

    os.makedirs("weights", exist_ok=True)

    unique_exercises = df["exercise_label"].unique()
    for exercise in unique_exercises:
        print(f"\n==================================================")
        print(f"Training Classifier for Exercise: '{exercise}'")
        print(f"==================================================")

        df_ex = df[df["exercise_label"] == exercise]

        # Use exercise-specific feature subset
        features_list = EXERCISE_FEATURES.get(exercise, ["left_elbow", "right_elbow", "left_knee", "right_knee", "left_hip", "right_hip", "bbox_ratio"])
        X = df_ex[features_list]
        y = df_ex["state_label"]

        if len(y.unique()) < 2:
            print(f"Skipping {exercise} because it has less than 2 classes in this dataset: {y.unique()}")
            continue

        # Split data into train and test sets (using stratify to ensure class balance)
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

        print(f"Training sample size: {len(X_train)} frames, Test sample size: {len(X_test)} frames")
        print("Unique states to learn:", sorted(y.unique()))

        # 1. Train KNN Classifier
        print(f"\n--- Training KNN for {exercise} ---")
        knn = KNeighborsClassifier(n_neighbors=5)
        knn.fit(X_train, y_train)
        knn_preds = knn.predict(X_test)
        knn_acc = accuracy_score(y_test, knn_preds)
        print(f"KNN Accuracy: {knn_acc:.4f}")
        print(classification_report(y_test, knn_preds))

        # 2. Train SVM Classifier
        print(f"\n--- Training SVM for {exercise} ---")
        svm = SVC(kernel="rbf", C=1.0, probability=True, random_state=42)
        svm.fit(X_train, y_train)
        svm_preds = svm.predict(X_test)
        svm_acc = accuracy_score(y_test, svm_preds)
        print(f"SVM Accuracy: {svm_acc:.4f}")
        print(classification_report(y_test, svm_preds))

        # Force save the KNN model as requested
        best_model = knn
        model_type = "KNN"

        model_path = f"weights/pose_classifier_{exercise}.pkl"
        print(f"\nSaving the model ({model_type}) to '{model_path}'...")

        with open(model_path, "wb") as f:
            pickle.dump({
                "model": best_model,
                "model_type": model_type,
                "features": features_list,
                "classes": list(best_model.classes_)
            }, f)

        print(f"Model training and export successful for '{exercise}'!")

if __name__ == "__main__":
    main()
