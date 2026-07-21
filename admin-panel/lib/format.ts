import { stat } from "node:fs/promises";

export async function fileLastModifiedIso(filePath: string): Promise<string | null> {
  try {
    const info = await stat(filePath);
    return new Date(info.mtimeMs).toISOString();
  } catch {
    return null;
  }
}

export function formatDateTime(value: string | number | null | undefined): string {
  if (value == null) return "—";
  const date = typeof value === "number"
    ? new Date(value > 1e12 ? value : value * 1000)
    : new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
