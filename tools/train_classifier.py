import pandas as pd
import numpy as np
import pickle
import os
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
from sklearn.metrics import classification_report, accuracy_score

def main():
    csv_file = "pose_features.csv"
    if not os.path.exists(csv_file):
        print(f"Error: CSV file '{csv_file}' not found. Please run collect_pose_data.py first.")
        return

    print(f"Loading dataset from '{csv_file}'...")
    df = pd.read_csv(csv_file)

    # Create combined target class: e.g., 'pushup_up', 'squat_down'
    df["target"] = df["exercise_label"] + "_" + df["state_label"]

    # Drop rows with NaN if any
    df = df.dropna()

    X = df[["left_elbow", "right_elbow", "left_knee", "right_knee", "left_hip", "right_hip", "bbox_ratio"]]
    y = df["target"]

    # Split data into train and test sets (using stratify to ensure class balance)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    print(f"Training sample size: {len(X_train)} frames, Test sample size: {len(X_test)} frames")
    print("Unique classes to learn:", sorted(y.unique()))

    # 1. Train KNN Classifier
    print("\n--- Training K-Nearest Neighbors (KNN) ---")
    knn = KNeighborsClassifier(n_neighbors=5)
    knn.fit(X_train, y_train)
    knn_preds = knn.predict(X_test)
    knn_acc = accuracy_score(y_test, knn_preds)
    print(f"KNN Accuracy: {knn_acc:.4f}")
    print(classification_report(y_test, knn_preds))

    # 2. Train SVM Classifier
    print("\n--- Training Support Vector Machine (SVM) ---")
    svm = SVC(kernel="rbf", C=1.0, probability=True, random_state=42)
    svm.fit(X_train, y_train)
    svm_preds = svm.predict(X_test)
    svm_acc = accuracy_score(y_test, svm_preds)
    print(f"SVM Accuracy: {svm_acc:.4f}")
    print(classification_report(y_test, svm_preds))

    # Force save the KNN model as requested
    best_model = knn
    model_type = "KNN"

    model_path = "weights/pose_classifier.pkl"
    print(f"\nSaving the best model ({model_type}) to '{model_path}'...")

    os.makedirs("weights", exist_ok=True)
    with open(model_path, "wb") as f:
        pickle.dump({
            "model": best_model,
            "model_type": model_type,
            "features": list(X.columns),
            "classes": list(best_model.classes_)
        }, f)

    print("Model training and export successful!")

if __name__ == "__main__":
    main()
