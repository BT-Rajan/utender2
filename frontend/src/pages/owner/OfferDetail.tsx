import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { OwnerOffer } from "@/api/types";
import { PageLoading } from "@/components/PageLoading";
import { OfferHistory, OfferRecord } from "@/components/OfferPreview";
import { VersionView } from "@/components/PostPublication";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";

// Stage 6.4: one offer, for the requirement's owner to review -- exactly what
// the provider submitted (the stored record, nothing recalculated), from
// whom, in what state, and against which version of the requirement. The
// same record and display as the provider's own preview. Read-only: nothing
// here changes the offer; awarding stays on the requirement page.
export function OwnerOfferDetailPage() {
  const { t, language } = useI18n();
  const { id, offerId } = useParams<{ id: string; offerId: string }>();
  const { data, error, isPending } = useQuery({
    queryKey: ["owner-offer", id, offerId],
    queryFn: () => apiFetch<OwnerOffer>(`/owner/projects/${id}/offers/${offerId}`),
    enabled: !!id && !!offerId,
    // The offer as the server now holds it: the provider may revise or withdraw it meanwhile.
    refetchInterval: 60 * 1000,
    refetchOnWindowFocus: true,
  });
  const back = (
    <Link to={`/owner/projects/${id}`} className="font-mono text-xs text-blue underline">
      ← {t("ownerOffer.back")}
    </Link>
  );

  if (isPending) return <PageLoading />;
  if (error || !data) {
    // Not found: withdrawn, sealed until the deadline, suspended, or not this owner's.
    const gone = error instanceof ApiError && error.status === 404;
    return (
      <div className="max-w-3xl mx-auto px-4 py-8 grid gap-3">
        {back}
        <p role="alert" className="text-sm text-steel" data-testid="owner-offer-unavailable">
          {gone ? t("ownerOffer.unavailable") : t("ownerOffer.loadError")}
        </p>
      </div>
    );
  }

  const { offer, requirement } = data;
  const answered = offer.based_on_material_revision ?? 0;
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 grid gap-4" data-testid="owner-offer">
      {back}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h1 className="font-display text-xl text-navy" dir="auto">
          {t("ownerOffer.heading").replace("{provider}", data.provider_name ?? t("owner.projectDetail.theServiceProvider"))}
        </h1>
        <span
          className={`font-mono text-[10px] uppercase px-2 py-1 rounded-full ${offer.status === "approved" ? "bg-green-tint text-green" : offer.status === "submitted" ? "bg-blue-tint text-blue" : "bg-border text-steel"}`}
          data-testid="owner-offer-status"
        >
          {offer.status === "submitted" ? t("owner.projectDetail.offerReceived") : t(`feed.offer_${offer.status}`)}
        </span>
      </div>
      <p className="font-mono text-[11px] text-steel">
        {offer.submitted_at && `${t("owner.projectDetail.submittedOn")} ${fullDate(offer.submitted_at, language)}`}
        {offer.revision > 1 && ` · ${t("ownerOffer.revision").replace("{n}", String(offer.revision))} · ${t("ownerOffer.lastChanged")} ${fullDate(offer.updated_at, language)}`}
      </p>
      <p className="text-xs text-steel">{t("ownerOffer.readOnly")}</p>

      <OfferRecord
        requirement={requirement}
        offer={offer}
        providerName={data.provider_name}
        onCurrentVersion={data.on_current_version}
        viewer="owner"
        versionNote={
          <>
            <p className="text-xs text-steel mt-1" data-testid="owner-offer-answered">
              {t("ownerOffer.answered").replace("{n}", String(answered))}
            </p>
            {/* Stage 6.8: the requirement exactly as this offer answered it -- scope,
                dates and the documents current then (Stage 3.17); after an
                amendment, that earlier version, not today's. */}
            <VersionView
              projectId={requirement.id}
              number={answered}
              label={(data.on_current_version ? t("ownerOffer.asAnswered") : t("ownerOffer.viewAnswered")).replace("{n}", String(answered))}
            />
          </>
        }
      />
      <OfferHistory projectId={requirement.id} offerId={offer.id} currency={requirement.currency} />
    </div>
  );
}
