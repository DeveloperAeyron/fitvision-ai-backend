import { readFile, writeFile } from "node:fs/promises";
import { NextRequest } from "next/server";
import { CONFIG_FILES, configPath, verifyAdminKey } from "@/lib/repo-paths";
import { fileLastModifiedIso } from "@/lib/format";

export const runtime = "nodejs";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ key: string }> },
) {
  const { key } = await params;
  const filePath = configPath(key);
  if (!filePath) {
    return Response.json({ detail: "Unknown config" }, { status: 404 });
  }

  try {
    const raw = await readFile(filePath, "utf-8");
    const lastModifiedAt = await fileLastModifiedIso(filePath);
    return Response.json({
      data: JSON.parse(raw),
      lastModifiedAt,
    });
  } catch {
    return Response.json({ detail: "Config file not found" }, { status: 404 });
  }
}

export async function PUT(
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
    const body = await request.json();
    const data = body?.data;
    if (!data || typeof data !== "object" || Array.isArray(data)) {
      return Response.json({ detail: "Body must include a data object" }, { status: 400 });
    }

    const formatted = `${JSON.stringify(data, null, 2)}\n`;
    await writeFile(filePath, formatted, "utf-8");
    const lastModifiedAt = await fileLastModifiedIso(filePath);

    return Response.json({ message: "Config saved", key, lastModifiedAt });
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Save failed";
    return Response.json({ detail }, { status: 500 });
  }
}
