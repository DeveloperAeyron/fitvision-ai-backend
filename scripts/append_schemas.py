import os

file_path = r"e:\Salik\Fitvision\fitvision-ai-backend\api\schemas.py"

content_to_add = """

class MealPlanResponse(BaseModel):
    goal_id: int
    fitness_goal: str | None = None
    nutrition_plan: dict
    created_at: datetime
"""

with open(file_path, "a", encoding="utf-8") as f:
    f.write(content_to_add)

print("Successfully appended MealPlanResponse")
