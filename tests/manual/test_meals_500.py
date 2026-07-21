import requests
import uuid

uid = uuid.uuid4().hex[:8]
email = f"user_{uid}@example.com"
password = "SecurePassword123!"

try:
    # 1. Sign up
    signup_res = requests.post(
        "http://localhost:8003/auth/signup",
        json={"email": email, "password": password, "full_name": "Test User"}
    )
    print("Signup Response:", signup_res.status_code)

    # 2. Login
    login_res = requests.post(
        "http://localhost:8003/auth/login",
        data={"email": email, "password": password}
    )
    print("Login Response:", login_res.status_code)

    token = login_res.json().get("access_token")
    if token:
        headers = {"Authorization": f"Bearer {token}"}
        
        # 3. Test Meals
        payload_meals = {
            "fitness_goal": "Weight Loss",
            "activity_level": "Active",
            "age": 25,
            "gender": "Male",
            "weight": 70,
            "weight_unit": "kg"
        }
        meals_res = requests.post("http://localhost:8003/auth/meals", json=payload_meals, headers=headers)
        print("Meals Response:", meals_res.status_code, meals_res.text[:50])

        # 4. Test Workouts
        payload_workouts = {
            "fitness_goal": "Build Muscle",
            "activity_level": "Active",
            "age": 25,
            "gender": "Male"
        }
        workouts_res = requests.post("http://localhost:8003/auth/goals", json=payload_workouts, headers=headers)
        print("Workouts Response:", workouts_res.status_code, workouts_res.text[:50])
except Exception as e:
    print(e)
