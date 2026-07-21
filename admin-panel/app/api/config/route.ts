import { NextRequest } from "next/server";
import { proxyBackendResponse } from "@/lib/backend";

export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  try {
    return await proxyBackendResponse(request, "/admin/config");
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Failed to load configs";
    return Response.json({ detail }, { status: 502 });
  }
}
