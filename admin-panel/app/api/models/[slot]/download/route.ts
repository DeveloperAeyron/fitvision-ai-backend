import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { MODEL_SLOTS, REPO_ROOT } from "@/lib/repo-paths";

export const runtime = "nodejs";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ slot: string }> },
) {
  const { slot } = await params;
  const meta = MODEL_SLOTS[slot];
  if (!meta) {
    return Response.json({ detail: "Unknown model slot" }, { status: 404 });
  }

  const artifactPath = path.join(REPO_ROOT, meta.path);

  try {
    const [contents, info] = await Promise.all([readFile(artifactPath), stat(artifactPath)]);
    return new Response(new Uint8Array(contents), {
      headers: {
        "Content-Type": "application/octet-stream",
        "Content-Length": String(info.size),
        "Content-Disposition": `attachment; filename="${meta.filename}"`,
        "Cache-Control": "private, no-store",
      },
    });
  } catch {
    return Response.json({ detail: "Model artifact is unavailable" }, { status: 404 });
  }
}
