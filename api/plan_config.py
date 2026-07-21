from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

CONFIG_FILES: dict[str, str] = {
    "goal-options": "goal_options.json",
    "meal-plan-templates": "meal_plan_templates.json",
    "workout-plan-rules": "workout_plan_rules.json",
    "alternative-meals": "alternative_meals.json",
}

MODEL_SLOTS: dict[str, dict[str, str]] = {
    "exercise-rep": {
        "path": "weights/TCN-exercise.pt",
        "filename": "TCN-exercise.pt",
        "label": "Exercise Rep (TCN)",
    },
    "equipment": {
        "path": "weights/Equipment-detection.pt",
        "filename": "Equipment-detection.pt",
        "label": "Equipment Detector",
    },
}

ROOT_DIR = DATA_DIR.parent

DEFAULT_MEAL = {
    "type": "Breakfast",
    "name": "Healthy Alternative Meal",
    "image_url": "https://images.unsplash.com/photo-1493770348161-369560ae357d?q=80&w=400&auto=format&fit=crop",
    "ingredients": ["Various healthy ingredients"],
    "steps": ["Prepare and enjoy."],
    "health_notes": "Balanced nutritious meal.",
    "calories": 400,
    "protein": 20,
    "carbs": 40,
    "fats": 15,
    "fiber": 5,
}


def _load_json(filename: str) -> dict[str, Any]:
    path = DATA_DIR / filename
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_meal_plan_config() -> dict[str, Any]:
    return _load_json("meal_plan_templates.json")


@lru_cache(maxsize=1)
def load_alternative_meals() -> dict[str, Any]:
    return _load_json("alternative_meals.json")["alternatives"]


@lru_cache(maxsize=1)
def load_goal_options() -> dict[str, Any]:
    return _load_json("goal_options.json")


@lru_cache(maxsize=1)
def load_workout_plan_rules() -> dict[str, Any]:
    return _load_json("workout_plan_rules.json")


def clear_config_cache() -> None:
    load_meal_plan_config.cache_clear()
    load_alternative_meals.cache_clear()
    load_goal_options.cache_clear()
    load_workout_plan_rules.cache_clear()


def get_config(config_key: str) -> dict[str, Any]:
    filename = CONFIG_FILES.get(config_key)
    if not filename:
        raise KeyError(f"Unknown config key: {config_key}")
    return _load_json(filename)


def get_config_mtime(config_key: str) -> datetime | None:
    filename = CONFIG_FILES.get(config_key)
    if not filename:
        raise KeyError(f"Unknown config key: {config_key}")
    path = DATA_DIR / filename
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def get_config_with_meta(config_key: str) -> dict[str, Any]:
    mtime = get_config_mtime(config_key)
    return {
        "data": get_config(config_key),
        "lastModifiedAt": mtime.isoformat() if mtime else None,
    }


def save_config(config_key: str, data: dict[str, Any]) -> datetime:
    filename = CONFIG_FILES.get(config_key)
    if not filename:
        raise KeyError(f"Unknown config key: {config_key}")
    path = DATA_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)
    clear_config_cache()
    mtime = get_config_mtime(config_key)
    return mtime or datetime.now(timezone.utc)


def list_config_keys() -> list[dict[str, str | None]]:
    items: list[dict[str, str | None]] = []
    for key, filename in CONFIG_FILES.items():
        mtime = get_config_mtime(key)
        items.append({
            "key": key,
            "filename": filename,
            "lastModifiedAt": mtime.isoformat() if mtime else None,
        })
    return items


def resolve_goal_category(fitness_goal: str) -> str:
    goal = fitness_goal.lower().strip()
    if "loss" in goal or "weight" in goal:
        return "loss"
    if "gain" in goal or "muscle" in goal or "hypertrophy" in goal:
        return "gain"
    return "general"


def resolve_activity_key(activity_level: str) -> str:
    level = activity_level.lower().strip()
    if "sedentary" in level:
        return "sedentary"
    if "light" in level:
        return "light"
    return "active"


def select_template(
    config: dict[str, Any],
    fitness_goal: str,
    activity_level: str,
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    category = resolve_goal_category(fitness_goal)
    template = config["templates"][category]
    activity_key = resolve_activity_key(activity_level)
    calories = template["activity_calories"].get(
        activity_key,
        template["activity_calories"]["active"],
    )
    daily_totals = {**template["macros"], "calories": calories}
    return category, daily_totals, template["meals"]


def get_alternative_meal(
    goal_str: str,
    meal_type: str,
    current_meal_name: str,
    swap_to_name: str | None = None,
) -> dict[str, Any]:
    category = resolve_goal_category(goal_str)
    mt = meal_type.capitalize().strip()
    if mt not in ("Breakfast", "Lunch", "Dinner"):
        mt = "Breakfast"

    options = load_alternative_meals().get(category, {}).get(mt, [])

    if swap_to_name:
        for opt in options:
            if opt["name"].lower() == swap_to_name.lower():
                return opt

    for opt in options:
        if opt["name"].lower() != current_meal_name.lower():
            return opt

    if options:
        return options[0]

    fallback = DEFAULT_MEAL.copy()
    fallback["type"] = mt
    return fallback


def perform_swap_logic(
    nut_plan: dict[str, Any],
    day_name: str,
    meal_type: str,
    fitness_goal: str,
    swap_to_name: str | None = None,
) -> dict[str, Any]:
    days = nut_plan.get("days", [])
    target_day = None
    for day in days:
        if day.get("day", "").lower() == day_name.lower():
            target_day = day
            break

    if not target_day:
        return nut_plan

    meals = target_day.get("meals", [])
    target_meal = None
    for meal in meals:
        if meal.get("type", "").lower() == meal_type.lower():
            target_meal = meal
            break

    if not target_meal:
        return nut_plan

    current_meal_name = target_meal.get("name", "")
    new_meal = get_alternative_meal(
        fitness_goal, meal_type, current_meal_name, swap_to_name=swap_to_name,
    )
    target_meal.update(new_meal)
    target_meal["completed"] = False

    actual_totals = {
        "calories": 0,
        "protein": 0,
        "carbs": 0,
        "fats": 0,
        "fiber": 0,
    }
    for meal in meals:
        if meal.get("completed", False):
            actual_totals["calories"] += meal.get("calories", 0)
            actual_totals["protein"] += meal.get("protein", 0)
            actual_totals["carbs"] += meal.get("carbs", 0)
            actual_totals["fats"] += meal.get("fats", 0)
            actual_totals["fiber"] += meal.get("fiber", 0)
    target_day["actual_totals"] = actual_totals

    return nut_plan


def get_alternative_meal_options(goal_str: str, meal_type: str) -> list[dict[str, Any]]:
    category = resolve_goal_category(goal_str)
    mt = meal_type.capitalize().strip()
    if mt not in ("Breakfast", "Lunch", "Dinner"):
        mt = "Breakfast"
    return load_alternative_meals().get(category, {}).get(mt, [])


MEAL_DAYS = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
]


def build_nutrition_plan(fitness_goal: str, activity_level: str) -> dict[str, Any]:
    """Build a 7-day nutrition plan from JSON templates."""
    config = load_meal_plan_config()
    _, daily_totals, meals = select_template(config, fitness_goal, activity_level)

    nutrition_plan: dict[str, Any] = {"daily_totals": daily_totals, "days": []}
    for day in MEAL_DAYS:
        day_meals = []
        for meal in meals:
            meal_copy = meal.copy()
            meal_copy["completed"] = False
            day_meals.append(meal_copy)
        nutrition_plan["days"].append({
            "day": day,
            "actual_totals": {
                "calories": 0, "protein": 0, "carbs": 0, "fats": 0, "fiber": 0,
            },
            "meals": day_meals,
        })
    return nutrition_plan
