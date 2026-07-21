export const BACKEND_URL = "https://fitvision.medaide.org";

export function adminHeaders(request: Request): HeadersInit {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const key = request.headers.get("X-Admin-Key");
  if (key) headers["X-Admin-Key"] = key;
  return headers;
}

export async function backendJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? response.statusText);
  }
  return response.json() as Promise<T>;
}
