"use client";

import { useState } from "react";
import ConfigEditor from "@/components/ConfigEditor";
import { previewPlan } from "@/lib/api";

const TABS = [
  {
    key: "meal-plan-templates",
    label: "Meal templates",
    title: "Meal plan templates",
    subtitle: "Default breakfast, lunch, and dinner per goal category (loss / gain / general).",
  },
  {
    key: "goal-options",
    label: "Goal options",
    title: "Goal options",
    subtitle: "Fitness goals, activity levels, timelines, alarm sounds, and default targets.",
  },
  {
    key: "workout-plan-rules",
    label: "Workout rules",
    title: "Workout plan rules",
    subtitle: "Workout names, durations, equipment filters, and default training days.",
  },
] as const;

const FITNESS_GOALS = ["Weight Loss", "Muscle Gain", "General Health"];
const ACTIVITY_LEVELS = ["Sedentary", "Lightly Active", "Active", "Very Active"];

export default function MealPlansPage({ toast }: { toast: (message: string) => void }) {
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("meal-plan-templates");
  const [fitnessGoal, setFitnessGoal] = useState("Weight Loss");
  const [activityLevel, setActivityLevel] = useState("Active");
  const [previewJson, setPreviewJson] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);

  const active = TABS.find((t) => t.key === tab)!;

  const runPreview = async () => {
    setPreviewLoading(true);
    try {
      const result = await previewPlan(fitnessGoal, activityLevel);
      setPreviewJson(JSON.stringify(result.nutrition_plan, null, 2));
      toast("Live preview generated from saved templates");
    } catch (err) {
      toast(err instanceof Error ? err.message : "Preview failed");
    } finally {
      setPreviewLoading(false);
    }
  };

  return (
    <>
      <div className="page-title compact">
        <div>
          <span className="eyebrow">PLAN CONFIGURATION</span>
          <h1>Meal plans &amp; goals</h1>
          <p>Edit JSON configs that drive user meal plans, goal options, and workout rules.</p>
        </div>
      </div>

      <div className="config-tabs">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            className={tab === item.key ? "active" : ""}
            onClick={() => setTab(item.key)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="config-layout">
        <ConfigEditor
          key={active.key}
          configKey={active.key}
          title={active.title}
          subtitle={active.subtitle}
          toast={toast}
        />

        <section className="card config-preview">
          <div className="config-head">
            <div>
              <h2>Live preview</h2>
              <p>Generate a 7-day nutrition plan from the saved templates.</p>
            </div>
          </div>
          <div className="preview-controls">
            <label>
              <span>Fitness goal</span>
              <select value={fitnessGoal} onChange={(e) => setFitnessGoal(e.target.value)}>
                {FITNESS_GOALS.map((g) => (
                  <option key={g}>{g}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Activity level</span>
              <select value={activityLevel} onChange={(e) => setActivityLevel(e.target.value)}>
                {ACTIVITY_LEVELS.map((l) => (
                  <option key={l}>{l}</option>
                ))}
              </select>
            </label>
            <button className="primary" type="button" onClick={runPreview} disabled={previewLoading}>
              {previewLoading ? "Generating…" : "Generate preview"}
            </button>
          </div>
          <textarea
            className="config-textarea preview-output"
            readOnly
            value={previewJson || "Click “Generate preview” to see the plan users would receive."}
          />
        </section>
      </div>
    </>
  );
}
