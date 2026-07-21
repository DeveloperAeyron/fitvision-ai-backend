type Meal = Record<string, unknown>;
type Template = {
  activity_calories: Record<string, number>;
  macros: Record<string, number>;
  meals: Meal[];
};

const MEAL_DAYS = [
  "Monday", "Tuesday", "Wednesday", "Thursday",
  "Friday", "Saturday", "Sunday",
];

function resolveGoalCategory(fitnessGoal: string): string {
  const goal = fitnessGoal.toLowerCase().trim();
  if (goal.includes("loss") || goal.includes("weight")) return "loss";
  if (goal.includes("gain") || goal.includes("muscle") || goal.includes("hypertrophy")) return "gain";
  return "general";
}

function resolveActivityKey(activityLevel: string): string {
  const level = activityLevel.toLowerCase().trim();
  if (level.includes("sedentary")) return "sedentary";
  if (level.includes("light")) return "light";
  return "active";
}

export function buildNutritionPlan(
  config: { templates: Record<string, Template> },
  fitnessGoal: string,
  activityLevel: string,
) {
  const category = resolveGoalCategory(fitnessGoal);
  const template = config.templates[category];
  if (!template) throw new Error(`Unknown template category: ${category}`);

  const activityKey = resolveActivityKey(activityLevel);
  const calories = template.activity_calories[activityKey] ?? template.activity_calories.active;

  const dailyTotals = { ...template.macros, calories };

  return {
    daily_totals: dailyTotals,
    days: MEAL_DAYS.map((day) => ({
      day,
      actual_totals: { calories: 0, protein: 0, carbs: 0, fats: 0, fiber: 0 },
      meals: template.meals.map((meal) => ({ ...meal, completed: false })),
    })),
  };
}
