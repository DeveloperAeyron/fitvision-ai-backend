import asyncio
import sys
import uuid
from fastapi.testclient import TestClient
from sqlalchemy.future import select

from main import app
from api.database import async_session
from api.models import User, PWDResetOTP


def test_forgot_password_flow():
    # Use a unique username and email for this run
    uid = uuid.uuid4().hex[:8]
    email = f"user_{uid}@example.com"
    old_password = "OldPassword123!"
    new_password = "NewPassword123!"

    with TestClient(app) as client:
        # 1. Sign up the user
        signup_data = {
            "email": email,
            "password": old_password
        }
        res = client.post("/auth/signup", json=signup_data)
        assert res.status_code == 201, f"Signup failed: {res.text}"

        # 2. Trigger forgot-password with mocked email sender
        from unittest.mock import patch

        captured_otp = None

        async def mock_send_otp_email(target_email, otp):
            nonlocal captured_otp
            captured_otp = otp

        with patch("api.auth_routes.send_otp_email", side_effect=mock_send_otp_email) as mock_send:
            res = client.post("/auth/forgot-password", json={"email": email})
            assert res.status_code == 200, f"Forgot password failed: {res.text}"
            assert "reset OTP has been sent" in res.json()["message"]

            assert mock_send.called
            otp_code = captured_otp
            assert otp_code is not None, "OTP code was not captured"
            assert len(otp_code) == 6

        # 4. Verify OTP with an incorrect code (should fail)
        res = client.post("/auth/verify-otp", json={"email": email, "otp": "000000"})
        assert res.status_code == 400, "Should fail with incorrect OTP"
        assert "Incorrect OTP" in res.json()["detail"]

        # 5. Verify OTP with correct code (should succeed)
        res = client.post("/auth/verify-otp", json={"email": email, "otp": otp_code})
        assert res.status_code == 200, f"OTP verification failed: {res.text}"
        data = res.json()
        assert "reset_token" in data
        reset_token = data["reset_token"]

        # 6. Verify password complexity validation during reset
        # A. Non-matching passwords
        res = client.post("/auth/reset-password", json={
            "token": reset_token,
            "password": "Password123!",
            "confirm_password": "Password123??"
        })
        assert res.status_code == 400, "Should fail on mismatching passwords"
        assert "Passwords do not match" in res.json()["detail"]

        # B. Less than 8 characters (triggers Pydantic schema validation error)
        res = client.post("/auth/reset-password", json={
            "token": reset_token,
            "password": "Up1!",
            "confirm_password": "Up1!"
        })
        assert res.status_code in (400, 422), "Should fail on short password"
        detail_msg = str(res.json()["detail"])
        assert "at least 8 characters" in detail_msg or "at least 8" in detail_msg

        # C. Missing uppercase letter
        res = client.post("/auth/reset-password", json={
            "token": reset_token,
            "password": "lowercase123!",
            "confirm_password": "lowercase123!"
        })
        assert res.status_code == 400, "Should fail on missing uppercase"
        assert "uppercase letter" in res.json()["detail"]

        # D. Missing symbol or digit
        res = client.post("/auth/reset-password", json={
            "token": reset_token,
            "password": "NoSymbolOrNumber",
            "confirm_password": "NoSymbolOrNumber"
        })
        assert res.status_code == 400, "Should fail on missing symbol/digit"
        assert "number or special symbol" in res.json()["detail"]

        # 7. Reset password with correct inputs
        res = client.post("/auth/reset-password", json={
            "token": reset_token,
            "password": new_password,
            "confirm_password": new_password
        })
        assert res.status_code == 200, f"Reset password failed: {res.text}"

        # 8. Try logging in with the old password (should fail)
        res = client.post("/auth/login", data={"email": email, "password": old_password})
        assert res.status_code == 401, "Should fail login with old password"

        # 9. Try logging in with the new password (should succeed)
        res = client.post("/auth/login", data={"email": email, "password": new_password})
        assert res.status_code == 200, f"Login with new password failed: {res.text}"
        assert "access_token" in res.json()

        print("--- ALL FORGOT PASSWORD FLOW TESTS PASSED ---")


if __name__ == "__main__":
    try:
        test_forgot_password_flow()
    except Exception as e:
        print("TEST FAIL:", e)
        sys.exit(1)
