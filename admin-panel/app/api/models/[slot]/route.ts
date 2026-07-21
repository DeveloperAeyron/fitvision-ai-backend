import { createWriteStream } from "node:fs";
import { mkdir, stat } from "node:fs/promises";
import path from "node:path";
import { pipeline } from "node:stream/promises";
import { Readable } from "node:stream";
import { NextRequest } from "next/server";
import { MODEL_SLOTS, REPO_ROOT, verifyAdminKey } from "@/lib/repo-paths";
import { fileLastModifiedIso } from "@/lib/format-server";

export const runtime = "nodejs";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ slot: string }> },
) {
  if (!verifyAdminKey(request)) {
    return Response.json({ detail: "Invalid or missing admin API key" }, { status: 401 });
  }

  const { slot } = await params;
  const meta = MODEL_SLOTS[slot];
  if (!meta) {
    return Response.json({ detail: "Unknown model slot" }, { status: 404 });
  }

  const dest = path.join(REPO_ROOT, meta.path);
  await mkdir(path.dirname(dest), { recursive: true });

  try {
    const form = await request.formData();
    const file = form.get("file");
    if (!(file instanceof Blob)) {
      return Response.json({ detail: "No file uploaded" }, { status: 400 });
    }

    const buffer = Buffer.from(await file.arrayBuffer());
    await pipeline(Readable.from(buffer), createWriteStream(dest));
    const info = await stat(dest);

    return Response.json({
      message: "Model uploaded",
      slot,
      filename: meta.filename,
      size_bytes: info.size,
      lastModifiedAt: await fileLastModifiedIso(dest),
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Upload failed";
    return Response.json({ detail }, { status: 500 });
  }
}
