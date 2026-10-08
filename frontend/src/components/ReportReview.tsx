import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ApiError, apiFetch } from "@/api/client";
import { useI18n } from "@/i18n/I18nContext";

const REASONS = ["abusive", "private_information", "not_about_this_transaction", "other"] as const;

// Stage 8.15: report the review your side received, or the response to your
// side's review, for U-Tender to look at. Nothing changes until an admin
// decides; to answer a review you disagree with, respond to it instead.
export function ReportReview({ projectBase, target }: { projectBase: string; target: "review" | "response" }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<(typeof REASONS)[number]>("abusive");
  const [note, setNote] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const send = useMutation({
    mutationFn: () => apiFetch(`${projectBase}/review-reports`, { method: "POST", body: { target, reason, note: note || null } }),
    onSuccess: () => setDone(t("report.sent")),
    onError: (e: Error) => setDone(e instanceof ApiError ? e.message : t("report.error")),
  });
  if (done) return <p className="text-xs text-amber-dark mt-2" role="status" data-testid="report-done">{done}</p>;
  if (!open)
    return (
      <button type="button" onClick={() => setOpen(true)} className="text-xs text-steel underline mt-2" data-testid="report-open">
        {t(target === "review" ? "report.reportReview" : "report.reportResponse")}
      </button>
    );
  return (
    <form
      className="mt-2 grid gap-2 text-sm"
      onSubmit={(ev) => {
        ev.preventDefault();
        send.mutate();
      }}
    >
      <p className="text-xs text-steel">{t("report.explain")}</p>
      <select value={reason} onChange={(ev) => setReason(ev.target.value as (typeof REASONS)[number])} className="border border-border rounded px-2 py-1.5 text-sm w-fit" aria-label={t("report.reason")}>
        {REASONS.map((r) => (
          <option key={r} value={r}>{t(`report.reasons.${r}`)}</option>
        ))}
      </select>
      <textarea value={note} onChange={(ev) => setNote(ev.target.value)} rows={2} maxLength={500} dir="auto" placeholder={t("report.note")} aria-label={t("report.note")} className="w-full border border-border rounded px-3 py-2 text-sm" />
      <div className="flex gap-2">
        <button type="submit" disabled={send.isPending} className="border border-navy text-navy text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-60">{t("report.submit")}</button>
        <button type="button" onClick={() => setOpen(false)} className="text-xs text-steel underline">{t("report.cancel")}</button>
      </div>
    </form>
  );
}
