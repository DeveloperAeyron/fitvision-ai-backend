import { NextRequest } from "next/server";
import { proxyBackendResponse } from "@/lib/backend";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  try {
    const body = await request.text();
    return await proxyBackendResponse(request, "/admin/config/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Preview failed";
    return Response.json({ detail }, { status: 502 });
  }
}
