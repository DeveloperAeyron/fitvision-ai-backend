import { writeFile } from "node:fs/promises";
import { NextRequest } from "next/server";
import { configPath, verifyAdminKey } from "@/lib/repo-paths";

export const runtime = "nodejs";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ key: string }> },
) {
  if (!verifyAdminKey(request)) {
    return Response.json({ detail: "Invalid or missing admin API key" }, { status: 401 });
  }

  const { key } = await params;
  const filePath = configPath(key);
  if (!filePath) {
    return Response.json({ detail: "Unknown config" }, { status: 404 });
  }

  try {
    const form = await request.formData();
    const file = form.get("file");
    if (!(file instanceof Blob)) {
      return Response.json({ detail: "No file uploaded" }, { status: 400 });
    }

    const raw = await file.text();
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      return Response.json({ detail: "File is not valid JSON" }, { status: 400 });
    }

    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return Response.json({ detail: "JSON root must be an object" }, { status: 400 });
    }

    const formatted = `${JSON.stringify(parsed, null, 2)}\n`;
    await writeFile(filePath, formatted, "utf-8");

    return Response.json({
      message: "Config replaced from upload",
      key,
      filename: file instanceof File ? file.name : "upload.json",
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Upload failed";
    return Response.json({ detail }, { status: 500 });
  }
}
