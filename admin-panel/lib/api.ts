const ADMIN_KEY_STORAGE = "fitvision_admin_key";

export function getAdminKey(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(ADMIN_KEY_STORAGE) ?? "fitvision-admin-dev";
}

export function setAdminKey(key: string) {
  localStorage.setItem(ADMIN_KEY_STORAGE, key);
}

async function localFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("X-Admin-Key", getAdminKey());
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export type ConfigResponse = {
  data: Record<string, unknown>;
  lastModifiedAt: string | null;
};

export type ConfigMeta = {
  key: string;
  filename: string;
  size_bytes: number;
  lastModifiedAt: string | null;
};

export async function fetchConfig(configKey: string) {
  return localFetch<ConfigResponse>(`/api/config/${configKey}`);
}

export async function saveConfig(configKey: string, data: Record<string, unknown>) {
  return localFetch<{ message: string; key: string; lastModifiedAt: string | null }>(
    `/api/config/${configKey}`,
    {
      method: "PUT",
      body: JSON.stringify({ data }),
    },
  );
}

export async function fetchConfigList() {
  return localFetch<{ configs: ConfigMeta[] }>("/api/config");
}

export async function uploadConfigFile(configKey: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`/api/config/${configKey}/upload`, {
    method: "POST",
    headers: { "X-Admin-Key": getAdminKey() },
    body: form,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? "Upload failed");
  }
  return response.json() as Promise<{ message: string; filename: string; lastModifiedAt: string | null }>;
}

export function downloadConfigJson(filename: string, data: Record<string, unknown>) {
  const blob = new Blob([`${JSON.stringify(data, null, 2)}\n`], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export async function previewPlan(fitnessGoal: string, activityLevel: string) {
  return localFetch<{
    fitness_goal: string;
    activity_level: string;
    nutrition_plan: Record<string, unknown>;
  }>("/api/config/preview", {
    method: "POST",
    body: JSON.stringify({
      fitness_goal: fitnessGoal,
      activity_level: activityLevel,
    }),
  });
}

export type ModelInfo = {
  slot: string;
  label: string;
  filename: string;
  size_bytes: number;
  updated_at: number | null;
  lastModifiedAt: string | null;
};

export async function fetchModels() {
  return localFetch<{ models: ModelInfo[] }>("/api/models");
}

export async function uploadModel(slot: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`/api/models/${slot}`, {
    method: "POST",
    headers: { "X-Admin-Key": getAdminKey() },
    body: form,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? "Upload failed");
  }
  return response.json();
}

export async function downloadModel(slot: string, filename: string) {
  const response = await fetch(`/api/models/${slot}/download`);
  if (!response.ok) {
    throw new Error("Download failed");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function formatBytes(bytes: number) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / Math.pow(1024, index)).toFixed(index ? 1 : 0)} ${units[index]}`;
}

export type Exercise = {
  id: number;
  title: string;
  primary_muscle: string;
  exercise_type: string;
  difficulty_level?: string;
  equipment_required?: string;
  location_type?: string | null;
  video_url?: string | null;
  image_url?: string | null;
  suggested_workouts?: string[];
  instructions?: string[];
  safety_tips?: string[];
  created_at?: string;
  lastModifiedAt?: string | null;
};

export type ExerciseInput = Omit<Exercise, "id">;

export async function fetchExercises() {
  const response = await fetch("/api/exercises");
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? "Failed to load exercises — is the backend running?");
  }
  return response.json() as Promise<Exercise[]>;
}

export async function createExercise(data: ExerciseInput) {
  return localFetch<Exercise>("/api/exercises", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateExercise(id: number, data: ExerciseInput) {
  return localFetch<Exercise>(`/api/exercises/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteExercise(id: number) {
  return localFetch<{ message: string }>(`/api/exercises/${id}`, {
    method: "DELETE",
  });
}
