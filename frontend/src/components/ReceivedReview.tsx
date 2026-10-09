import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiFetch } from "@/api/client";
import { useConfirm } from "@/components/ConfirmDialog";
import { ErrorBanner } from "@/components/ErrorBanner";
import { ReportReview } from "@/components/ReportReview";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";

interface Received {
  rating: number;
  comment: string | null;
  created_at: string;
  response: string | null;
  response_at: string | null;
}

// Stage 8.9: the reviewed side's one, final response, shown under the review it answers.
export function ReviewResponse({ response, at, label, reportBase }: { response: string | null | undefined; at: string | null | undefined; label: string; reportBase?: string }) {
  const { language } = useI18n();
  if (!response) return null;
  return (
    <div className="mt-2 border-s-2 border-border ps-3" data-testid="review-response">
      <div className="font-mono text-[10px] uppercase text-steel">{label}</div>
      <p className="text-sm text-steel whitespace-pre-wrap break-words" dir="auto">{response}</p>
      {at && <div className="font-mono text-[10px] text-steel">{fullDate(at, language)}</div>}
      {reportBase && <ReportReview projectBase={reportBase} target="response" />}
    </div>
  );
}

// Stage 8.6: the review this side received on a completed transaction -- the
// rating, comment and date only, from the side's own "received" endpoint.
// Stage 8.9: with this side's one, final response, or the form to give it.
export function ReceivedReview({ url, from }: { url: string; from: string }) {
  const { t, language } = useI18n();
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const key = ["received-review", url];
  const { data: review } = useQuery({ queryKey: key, queryFn: () => apiFetch<Received | null>(url) });
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const respond = useMutation({
    mutationFn: () => apiFetch<Received>(`${url}/response`, { method: "POST", body: { response: text } }),
    onSuccess: (saved) => { setError(null); queryClient.setQueryData(key, saved); },
    onError: (e: Error) => { setError(e instanceof ApiError ? e.message : t("review.responseError")); queryClient.invalidateQueries({ queryKey: key }); },
  });
  if (!review) return null;
  return (
    <section className="mt-4 max-w-xl text-ink" data-testid="received-review">
      <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-2" dir="auto">{t("review.receivedHeading").replace("{party}", from)}</h3>
      <div className="bg-white border border-border rounded px-4 py-3">
        <span className="text-amber text-lg tracking-tight" aria-label={t("ownerReview.rating").replace("{n}", String(review.rating))}>
          {"★".repeat(review.rating)}{"☆".repeat(5 - review.rating)}
        </span>
        {review.comment && <p className="text-sm text-steel mt-1 whitespace-pre-wrap break-words" dir="auto">{review.comment}</p>}
        <div className="font-mono text-[10px] text-steel mt-1">{t("review.receivedOn")} {fullDate(review.created_at, language)}</div>
        {review.response ? (
          <ReviewResponse response={review.response} at={review.response_at} label={t("review.yourResponse")} />
        ) : (
          <form
            className="mt-3 grid gap-2"
            onSubmit={(ev) => {
              ev.preventDefault();
              void confirm({ title: t("review.respondConfirmTitle"), body: t("review.respondConfirmBody"), confirmLabel: t("review.respond") }).then((ok) => ok && respond.mutate());
            }}
          >
            <ErrorBanner message={error} />
            <textarea
              value={text}
              onChange={(ev) => setText(ev.target.value)}
              rows={2}
              maxLength={2000}
              dir="auto"
              aria-label={t("review.responsePlaceholder")}
              placeholder={t("review.responsePlaceholder")}
              className="w-full border border-border rounded px-3 py-2 text-sm"
            />
            <button type="submit" disabled={!text.trim() || respond.isPending} className="border border-navy text-navy text-xs font-semibold rounded px-3 py-1.5 w-fit disabled:opacity-60">
              {t("review.respond")}
            </button>
          </form>
        )}
        {/* Stage 8.15: abuse or private details -- not disagreement -- go to U-Tender. */}
        <ReportReview projectBase={url.replace(/\/review\/received$/, "")} target="review" />
      </div>
    </section>
  );
}
