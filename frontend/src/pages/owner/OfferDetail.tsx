import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { OwnerOffer } from "@/api/types";
import { PageLoading } from "@/components/PageLoading";
import { OfferHistory, OfferRecord } from "@/components/OfferPreview";
import { OfferClarifications } from "@/components/OfferClarifications";
import { EvaluationNotes } from "@/components/EvaluationNotes";
import { VersionView } from "@/components/PostPublication";
import { ProviderReputation } from "@/components/ProviderReputation";
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
  const queryClient = useQueryClient();
  // Stage 6.12: the owner side's private shortlist -- not an award.
  const shortlist = useMutation({
    mutationFn: (on: boolean) => apiFetch(`/owner/projects/${id}/offers/${offerId}/shortlist`, { method: on ? "PUT" : "DELETE" }),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["owner-offer", id, offerId] });
      queryClient.invalidateQueries({ queryKey: ["owner-offers", id] });
    },
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
      {(offer.shortlisted || (offer.status === "submitted" && (requirement.status === "closed" || requirement.status === "under_evaluation"))) && (
        <div className="border border-border rounded px-4 py-3 text-sm flex flex-wrap items-center gap-3" data-testid="owner-offer-shortlist">
          {offer.shortlisted && <span className="font-mono text-[10px] uppercase px-2 py-1 rounded-full bg-amber/10 text-amber-dark">★ {t("shortlist.badge")}</span>}
          {offer.status === "submitted" && (requirement.status === "closed" || requirement.status === "under_evaluation") && (
            <button
              type="button"
              disabled={shortlist.isPending}
              onClick={() => shortlist.mutate(!offer.shortlisted)}
              className="border border-navy text-navy text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-60"
            >
              {offer.shortlisted ? t("shortlist.remove") : t("shortlist.add")}
            </button>
          )}
          <span className="text-xs text-steel basis-full">{t("shortlist.note")}</span>
          {shortlist.error && <span role="alert" className="text-xs text-red basis-full">{(shortlist.error as Error).message}</span>}
        </div>
      )}

      {/* Stage 8.7: the provider's U-Tender track record, for information. */}
      <ProviderReputation url={`/owner/projects/${requirement.id}/offers/${offer.id}/reputation`} />

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
      {/* Stage 6.11: the owner side's own private notes on this offer. */}
      <EvaluationNotes projectId={requirement.id} offerId={offer.id} />
      {/* Stage 6.10: clarifying this offer while it is being evaluated. */}
      <OfferClarifications
        projectId={requirement.id}
        offerId={offer.id}
        role="owner"
        canAsk={offer.status === "submitted" && (requirement.status === "closed" || requirement.status === "under_evaluation")}
      />
    </div>
  );
}
