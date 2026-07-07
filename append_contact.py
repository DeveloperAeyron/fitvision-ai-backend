import os

file_path = r"e:\Salik\Fitvision\fitvision-ai-backend\api\auth_routes.py"

content_to_add = """

from pydantic import BaseModel
class ContactUsRequest(BaseModel):
    email: str
    description: str
    file_url: str | None = None

@router.post("/contact")
async def contact_us(
    request: ContactUsRequest,
    current_user: User = Depends(get_current_user)
):
    # Dummy implementation for Contact Us
    logger.info(f"Contact Us message from {request.email}: {request.description}")
    return {"message": "Thank you for contacting us. Your request has been received."}
"""

with open(file_path, "a", encoding="utf-8") as f:
    f.write(content_to_add)

print("Successfully appended Contact Us endpoint")
