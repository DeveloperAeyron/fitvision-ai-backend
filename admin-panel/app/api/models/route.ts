import { stat } from "node:fs/promises";
import path from "node:path";
import { MODEL_SLOTS, REPO_ROOT } from "@/lib/repo-paths";

export const runtime = "nodejs";

export async function GET() {
  const models = await Promise.all(
    Object.entries(MODEL_SLOTS).map(async ([slot, meta]) => {
      const fullPath = path.join(REPO_ROOT, meta.path);
      try {
        const info = await stat(fullPath);
        return {
          slot,
          label: meta.label,
          filename: meta.filename,
          size_bytes: info.size,
          updated_at: info.mtimeMs,
        };
      } catch {
        return {
          slot,
          label: meta.label,
          filename: meta.filename,
          size_bytes: 0,
          updated_at: null,
        };
      }
    }),
  );

  return Response.json({ models });
}
