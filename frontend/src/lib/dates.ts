import type { Project } from "@/api/types";

// The response deadline comes from the API as UTC ("...Z") and is shown
// everywhere in Kuwait time (lib/format.ts). <input type="datetime-local">
// has no timezone, so read and write it as Kuwait time too (UTC+3, no
// daylight saving) -- not the device's clock: an owner who picks 17:00 means
// 17:00 in Kuwait even when their phone is set to another timezone.
const KUWAIT_OFFSET_MS = 3 * 60 * 60 * 1000;

export function toLocalInputValue(iso: string): string {
  const d = new Date(new Date(iso).getTime() + KUWAIT_OFFSET_MS);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

export function localInputToUtcIso(value: string): string {
  const withSeconds = value.length === 16 ? `${value}:00` : value;
  return new Date(`${withSeconds}+03:00`).toISOString();
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
