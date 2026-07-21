export const BACKEND_URL = "https://fitvision.medaide.org";

export function adminHeaders(request: Request): HeadersInit {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const key = request.headers.get("X-Admin-Key");
  if (key) headers["X-Admin-Key"] = key;
  return headers;
}

export function forwardAdminKey(request: Request): HeadersInit {
  const headers: Record<string, string> = {};
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

export async function proxyBackendResponse(
  request: Request,
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers);
  const adminKey = request.headers.get("X-Admin-Key");
  if (adminKey) headers.set("X-Admin-Key", adminKey);

  const response = await fetch(`${BACKEND_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  const body = await response.text();
  return new Response(body, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("Content-Type") ?? "application/json",
    },
  });
}
