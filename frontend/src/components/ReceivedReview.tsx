import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";

// Stage 8.6: the review this side received on a completed transaction -- the
// rating, comment and date only, from the side's own "received" endpoint.
export function ReceivedReview({ url, from }: { url: string; from: string }) {
  const { t, language } = useI18n();
  const { data: review } = useQuery({
    queryKey: ["received-review", url],
    queryFn: () => apiFetch<{ rating: number; comment: string | null; created_at: string } | null>(url),
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
      </div>
    </section>
  );
}
