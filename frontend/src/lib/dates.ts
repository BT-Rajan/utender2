import type { Project } from "@/api/types";

// The response deadline comes from the API as UTC ("...Z"). <input
// type="datetime-local"> works in the browser's local time, so convert both
// ways: an owner in Kuwait who picks 17:00 means 17:00 Kuwait time.
export function toLocalInputValue(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function localInputToUtcIso(value: string): string {
  return new Date(value).toISOString();
}

// Calendar dates ("YYYY-MM-DD") are shown as-is: they have no time of day.
function formatDay(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

// "Work: from 5 Nov 2026 · 45 days" -- null when the owner gave no timing.
export function formatWorkTiming(t: (key: string) => string, p: Pick<Project, "expected_start_date" | "expected_completion_date" | "expected_duration_days">): string | null {
  const parts = [
    p.expected_start_date ? t("dates.from").replace("{date}", formatDay(p.expected_start_date)) : null,
    p.expected_completion_date ? t("dates.until").replace("{date}", formatDay(p.expected_completion_date)) : null,
    p.expected_duration_days ? t("dates.days").replace("{n}", String(p.expected_duration_days)) : null,
  ].filter(Boolean);
  return parts.length ? `${t("dates.work")}: ${parts.join(" · ")}` : null;
}
