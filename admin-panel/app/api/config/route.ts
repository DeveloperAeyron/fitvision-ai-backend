import { stat } from "node:fs/promises";
import path from "node:path";
import { CONFIG_FILES, DATA_DIR } from "@/lib/repo-paths";
import { fileLastModifiedIso } from "@/lib/format";

export const runtime = "nodejs";

export async function GET() {
  const configs = await Promise.all(
    Object.entries(CONFIG_FILES).map(async ([key, filename]) => {
      const fullPath = path.join(DATA_DIR, filename);
      try {
        const info = await stat(fullPath);
        return {
          key,
          filename,
          size_bytes: info.size,
          lastModifiedAt: await fileLastModifiedIso(fullPath),
        };
      } catch {
        return {
          key,
          filename,
          size_bytes: 0,
          lastModifiedAt: null,
        };
      }
    }),
  );

  return Response.json({ configs });
}
