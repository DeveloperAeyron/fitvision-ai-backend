import asyncio
import httpx
from sqlalchemy.ext.asyncio import create_async_engine

async def test_profile_update():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000") as client:
        # Sign in
        login_data = {"grant_type": "password", "username": "testclient@yopmail.com", "password": "password123"}
        response = await client.post("/auth/login", data=login_data)
        if response.status_code != 200:
            print("Login failed:", response.text)
            return
        
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get profile
        response = await client.get("/auth/profile", headers=headers)
        print("GET /profile:", response.status_code, response.json())
        
        # Update profile
        update_data = {
            "full_name": "John Doe",
            "gender": "Male",
            "allow_notifications": False,
            "app_blocker": True
        }
        response = await client.put("/auth/profile", headers=headers, json=update_data)
        print("PUT /profile:", response.status_code, response.json())
        
        # Get profile again
        response = await client.get("/auth/profile", headers=headers)
        print("GET /profile:", response.status_code, response.json())

if __name__ == "__main__":
    asyncio.run(test_profile_update())
