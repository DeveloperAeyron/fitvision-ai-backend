import { readFile } from "node:fs/promises";
import { NextRequest } from "next/server";
import { buildNutritionPlan } from "@/lib/plan-preview";
import { configPath } from "@/lib/repo-paths";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const fitnessGoal = body.fitness_goal ?? "Weight Loss";
    const activityLevel = body.activity_level ?? "Active";

    const filePath = configPath("meal-plan-templates");
    if (!filePath) {
      return Response.json({ detail: "Templates config missing" }, { status: 500 });
    }

    const config = JSON.parse(await readFile(filePath, "utf-8"));
    const nutritionPlan = buildNutritionPlan(config, fitnessGoal, activityLevel);

    return Response.json({
      fitness_goal: fitnessGoal,
      activity_level: activityLevel,
      nutrition_plan: nutritionPlan,
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Preview failed";
    return Response.json({ detail }, { status: 500 });
  }
}
