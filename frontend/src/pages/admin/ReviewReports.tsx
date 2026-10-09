import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiFetch } from "@/api/client";
import { ErrorBanner } from "@/components/ErrorBanner";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";

interface ReportRow {
  id: string;
  target: "review" | "response";
  reason: string;
  note: string | null;
  status: "open" | "kept" | "hidden";
  created_at: string;
  resolved_at: string | null;
  resolution_note: string | null;
  reported_by: "owner" | "service_provider";
  direction: string;
  rating: number;
  comment: string | null;
  response: string | null;
  review_hidden: boolean;
  response_hidden: boolean;
  project_title: string;
  owner_name: string | null;
  provider_name: string | null;
}

// Stage 8.15: reported reviews and responses -- keep what was reported, or
// hide it (it stops being shown, and a hidden review stops counting). The
// record and the audit trail remain.
export function AdminReviewReportsPage() {
  const { t, language } = useI18n();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const { data } = useQuery({ queryKey: ["admin-review-reports"], queryFn: () => apiFetch<ReportRow[]>("/admin/review-reports") });
  const decide = useMutation({
    mutationFn: (v: { id: string; decision: "keep" | "hide" }) => apiFetch(`/admin/review-reports/${v.id}/decision`, { method: "POST", body: { decision: v.decision } }),
    onSuccess: () => { setError(null); queryClient.invalidateQueries({ queryKey: ["admin-review-reports"] }); },
    onError: (e: Error) => { setError(e instanceof ApiError ? e.message : t("report.error")); queryClient.invalidateQueries({ queryKey: ["admin-review-reports"] }); },
  });
  return (
    <main className="max-w-5xl mx-auto px-5 py-8 text-ink">
      <h1 className="font-display text-2xl font-semibold text-navy mb-4">{t("admin.nav.reviewReports")}</h1>
      <ErrorBanner message={error} />
      {!data?.length && <p className="text-sm text-steel">{t("report.adminNone")}</p>}
      <ul className="grid gap-3">
        {data?.map((r) => (
          <li key={r.id} className="bg-white border border-border rounded px-4 py-3 text-sm" data-testid="review-report">
            <div className="font-mono text-[10.5px] uppercase text-steel">
              {r.status} · {t(`report.reasons.${r.reason}`)} · {t(r.target === "review" ? "report.targetReview" : "report.targetResponse")} · {fullDate(r.created_at, language)}
            </div>
            <div className="mt-1" dir="auto">{r.project_title} — {r.owner_name ?? "—"} / {r.provider_name ?? "—"}</div>
            <div className="mt-1">{"★".repeat(r.rating)}{"☆".repeat(5 - r.rating)} <span className="whitespace-pre-wrap break-words" dir="auto">{r.comment}</span></div>
            {r.response && <div className="mt-1 text-steel whitespace-pre-wrap break-words" dir="auto">↳ {r.response}</div>}
            {r.note && <div className="mt-1 text-xs text-steel whitespace-pre-wrap break-words" dir="auto">{t("report.note")}: {r.note}</div>}
            {r.status === "open" ? (
              <div className="mt-2 flex gap-2">
                <button type="button" disabled={decide.isPending} onClick={() => decide.mutate({ id: r.id, decision: "keep" })} className="border border-navy text-navy text-xs font-semibold rounded px-3 py-1.5">{t("report.keep")}</button>
                <button type="button" disabled={decide.isPending} onClick={() => decide.mutate({ id: r.id, decision: "hide" })} className="border border-red text-red text-xs font-semibold rounded px-3 py-1.5">{t("report.hide")}</button>
              </div>
            ) : (
              r.resolved_at && <div className="mt-1 font-mono text-[10px] text-steel">{fullDate(r.resolved_at, language)}</div>
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}
