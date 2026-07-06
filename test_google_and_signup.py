import sys
import uuid
from fastapi.testclient import TestClient

from main import app


def test_google_and_signup_flow():
    uid = uuid.uuid4().hex[:8]
    email = f"user_{uid}@example.com"
    password = "SecurePassword123!"
    gender = "Male"
    dob = "1998-05-15"

    with TestClient(app) as client:
        # 1. Test signup with new fields (gender and date_of_birth)
        signup_data = {
            "email": email,
            "password": password,
            "gender": gender,
            "date_of_birth": dob
        }
        res = client.post("/auth/signup", json=signup_data)
        assert res.status_code == 201, f"Signup failed: {res.text}"
        
        user_data = res.json()
        assert user_data["email"] == email
        assert user_data["gender"] == gender
        assert user_data["date_of_birth"] == dob

        # 2. Test login with Google authentication using mocked HTTP call
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_response = MagicMock()
        mock_response.status_code = 200
        # Simulated payload returned from Google verification
        google_email = f"google_user_{uid}@gmail.com"
        mock_response.json.return_value = {
            "email": google_email,
            "email_verified": "true",
            "name": "Google User",
            "sub": "google_sub_id_12345",
            "aud": "272845957801-lel0bj139oa9tic61f419du4fgpspc7c.apps.googleusercontent.com"
        }

        # Patch httpx.AsyncClient.get to mock tokeninfo call
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            
            # Case A: New Google user (automatic signup)
            res = client.post("/auth/google", json={"id_token": "valid_google_token"})
            assert res.status_code == 200, f"Google login failed: {res.text}"
            
            data = res.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"
            assert mock_get.called

            # Case B: Existing Google user (login directly)
            res = client.post("/auth/google", json={"id_token": "valid_google_token"})
            assert res.status_code == 200, f"Subsequent Google login failed: {res.text}"
            data_subsequent = res.json()
            assert "access_token" in data_subsequent

            # Case C: Invalid Google ID token (should return 400 Bad Request)
            mock_fail_response = MagicMock()
            mock_fail_response.status_code = 400
            mock_fail_response.json.return_value = {"error_description": "Invalid Value"}
            
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_fail_get:
                mock_fail_get.return_value = mock_fail_response
                res_fail = client.post("/auth/google", json={"id_token": "invalid_token"})
                assert res_fail.status_code == 400
                assert "Invalid Google ID token" in res_fail.json()["detail"]

        print("--- ALL GOOGLE LOGIN AND SIGNUP FIELD TESTS PASSED ---")


if __name__ == "__main__":
    try:
        test_google_and_signup_flow()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
