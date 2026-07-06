import sys
import uuid
from fastapi.testclient import TestClient

from main import app


def test_goals_and_plans_flow():
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

        # 2. Test create goal: Unauthenticated (should fail)
        goal_payload = {
            "target_workouts": 4,
            "target_reps": 400,
            "target_calories": 2500,
            "fitness_goal": "Weight Loss",
            "activity_level": "Lightly Active"
        }
        fail_res = client.post("/auth/goals", json=goal_payload)
        assert fail_res.status_code == 401

        # 3. Test create goal: Authenticated (should succeed and generate plans)
        success_res = client.post("/auth/goals", json=goal_payload, headers=headers)
        assert success_res.status_code == 200, f"Goal creation failed: {success_res.text}"
        
        goal_data = success_res.json()
        assert goal_data["target_workouts"] == 4
        assert goal_data["fitness_goal"] == "Weight Loss"
        assert goal_data["activity_level"] == "Lightly Active"
        
        # Verify plans generated
        assert len(goal_data["workout_plan"]) > 0
        assert "daily_calories" in goal_data["nutrition_plan"]
        assert goal_data["nutrition_plan"]["daily_calories"] == 1800  # based on Loss + Lightly Active

        # 4. Test fetch active goal (GET /auth/goals)
        get_res = client.get("/auth/goals", headers=headers)
        assert get_res.status_code == 200
        active_data = get_res.json()
        assert active_data["fitness_goal"] == "Weight Loss"
        assert len(active_data["workout_plan"]) > 0

        # 5. Test updating goal with different metrics (Muscle Gain)
        muscle_payload = {
            "target_workouts": 5,
            "target_reps": 600,
            "target_calories": 4000,
            "fitness_goal": "Muscle Gain",
            "activity_level": "Active"
        }
        update_res = client.post("/auth/goals", json=muscle_payload, headers=headers)
        assert update_res.status_code == 200
        updated_data = update_res.json()
        assert updated_data["target_workouts"] == 5
        assert updated_data["fitness_goal"] == "Muscle Gain"
        assert updated_data["nutrition_plan"]["daily_calories"] == 3000  # Gain + Active

        print("--- ALL USER GOALS & PLANNER INTEGRATION TESTS PASSED ---")


if __name__ == "__main__":
    try:
        test_goals_and_plans_flow()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
