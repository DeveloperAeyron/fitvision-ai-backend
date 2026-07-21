import { NextRequest } from "next/server";
import { BACKEND_URL, adminHeaders, backendJson } from "@/lib/backend";

export const runtime = "nodejs";

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const body = await request.json();
    const exercise = await backendJson(`${BACKEND_URL}/admin/exercises/${id}`, {
      method: "PUT",
      headers: adminHeaders(request),
      body: JSON.stringify(body),
    });
    return Response.json(exercise);
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Failed to update exercise";
    return Response.json({ detail }, { status: 502 });
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const result = await backendJson(`${BACKEND_URL}/admin/exercises/${id}`, {
      method: "DELETE",
      headers: adminHeaders(request),
    });
    return Response.json(result);
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Failed to delete exercise";
    return Response.json({ detail }, { status: 502 });
  }
}
