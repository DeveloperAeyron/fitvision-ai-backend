from ultralytics import YOLO
import sys
import cv2

def main():
    model_path = "best (3).pt"
    try:
        # Load the model
        print(f"Attempting to load model from: {model_path}")
        model = YOLO(model_path)
        print("Model loaded successfully!")
        
        # Print basic information about the model
        model.info()
        
        # Check if an input source was provided via command line
        if len(sys.argv) > 1:
            source = sys.argv[1]
            print(f"Running inference on source: {source}")
            
            # Run inference
            results = model(source)
            
            # Process and display results
            for result in results:
                # Print detected boxes or keypoints
                if hasattr(result, 'boxes') and result.boxes is not None:
                    print("Boxes:", result.boxes.data)
                if hasattr(result, 'keypoints') and result.keypoints is not None:
                    print("Keypoints:", result.keypoints.data)
                
                # Show image with annotations
                annotated_frame = result.plot()
                cv2.imshow("Inference Result", annotated_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'): break
            cv2.destroyAllWindows()
        else:
            print("\nModel is ready for inference.")
            print("To test on a specific image or video, run:")
            print("python test_model.py <path_to_image_or_video>")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
