export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string,
    public details: Record<string, unknown> = {}) { super(message); }
}
/** Session credentials live in an HttpOnly cookie; API keys never reach this client. */
export async function api<T = Record<string, unknown>>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`/api/backend${path.startsWith("/") ? path : `/${path}`}`, {
    ...init, headers, cache: "no-store", credentials: "same-origin",
  });
  const data = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) {
    const err = data?.error;
    // Do not clear cookies or redirect on a late old-session response.
    throw new ApiError(response.status, err?.code ?? "REQUEST_FAILED", err?.message ?? "Request failed", err?.details ?? {});
  }
  return data as T;
}
