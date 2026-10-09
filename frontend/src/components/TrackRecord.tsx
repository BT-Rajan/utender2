import type { Offer } from "@/api/types";
import { useI18n } from "@/i18n/I18nContext";

// Stage 8.14: the provider's U-Tender track record beside its offer -- the
// server's own figures, for information only (offers are never ordered or
// judged by it). No history reads as "none yet", never as 0 stars; an
// average always comes with how many reviews it rests on.
export function TrackRecord({ offer }: { offer: Offer }) {
  const { t } = useI18n();
  const completed = offer.service_provider_completed_transactions ?? 0;
  const reviews = offer.service_provider_review_count ?? 0;
  if (offer.service_provider_completed_transactions == null && offer.service_provider_review_count == null) return null;
  return (
    <span className="block font-mono text-[10.5px] text-steel font-normal" data-testid="track-record">
      {completed === 0 && reviews === 0 ? (
        t("reputation.none")
      ) : (
        <>
          {t("reputation.completed").replace("{n}", String(completed))}
          {" · "}
          {reviews
            ? t("reputation.summary").replace("{avg}", Number(offer.service_provider_avg_rating ?? 0).toFixed(1)).replace("{n}", String(reviews))
            : t("reputation.noReviews")}
        </>
      )}
      {!!offer.completed_with_you && (
        <span className="block text-green" data-testid="completed-together">{t("previous.together").replace("{n}", String(offer.completed_with_you))}</span>
      )}
    </span>
  );
}
