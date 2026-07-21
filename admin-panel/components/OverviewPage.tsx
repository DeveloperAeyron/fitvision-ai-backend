"use client";

import { useEffect, useState } from "react";
import {
  ArrowRight, Barbell, Brain, CheckCircle, ForkKnife, Gauge, ListChecks,
  Plus, ShieldCheck, UploadSimple, WarningCircle,
} from "@phosphor-icons/react";
import {
  fetchConfigList, fetchExercises, fetchModels, formatBytes,
  type ConfigMeta, type ModelInfo,
} from "@/lib/api";
import { BACKEND_URL } from "@/lib/backend";
import { formatDateTime } from "@/lib/format";

const CONFIG_KEYS = [
  "goal-options",
  "meal-plan-templates",
  "workout-plan-rules",
  "alternative-meals",
];

const SLOT_META: Record<string, { task: string; backend: string }> = {
  "exercise-rep": {
    task: "Rep counting · pushup, squat, situp",
    backend: "TCN (30-frame pose sequence)",
  },
  equipment: {
    task: "Gym equipment detection",
    backend: "YOLO · 63 classes",
  },
};

type OverviewProps = {
  toast: (message: string) => void;
  onNavigate: (page: string) => void;
};

export default function OverviewPage({ toast, onNavigate }: OverviewProps) {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [configs, setConfigs] = useState<ConfigMeta[]>([]);
  const [exerciseCount, setExerciseCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [backendOk, setBackendOk] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      try {
        const [modelResult, configResult, exercises] = await Promise.all([
          fetchModels(),
          fetchConfigList(),
          fetchExercises().catch(() => null),
        ]);
        if (cancelled) return;
        setModels(modelResult.models);
        setConfigs(configResult.configs);
        setExerciseCount(exercises?.length ?? null);
        setBackendOk(exercises !== null);
      } catch {
        if (!cancelled) toast("Could not load overview data");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [toast]);

  const deployedCount = models.filter((m) => m.size_bytes > 0).length;
  const today = new Date().toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
  const greeting = (() => {
    const hour = new Date().getHours();
    if (hour < 12) return "Good morning";
    if (hour < 17) return "Good afternoon";
    return "Good evening";
  })();

  const modelMap = Object.fromEntries(models.map((m) => [m.slot, m]));

  return (
    <>
      <div className="page-title">
        <div>
          <span className="eyebrow">{today}</span>
          <h1>{greeting}, Ali.</h1>
          <p>Live status across models, exercises, and meal plan configs.</p>
        </div>
        <div className="title-actions">
          <button className="secondary" onClick={() => onNavigate("Models")}>
            <UploadSimple />Upload model
          </button>
          <button className="primary" onClick={() => onNavigate("Meal plans")}>
            <Plus weight="bold" />Edit meal plans
          </button>
        </div>
      </div>

      <section className="metrics">
        <Metric
          icon={<Brain />}
          tone="violet"
          label="Production models"
          value={loading ? "—" : `${deployedCount}/2`}
          change={deployedCount === 2 ? "Both slots deployed" : "Check missing weights"}
        />
        <Metric
          icon={<ForkKnife />}
          tone="green"
          label="Meal configs"
          value={String(CONFIG_KEYS.length)}
          change="JSON-driven templates"
        />
        <Metric
          icon={<Barbell />}
          tone="orange"
          label="Exercises"
          value={exerciseCount === null ? "—" : String(exerciseCount)}
          change={backendOk ? "Synced from backend" : "Backend unreachable"}
        />
        <Metric
          icon={<ListChecks />}
          tone="blue"
          label="Plan templates"
          value="3"
          change="loss / gain / general"
        />
      </section>

      <div className="grid-main">
        <section className="card models-card">
          <CardHead
            title="Model health"
            subtitle="Deployed ML artifacts on the backend server"
            action="Manage models"
            onAction={() => onNavigate("Models")}
          />
          {loading ? (
            <div className="config-loading overview-loading">Loading models…</div>
          ) : (
            <div className="model-list">
              {(["exercise-rep", "equipment"] as const).map((slot, index) => {
                const item = modelMap[slot];
                const meta = SLOT_META[slot];
                const deployed = Boolean(item?.size_bytes);
                return (
                  <div className="model-row" key={slot}>
                    <div className={`model-icon m${index}`}>
                      <Brain weight="fill" />
                    </div>
                    <div className="model-name">
                      <strong>{item?.label ?? slot}</strong>
                      <span>{meta.task}</span>
                    </div>
                    <div className="model-stat">
                      <span>File</span>
                      <strong>{item?.filename ?? "—"}</strong>
                    </div>
                    <div className="model-stat">
                      <span>Modified</span>
                      <strong>{formatDateTime(item?.lastModifiedAt)}</strong>
                    </div>
                    <span className={`pill ${deployed ? "live" : "draft"}`}>
                      <i />{deployed ? "Deployed" : "Missing"}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <section className="card activity">
          <CardHead title="System status" subtitle="Backend and workspace connections" />
          <div className="timeline">
            <StatusRow
              ok={deployedCount === 2}
              title="ML model weights"
              meta={`${deployedCount}/2 deployed in weights/`}
            />
            <StatusRow
              ok={backendOk === true}
              title="Exercise API"
              meta={backendOk ? `Connected · ${BACKEND_URL}` : `Unreachable · ${BACKEND_URL}`}
            />
            <StatusRow
              ok
              title="Meal plan configs"
              meta={`${configs.length || CONFIG_KEYS.length} JSON files · latest ${formatDateTime(
                configs.reduce<string | null>((latest, cfg) => {
                  if (!cfg.lastModifiedAt) return latest;
                  if (!latest || cfg.lastModifiedAt > latest) return cfg.lastModifiedAt;
                  return latest;
                }, null),
              )}`}
            />
          </div>
          <div className="overview-endpoints">
            <strong>Live endpoints</strong>
            <code>POST /count-reps</code>
            <code>POST /detect-equipment</code>
            <code>GET /exercises</code>
          </div>
        </section>
      </div>

      <div className="grid-bottom">
        <section className="card">
          <CardHead
            title="Recent updates"
            subtitle="Latest changes in this workspace"
            action="View exercises"
            onAction={() => onNavigate("Exercises")}
          />
          <div className="timeline">
            <Activity
              icon={<Brain />}
              tone="violet"
              title="TCN rep counter integrated"
              meta="Exercise Rep · TCN-exercise.pt · Today"
            />
            <Activity
              icon={<Gauge />}
              tone="orange"
              title="Equipment YOLO detector live"
              meta="Equipment-detection.pt · /detect-equipment · Today"
            />
            <Activity
              icon={<ForkKnife />}
              tone="green"
              title="Meal configs moved to JSON"
              meta="Admin panel · editable without backend"
            />
            <Activity
              icon={<ShieldCheck />}
              tone="blue"
              title="Production backend connected"
              meta={`Exercises API · ${BACKEND_URL}`}
            />
          </div>
        </section>

        <section className="card overview-quick">
          <CardHead title="Quick actions" subtitle="Jump to common admin tasks" />
          <div className="quick-grid">
            {[
              ["Exercises", Barbell, "Manage exercise library"],
              ["Models", Brain, "Upload TCN or YOLO weights"],
              ["Meals", ForkKnife, "Edit alternative meals"],
              ["Meal plans", ListChecks, "Goal & template rules"],
            ].map(([label, Icon, hint]) => (
              <button
                key={label as string}
                type="button"
                className="quick-action"
                onClick={() => onNavigate(label as string)}
              >
                <Icon weight="fill" />
                <div>
                  <strong>{label as string}</strong>
                  <span>{hint as string}</span>
                </div>
                <ArrowRight />
              </button>
            ))}
          </div>
        </section>
      </div>
    </>
  );
}

function Metric({
  icon, tone, label, value, change,
}: {
  icon: React.ReactNode;
  tone: string;
  label: string;
  value: string;
  change: string;
}) {
  return (
    <div className="metric card">
      <div className={`metric-icon ${tone}`}>{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{change}</small>
      </div>
      <div className="spark">▁▂▂▃▅▄▆▇</div>
    </div>
  );
}

function CardHead({
  title, subtitle, action, onAction,
}: {
  title: string;
  subtitle: string;
  action?: string;
  onAction?: () => void;
}) {
  return (
    <div className="card-head">
      <div>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
      {action && (
        <button type="button" onClick={onAction}>
          {action}<ArrowRight />
        </button>
      )}
    </div>
  );
}

function Activity({
  icon, tone, title, meta,
}: {
  icon: React.ReactNode;
  tone: string;
  title: string;
  meta: string;
}) {
  return (
    <div className="activity-row">
      <div className={`activity-icon ${tone}`}>{icon}</div>
      <div>
        <strong>{title}</strong>
        <span>{meta}</span>
      </div>
    </div>
  );
}

function StatusRow({
  ok, title, meta,
}: {
  ok: boolean;
  title: string;
  meta: string;
}) {
  return (
    <div className="activity-row status-row">
      <div className={`activity-icon ${ok ? "green" : "orange"}`}>
        {ok ? <CheckCircle weight="fill" /> : <WarningCircle weight="fill" />}
      </div>
      <div>
        <strong>{title}</strong>
        <span>{meta}</span>
      </div>
    </div>
  );
}
