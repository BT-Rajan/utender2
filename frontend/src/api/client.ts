export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

async function parseError(res: Response): Promise<never> {
  let detail = res.statusText;
  try {
    const body = await res.json();
    detail = body.detail || detail;
  } catch {
    // non-JSON error body — fall back to statusText
  }
  throw new ApiError(res.status, detail);
}

let refreshPromise: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = fetch(`${API_URL}/auth/refresh`, { method: "POST", credentials: "include" })
      .then((res) => res.ok)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

// A thin fetch wrapper: cookies (httpOnly access/refresh tokens) ride
// along automatically via credentials:"include", JSON bodies are
// serialized, and a single 401 triggers one silent refresh-and-retry
// before giving up — mirrors the original app's reliance on
// Supabase's auto-refreshing session cookie.
export async function apiFetch<T>(
  path: string,
  options: { method?: string; body?: unknown; formData?: FormData; retry?: boolean; headers?: Record<string, string> } = {}
): Promise<T> {
  const { method = "GET", body, formData, retry = true, headers = {} } = options;

  const init: RequestInit = {
    method,
    credentials: "include",
    headers: { ...headers },
  };

  if (formData) {
    init.body = formData;
  } else if (body !== undefined) {
    init.headers = { ...headers, "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }

  const res = await fetch(`${API_URL}${path}`, init);

  if (res.status === 401 && retry) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      return apiFetch<T>(path, { ...options, retry: false });
    }
  }

  if (!res.ok) {
    return parseError(res);
  }

  if (res.status === 204) return undefined as T;

  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return res.json();
  }
  return (await res.blob()) as unknown as T;
}

// Stage 3.11: a draft save carries the version the page last saw, so a stale
// page (another tab or device) gets a clear refusal instead of overwriting
// newer work.
export function draftVersion(project: { version?: number | null }): Record<string, string> {
  return project.version != null ? { "If-Match": String(project.version) } : {};
}
