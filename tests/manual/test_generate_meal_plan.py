import requests

url = "http://localhost:8004"
auth_url = f"{url}/auth/signup"
import uuid
email = f"test_{uuid.uuid4().hex[:6]}@yopmail.com"
resp = requests.post(auth_url, json={"email": email, "username": email, "password": "password123"})
resp = requests.post(f"{url}/auth/login", data={"email": email, "password": "password123"})
if resp.status_code != 200:
    print("Login failed", resp.status_code, resp.text)
    exit()
token = resp.json()["access_token"]

headers = {"Authorization": f"Bearer {token}"}
goals = requests.get(f"{url}/auth/goals", headers=headers).json()
print("Goals:", [g['id'] for g in goals])

# take the first goal that has no meal plan
goal_id = None
for g in goals:
    if not g.get('has_meal_plan'):
        goal_id = g['id']
        break

if not goal_id:
    # Just create a goal
    res = requests.post(f"{url}/auth/goals", json={
        "fitness_goal": "Weight Loss",
        "activity_level": "Sedentary",
        "days": ["Monday"],
        "age": 25,
        "gender": "Male",
        "weight": 80,
        "weight_unit": "kg",
        "timeline": "3 months",
        "alarm_sound": "default",
        "time_of_day": "08:00 AM"
    }, headers=headers)
    goal_id = res.json()["id"]
    print("Created goal", goal_id)

res = requests.post(f"{url}/auth/goals/{goal_id}/meal-plan", headers=headers)
print("Meal plan res:", res.status_code)
goal_data = res.json()
print("Has meal plan:", goal_data.get('has_meal_plan'))
print("Nutrition plan generated:", goal_data.get('nutrition_plan') is not None)
