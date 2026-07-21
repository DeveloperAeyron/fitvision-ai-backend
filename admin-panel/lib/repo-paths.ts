import path from "node:path";

export const REPO_ROOT = path.resolve(process.cwd(), "..");
export const DATA_DIR = path.join(REPO_ROOT, "data");
export const WEIGHTS_DIR = path.join(REPO_ROOT, "weights");

export const CONFIG_FILES: Record<string, string> = {
  "goal-options": "goal_options.json",
  "meal-plan-templates": "meal_plan_templates.json",
  "workout-plan-rules": "workout_plan_rules.json",
  "alternative-meals": "alternative_meals.json",
};

export const MODEL_SLOTS: Record<string, { path: string; filename: string; label: string }> = {
  "exercise-rep": {
    path: path.join("weights", "exercise_rep_tcn.keras"),
    filename: "exercise_rep_tcn.keras",
    label: "Exercise Rep (TCN)",
  },
  equipment: {
    path: path.join("weights", "Equipment-detection.pt"),
    filename: "Equipment-detection.pt",
    label: "Equipment Detector",
  },
};

export function configPath(key: string) {
  const filename = CONFIG_FILES[key];
  if (!filename) return null;
  return path.join(DATA_DIR, filename);
}

export function verifyAdminKey(request: Request): boolean {
  const expected = process.env.ADMIN_API_KEY ?? "fitvision-admin-dev";
  return request.headers.get("X-Admin-Key") === expected;
}
