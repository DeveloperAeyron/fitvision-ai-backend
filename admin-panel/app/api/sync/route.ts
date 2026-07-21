import { BACKEND_URL } from "@/lib/backend";

export const runtime = "nodejs";

export async function GET() {
  try {
    const response = await fetch(`${BACKEND_URL}/sync/catalog`, {
      cache: "no-store",
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      return Response.json(
        { detail: body.detail ?? "Failed to load sync catalog" },
        { status: 502 },
      );
    }
    return Response.json(await response.json());
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Failed to load sync catalog";
    return Response.json({ detail }, { status: 502 });
  }
}
