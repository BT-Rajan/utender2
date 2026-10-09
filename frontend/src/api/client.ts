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

// The language the interface is showing (I18nProvider keeps <html lang> in step).
function interfaceLanguage(): string {
  return typeof document !== "undefined" && document.documentElement.lang === "ar" ? "ar" : "en";
}

// Stage 9.13: the server answers an access gate with a bare code (the route
// guards act on the account state). Should one reach a message -- e.g. a
// subscription that lapsed while an offer was being prepared -- say what it means.
const ACCESS_CODES: Record<string, { en: string; ar: string }> = {
  payment_required: {
    en: "Your marketplace subscription isn't active, so offers can't be saved or sent. Open Subscription to renew or update your payment.",
    ar: "اشتراكك في السوق غير نشط، لذا لا يمكن حفظ العروض أو إرسالها. افتح صفحة الاشتراك للتجديد أو تحديث وسيلة الدفع.",
  },
  not_approved: {
    en: "Your account's verification isn't approved yet, so this isn't available. See your verification status for what's needed.",
    ar: "لم تتم الموافقة على توثيق حسابك بعد، لذا هذا غير متاح. راجع حالة التوثيق لمعرفة المطلوب.",
  },
};

async function parseError(res: Response): Promise<never> {
  let detail = res.statusText;
  try {
    const body = await res.json();
    detail = body.detail || detail;
  } catch {
    // non-JSON error body — fall back to statusText
  }
  if (typeof detail === "string" && ACCESS_CODES[detail]) detail = ACCESS_CODES[detail][interfaceLanguage() as "en" | "ar"];
  throw new ApiError(res.status, detail);
}

function unknownOutcome(): string {
  return interfaceLanguage() === "ar"
    ? "تعذر التأكد من حفظ هذا الإجراء. حدّث الصفحة لترى ما هو مسجل قبل المحاولة مرة أخرى."
    : "We couldn't confirm whether this went through. Refresh the page to see what is on record before trying again.";
}

function connectionLost(): string {
  return interfaceLanguage() === "ar" ? "تعذر الاتصال بـ U-Tender. تحقق من اتصالك ثم حاول مرة أخرى." : "Couldn't reach U-Tender. Check your connection and try again.";
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
// Stage 4.3 follow-up: the server's clock, from the time it sends with every
// response, so "time left" is counted from the clock that enforces deadlines.
let serverOffsetMs = 0;
function noteServerTime(value: string | null) {
  const server = Number(value);
  if (value && Number.isFinite(server)) serverOffsetMs = server - Date.now();
}
export function serverNow(): number {
  return Date.now() + serverOffsetMs;
}

export async function apiFetch<T>(
  path: string,
  options: { method?: string; body?: unknown; formData?: FormData; retry?: boolean; headers?: Record<string, string> } = {}
): Promise<T> {
  const { method = "GET", body, formData, retry = true, headers = {} } = options;

  const init: RequestInit = {
    method,
    credentials: "include",
    // The server sends its messages in the interface's language.
    headers: { "Accept-Language": interfaceLanguage(), ...headers },
  };

  if (formData) {
    init.body = formData;
  } else if (body !== undefined) {
    init.headers = { "Accept-Language": interfaceLanguage(), ...headers, "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }

  // Stage 9.8: a change whose request never got an answer (dropped connection,
  // timeout) or failed on the server may still have been saved. Say so, rather
  // than implying it didn't happen; the server refuses a repeat that would
  // double it, and a refresh shows what is on record.
  const writes = method !== "GET";
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(0, writes ? unknownOutcome() : connectionLost());
  }
  noteServerTime(res.headers.get("X-Server-Time"));
  if (writes && res.status >= 500) {
    throw new ApiError(res.status, unknownOutcome());
  }

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
