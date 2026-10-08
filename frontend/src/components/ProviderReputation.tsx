import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";

interface Reputation {
  completed_transactions: number;
  review_count: number;
  avg_rating: number | null;
  recent_reviews: { rating: number; comment: string | null; created_at: string }[];
}

// Stage 8.7: a provider's U-Tender track record -- completed transactions and
// owner reviews, as the server computes them. Informational only; no history
// reads as "none yet", never as a 0-star rating.
export function ProviderReputation({ url }: { url: string }) {
  const { t, language } = useI18n();
  const { data } = useQuery({ queryKey: ["provider-reputation", url], queryFn: () => apiFetch<Reputation>(url) });
  if (!data) return null;
  return (
    <section className="border border-border rounded px-4 py-3 bg-white text-ink" data-testid="provider-reputation">
      <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-2">{t("reputation.heading")}</h3>
      {data.completed_transactions === 0 ? (
        <p className="text-sm text-steel">{t("reputation.none")}</p>
      ) : (
        <>
          <p className="text-sm">
            {t("reputation.completed").replace("{n}", String(data.completed_transactions))}
            {" · "}
            {data.avg_rating === null
              ? t("reputation.noReviews")
              : t("reputation.summary").replace("{avg}", data.avg_rating.toFixed(1)).replace("{n}", String(data.review_count))}
          </p>
          {data.recent_reviews.length > 0 && (
            <ul className="mt-2 grid gap-2">
              {data.recent_reviews.map((r, i) => (
                <li key={i} className="border-t border-border pt-2">
                  <span className="text-amber tracking-tight" aria-label={t("ownerReview.rating").replace("{n}", String(r.rating))}>
                    {"★".repeat(r.rating)}{"☆".repeat(5 - r.rating)}
                  </span>
                  {r.comment && <p className="text-sm text-steel mt-1 whitespace-pre-wrap break-words" dir="auto">{r.comment}</p>}
                  <div className="font-mono text-[10px] text-steel mt-1">{t("reputation.verified")} · {fullDate(r.created_at, language)}</div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      <p className="text-[11px] text-steel mt-2">{t("reputation.note")}</p>
    </section>
  );
}
