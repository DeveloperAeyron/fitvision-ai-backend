import { NextRequest } from "next/server";
import { proxyBackendResponse } from "@/lib/backend";

export const runtime = "nodejs";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ key: string }> },
) {
  const { key } = await params;
  try {
    return await proxyBackendResponse(request, `/admin/config/${key}`);
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Failed to load config";
    return Response.json({ detail }, { status: 502 });
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ key: string }> },
) {
  const { key } = await params;
  try {
    const body = await request.text();
    return await proxyBackendResponse(request, `/admin/config/${key}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body,
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Failed to save config";
    return Response.json({ detail }, { status: 502 });
  }
}
