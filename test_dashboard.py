import sys
import uuid
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from main import app


def test_dashboard_calculations():
    uid = uuid.uuid4().hex[:8]
    email = f"user_{uid}@example.com"
    password = "SecurePassword123!"

    with TestClient(app) as client:
        # 1. Signup and login to get auth token
        signup_res = client.post("/auth/signup", json={
            "email": email,
            "password": password
        })
        assert signup_res.status_code == 201

        login_res = client.post("/auth/login", data={
            "email": email,
            "password": password
        })
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Get dashboard initially (should return default Figma fallback values since logs are empty)
        dash_res = client.get("/auth/dashboard", headers=headers)
        assert dash_res.status_code == 200
        data = dash_res.json()
        assert data["username"] == email
        assert data["email"] == email
        assert data["completion_percentage"] == 72.0  # fallback today completion
        assert data["goals"]["workouts"]["current"] == 11
        assert data["goals"]["workouts"]["target"] == 15
        assert data["goals"]["reps"]["current"] == 1245
        assert data["goals"]["reps"]["target"] == 1800
        assert data["goals"]["calories"]["current"] == 6250
        assert data["goals"]["calories"]["target"] == 8000
        
        # Check weekly progress fallbacks
        mon_progress = [d for d in data["weekly_progress"] if d["day"] == "Mon"][0]
        assert mon_progress["percentage"] == 20.0

        # 3. Log some workouts (ensure they fall in the current week)
        today = datetime.utcnow().date()
        start_of_week = datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time())
        time1_str = (start_of_week + timedelta(hours=10)).isoformat()
        time2_str = (start_of_week + timedelta(days=1, hours=10)).isoformat()

        # Log workout 1: Monday, 10 reps, 50 calories
        log_res1 = client.post("/auth/workouts/log", headers=headers, json={
            "exercise_name": "pushup",
            "reps": 10,
            "calories": 50,
            "duration_minutes": 5,
            "created_at": time1_str
        })
        assert log_res1.status_code == 201

        # Log workout 2: Tuesday, 20 reps, 100 calories
        log_res2 = client.post("/auth/workouts/log", headers=headers, json={
            "exercise_name": "squat",
            "reps": 20,
            "calories": 100,
            "duration_minutes": 10,
            "created_at": time2_str
        })
        assert log_res2.status_code == 201

        # 4. Get dashboard again (should now be calculated dynamically from logs!)
        dash_res2 = client.get("/auth/dashboard", headers=headers)
        assert dash_res2.status_code == 200
        data2 = dash_res2.json()
        
        # Total workouts: 2
        # Total reps: 30 (10 + 20)
        # Total calories: 150 (50 + 100)
        assert data2["goals"]["workouts"]["current"] == 2
        assert data2["goals"]["reps"]["current"] == 30
        assert data2["goals"]["calories"]["current"] == 150

        # Target workouts: 15, reps: 1800, calories: 8000
        # work_pct = 2/15 = 13.33%
        # rep_pct = 30/1800 = 1.67%
        # cal_pct = 150/8000 = 1.88%
        # avg = (13.33 + 1.67 + 1.88)/3 = 5.6%
        assert 5.0 <= data2["completion_percentage"] <= 6.0

        # Verify weekday values are mapped correctly
        mon_progress = [d for d in data2["weekly_progress"] if d["day"] == "Mon"][0]
        tue_progress = [d for d in data2["weekly_progress"] if d["day"] == "Tue"][0]

        # Since logs exist, non-logged days should be 0.0
        wed_progress = [d for d in data2["weekly_progress"] if d["day"] == "Wed"][0]
        assert wed_progress["percentage"] == 0.0

        # Monday's progress: 1 workout, 10 reps, 50 calories.
        # Daily target = weekly target / 7.
        # Workouts target = 15/7 = 2.14. reps = 1800/7 = 257.14. calories = 8000/7 = 1142.86.
        # w_pct = 1 / 2.14 = 46.7%
        # r_pct = 10 / 257.14 = 3.9%
        # c_pct = 50 / 1142.86 = 4.4%
        # average = (46.7 + 3.9 + 4.4)/3 = 18.3%
        assert 16.0 <= mon_progress["percentage"] <= 20.0
        assert tue_progress["percentage"] > 0.0


        # Next workout info structure check
        assert "title" in data2["next_workout"]
        assert "duration" in data2["next_workout"]

        print("--- ALL DASHBOARD INTEGRATION TESTS PASSED ---")


if __name__ == "__main__":
    try:
        test_dashboard_calculations()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
