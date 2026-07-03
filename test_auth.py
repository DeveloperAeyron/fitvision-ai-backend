import sys
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_auth_flow():
    with TestClient(app) as client:
        # 1. Signup
        test_user = {
            "username": "testuser_unique_123",
            "email": "testuser_unique_123@example.com",
            "password": "testpassword123"
        }

        # Try signing up
        response = client.post("/auth/signup", json=test_user)
        print("Signup Response Status:", response.status_code)
        print("Signup Response Body:", response.json())

        # If already exists (from a previous test run), status might be 400, which is fine, but we expect 201 on first run.
        assert response.status_code in (201, 400), "Signup failed!"

        # 2. Login
        login_data = {
            "username": test_user["username"],
            "password": test_user["password"]
        }
        # OAuth2Form login uses x-www-form-urlencoded data
        response = client.post("/auth/login", data=login_data)
        print("Login Response Status:", response.status_code)
        print("Login Response Body:", response.json())

        assert response.status_code == 200, "Login failed!"
        assert "access_token" in response.json(), "Access token not in response!"
        assert response.json()["token_type"] == "bearer", "Token type is not bearer!"

        print("ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    try:
        test_auth_flow()
    except Exception as e:
        print("TEST RUN FAILED:", e)
        sys.exit(1)
