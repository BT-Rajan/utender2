export function timeRemaining(deadlineIso: string): string {
  const diffMs = new Date(deadlineIso).getTime() - Date.now();
  if (diffMs <= 0) return "Deadline passed";
  const days = Math.floor(diffMs / 86_400_000);
  const hours = Math.floor((diffMs % 86_400_000) / 3_600_000);
  return `${days}d ${hours}h remaining`;
}

export function formatDeadline(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
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
    weekday: "short",
    day: "numeric",
    month: "short",
    ...(d.getFullYear() !== new Date().getFullYear() ? { year: "numeric" } : {}),
    ...(withTime ? { hour: "numeric", minute: "2-digit" } : {}),
  });
}

// Time left before a deadline, translated ("feed.*" keys).
export function timeLeft(t: (key: string) => string, iso: string): string {
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return t("feed.closedNow");
  const days = Math.floor(ms / 86_400_000);
  const hours = Math.floor((ms % 86_400_000) / 3_600_000);
  return days > 0 ? t("feed.leftDays").replace("{d}", String(days)).replace("{h}", String(hours)) : t("feed.leftHours").replace("{h}", String(hours));
}
