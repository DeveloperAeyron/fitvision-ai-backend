import sys
import uuid
from fastapi.testclient import TestClient

from main import app


def test_exercise_crud_flow():
    uid = uuid.uuid4().hex[:8]
    username = f"user_{uid}"
    email = f"user_{uid}@example.com"
    password = "SecurePassword123!"

    with TestClient(app) as client:
        # 1. Sign up and login to obtain a bearer token
        signup_res = client.post(
            "/auth/signup",
            json={"username": username, "email": email, "password": password}
        )
        assert signup_res.status_code == 201

        login_res = client.post(
            "/auth/login",
            data={"username": username, "password": password}
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Test create exercise: Unauthenticated (should fail)
        exercise_payload = {
            "title": f"Bicep Curl {uid}",
            "primary_muscle": "Biceps",
            "exercise_type": "Strength",
            "video_url": "http://example.com/curl.gif",
            "muscles_worked_pct": {"Biceps": 80, "Forearms": 20},
            "suggested_workouts": ["Arm Day", "Upper Pull"],
            "instructions": [
                "Stand straight with a dumbbell in each hand.",
                "Squeeze bicep and lift weights up."
            ],
            "safety_tips": [
                "Do not swing your back."
            ]
        }
        fail_res = client.post("/exercises", json=exercise_payload)
        assert fail_res.status_code == 401, "Should reject unauthenticated POST"

        # 3. Test create exercise: Authenticated (should succeed)
        success_res = client.post("/exercises", json=exercise_payload, headers=headers)
        assert success_res.status_code == 201, f"Create failed: {success_res.text}"
        exercise_data = success_res.json()
        assert exercise_data["title"] == exercise_payload["title"]
        assert exercise_data["primary_muscle"] == "Biceps"
        assert exercise_data["muscles_worked_pct"]["Biceps"] == 80
        assert "Arm Day" in exercise_data["suggested_workouts"]
        assert len(exercise_data["instructions"]) == 2

        exercise_id = exercise_data["id"]

        # 4. Test fetch all exercises
        list_res = client.get("/exercises")
        assert list_res.status_code == 200
        titles = [ex["title"] for ex in list_res.json()]
        assert exercise_payload["title"] in titles

        # 5. Test fetch single exercise
        single_res = client.get(f"/exercises/{exercise_id}")
        assert single_res.status_code == 200
        assert single_res.json()["title"] == exercise_payload["title"]

        # 6. Test update exercise (PUT)
        update_payload = dict(exercise_payload)
        update_payload["primary_muscle"] = "Biceps Brachii"
        update_payload["muscles_worked_pct"] = {"Biceps": 90, "Forearms": 10}

        update_res = client.put(f"/exercises/{exercise_id}", json=update_payload, headers=headers)
        assert update_res.status_code == 200
        updated_data = update_res.json()
        assert updated_data["primary_muscle"] == "Biceps Brachii"
        assert updated_data["muscles_worked_pct"]["Biceps"] == 90

        # 7. Test delete exercise (DELETE)
        delete_res = client.delete(f"/exercises/{exercise_id}", headers=headers)
        assert delete_res.status_code == 200
        assert delete_res.json()["message"] == "Exercise deleted successfully"

        # Confirm deleted
        get_deleted_res = client.get(f"/exercises/{exercise_id}")
        assert get_deleted_res.status_code == 404

        print("--- ALL EXERCISE CRUD INTEGRATION TESTS PASSED ---")


if __name__ == "__main__":
    try:
        test_exercise_crud_flow()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
