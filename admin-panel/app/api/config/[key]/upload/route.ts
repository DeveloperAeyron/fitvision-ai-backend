import { NextRequest } from "next/server";
import { BACKEND_URL, adminHeaders } from "@/lib/backend";

export const runtime = "nodejs";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ key: string }> },
) {
  const { key } = await params;

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

    const response = await fetch(`${BACKEND_URL}/admin/config/${key}`, {
      method: "PUT",
      headers: adminHeaders(request),
      body: JSON.stringify({ data: parsed }),
      cache: "no-store",
    });

    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      return Response.json(
        { detail: body.detail ?? "Upload failed" },
        { status: response.status },
      );
    }

    return Response.json({
      message: "Config replaced from upload",
      key,
      filename: file instanceof File ? file.name : "upload.json",
      lastModifiedAt: body.lastModifiedAt ?? null,
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Upload failed";
    return Response.json({ detail }, { status: 502 });
  }
}
