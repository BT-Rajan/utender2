import { serverNow } from "@/api/client";
// The interface language, as I18nContext sets it on <html lang>. Lets the
// plain helpers below follow the language without a hook.
// Requirements are in Kuwait, and their times are Kuwait times: shown so on
// every device, wherever it is set.
export const KUWAIT_TZ = "Asia/Kuwait";
export function deviceOutsideKuwait(): boolean {
  try {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return !!zone && zone !== KUWAIT_TZ && new Date().getTimezoneOffset() !== -180;
  } catch {
    return false;
  }
}

function uiLanguage(): string {
  return typeof document !== "undefined" && document.documentElement.lang === "ar" ? "ar" : "en";
}

export function timeRemaining(deadlineIso: string): string {
  const diffMs = new Date(deadlineIso).getTime() - serverNow();
  const ar = uiLanguage() === "ar";
  if (diffMs <= 0) return ar ? "انتهى الموعد" : "Deadline passed";
  const days = Math.floor(diffMs / 86_400_000);
  const hours = Math.floor((diffMs % 86_400_000) / 3_600_000);
  return ar ? `متبقٍ ${days} يوم و${hours} ساعة` : `${days}d ${hours}h remaining`;
}

// Short date and time in the interface language; the year is added when it
// isn't this year.
export function formatDeadline(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(uiLanguage() === "ar" ? "ar-KW" : "en-US", {
    timeZone: KUWAIT_TZ,
    month: "short",
    day: "numeric",
    ...(d.getFullYear() !== new Date().getFullYear() ? { year: "numeric" } : {}),
    hour: "numeric",
    minute: "2-digit",
  });
}

// A file size for people: 820 KB, 4.2 MB.
export function formatSize(bytes: number | null | undefined): string | null {
  if (bytes == null) return null;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function stars(rating: number): string {
  const full = Math.round(rating ?? 0);
  return "★".repeat(full) + "☆".repeat(5 - full);
}

// Stage 4.3/4.4: a deadline (or other moment) in full, in the interface
// language -- weekday, date (the year when it isn't this year) and time.
// The moment itself always comes from the server.
export function fullDate(iso: string, lang: string, withTime = true): string {
  const d = new Date(iso);
  return d.toLocaleString(lang === "ar" ? "ar-KW" : "en-GB", {
    timeZone: KUWAIT_TZ,
    weekday: "short",
    day: "numeric",
    month: "short",
    ...(d.getFullYear() !== new Date().getFullYear() ? { year: "numeric" } : {}),
    ...(withTime ? { hour: "numeric", minute: "2-digit" } : {}),
  });
}

// Time left before a deadline, translated ("feed.*" keys).
export function timeLeft(t: (key: string) => string, iso: string): string {
  const ms = new Date(iso).getTime() - serverNow();
  if (ms <= 0) return t("feed.closedNow");
  const days = Math.floor(ms / 86_400_000);
  const hours = Math.floor((ms % 86_400_000) / 3_600_000);
  return days > 0 ? t("feed.leftDays").replace("{d}", String(days)).replace("{h}", String(hours)) : t("feed.leftHours").replace("{h}", String(hours));
}
