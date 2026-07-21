import { NextRequest } from "next/server";
import { BACKEND_URL, adminHeaders, backendJson } from "@/lib/backend";

export const runtime = "nodejs";

export async function GET() {
  try {
    const exercises = await backendJson<unknown[]>(`${BACKEND_URL}/exercises`);
    return Response.json(exercises);
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Failed to load exercises";
    return Response.json({ detail }, { status: 502 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const exercise = await backendJson(`${BACKEND_URL}/admin/exercises`, {
      method: "POST",
      headers: adminHeaders(request),
      body: JSON.stringify(body),
    });
    return Response.json(exercise, { status: 201 });
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Failed to create exercise";
    return Response.json({ detail }, { status: 502 });
  }
}
