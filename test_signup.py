import traceback
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

try:
    response = client.post("/auth/signup", json={"email": "testclient@yopmail.com", "password": "password123", "gender": "Male", "date_of_birth": "1990-01-01"})
    print(response.status_code)
    print(response.text)
except Exception as e:
    traceback.print_exc()
