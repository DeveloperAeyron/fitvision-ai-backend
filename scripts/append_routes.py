import os

file_path = r"e:\Salik\Fitvision\fitvision-ai-backend\api\auth_routes.py"

content_to_add = """

@router.get("/meal-plans", response_model=list[dict])
async def get_user_meal_plans(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from api.schemas import MealPlanResponse
    result = await db.execute(
        select(UserGoal)
        .where(UserGoal.user_id == current_user.id, UserGoal.has_meal_plan == True)
        .order_by(UserGoal.id.desc())
    )
    user_goals = result.scalars().all()
    
    meal_plans = []
    for g in user_goals:
        nut_plan = {}
        if g.nutrition_plan:
            try:
                nut_plan = json.loads(g.nutrition_plan)
            except Exception:
                pass
        meal_plans.append(
            MealPlanResponse(
                goal_id=g.id,
                fitness_goal=g.fitness_goal,
                nutrition_plan=nut_plan,
                created_at=g.created_at
            ).model_dump()
        )
    return meal_plans


@router.get("/profile")
async def get_user_profile(current_user: User = Depends(get_current_user)):
    from api.schemas import UserResponse
    return UserResponse.model_validate(current_user)


@router.put("/profile")
async def update_user_profile(
    profile_data: dict, # using dict here because I will import UserProfileUpdate later, or I can just use dict for now
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from api.schemas import UserProfileUpdate, UserResponse
    # Validate profile_data via UserProfileUpdate
    update_schema = UserProfileUpdate(**profile_data)
    update_data = update_schema.model_dump(exclude_unset=True)
    
    if "email" in update_data and update_data["email"] != current_user.email:
        # Check if new email is already taken
        email_result = await db.execute(select(User).where(User.email == update_data["email"]))
        if email_result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
            
    for key, value in update_data.items():
        setattr(current_user, key, value)
        
    await db.commit()
    await db.refresh(current_user)
    return UserResponse.model_validate(current_user)
"""

with open(file_path, "a", encoding="utf-8") as f:
    f.write(content_to_add)

print("Successfully appended routes")
