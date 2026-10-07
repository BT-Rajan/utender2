import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError, serverNow } from "@/api/client";
import type { EligibilityCheck, Offer, OpportunityListing, ProjectDetail } from "@/api/types";
import { PageLoading } from "@/components/PageLoading";
import { ClarificationsPanel } from "@/components/ClarificationsPanel";
import { IneligibleNotice } from "@/components/ProviderEligibility";
import { ProviderRequirementView } from "@/components/ProviderRequirementView";
import { OfferForm } from "@/components/OfferForm";
import { OfferHistory, OfferPreview } from "@/components/OfferPreview";
import { OfferClarifications } from "@/components/OfferClarifications";
import { offerStatusLabel } from "@/components/ClosureOutcome";
import { SaveButton } from "@/components/SaveOpportunity";
import { useI18n } from "@/i18n/I18nContext";
import { outcomeText } from "@/components/ClosureOutcome";
import { money } from "@/lib/money";
import { fullDate, timeLeft } from "@/lib/format";
import { formatArea } from "@/lib/location";

interface AwardRecord {
  amount: string | null; // Stage 6.16: the winner's own side only
  service_provider_company_name: string | null;
  created_at: string;
  mine: boolean;
}

// Stage 6.16: the outcome as the award record holds it. The winner sees that
// their offer was awarded, and at what; every other bidder sees only that the
// requirement was awarded to a successful bidder -- not who, nor at what.
function AwardOutcome({ projectId }: { projectId: string }) {
  const { t } = useI18n();
  const { data: award } = useQuery({
    queryKey: ["award", projectId],
    queryFn: () => apiFetch<AwardRecord>(`/projects/${projectId}/award`),
  });

  if (!award) return null;

  return (
    <p className="mt-3 font-mono text-xs text-navy" data-testid="award-outcome">
      {award.mine
        ? `${t("service_provider.offer.yourOfferAwarded")} ${money(award.amount)}`
        : t("service_provider.offer.awardedToOther")}
    </p>
  );
}

export function ServiceProviderOfferPage() {
  const { t, language } = useI18n();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const {
    data: project,
    isError: projectError,
  } = useQuery({
    queryKey: ["project", id],
    queryFn: () => apiFetch<ProjectDetail>(`/projects/${id}`),
    enabled: !!id,
    // Stage 4.6: document links last an hour; keep them (and the state) fresh.
    refetchInterval: 20 * 60 * 1000,
    refetchOnWindowFocus: true,
  });

  // The backend 404s this endpoint identically whether the project doesn't
  // exist or this service provider doesn't currently have marketplace access to
  // it (unpaid, unverified, etc.) — by design, so the response can't be
  // used to enumerate projects. Land back on the feed with a plain notice
  // instead of spinning forever.
  // Stage 3.9: the full requirement is refused to a provider who isn't
  // eligible for it; ask why before falling back to the generic notice.
  const { data: eligibility, isError: eligibilityError } = useQuery({
    queryKey: ["eligibility", id],
    queryFn: () => apiFetch<EligibilityCheck>(`/projects/${id}/eligibility`),
    enabled: !!id && projectError,
    retry: false,
  });
  // Stage 4.5: when the requirement itself can't be opened, the server's
  // verdict says why -- ended or unavailable, not eligible (and what can be
  // fixed), or an action to take -- rather than a generic "not available".
  const verdict = projectError ? eligibility?.participation : undefined;
  const unavailable = verdict?.status === "unavailable";
  const ineligible = projectError && eligibility && !unavailable && !eligibility.eligible;
  const needsAccess = verdict?.status === "action_required" && verdict.action === "activate_access" && !!eligibility?.listing;
  useEffect(() => {
    if (projectError && (eligibilityError || (eligibility && verdict?.status === "can_participate"))) {
      navigate("/service-provider/feed", {
        replace: true,
        state: { notice: t("service_provider.offer.notAvailableNotice") },
      });
    }
  }, [projectError, eligibility, eligibilityError, verdict, navigate, t]);

  const { data: myOffer } = useQuery({
    queryKey: ["my-offer", id],
    queryFn: () => apiFetch<Offer | null>(`/projects/${id}/offers/mine`),
    enabled: !!id,
  });
  // Stage 5.2: the provider's one offer -- a draft until it is submitted. A
  // draft has never been put forward, so the form treats it as a new offer.
  const draft = myOffer?.status === "draft" ? myOffer : null;
  const existingOffer = draft ? null : myOffer;

  if (unavailable && eligibility) {
    return (
      <main className="max-w-2xl mx-auto px-5 py-8 grid gap-4">
        {eligibility.listing && <ListingSummary listing={eligibility.listing} />}
        <div className="border border-dashed border-border rounded p-6 text-sm text-steel" data-testid="participation">
          {verdict?.availability === "paused" ? t("postPub.pausedProviderBody") : verdict?.availability === "ended" ? t("eligibility.ended") : t("eligibility.unavailable")}
        </div>
        {eligibility.reasons.length > 0 && <IneligibleNotice reasons={eligibility.reasons} />}
        <button type="button" onClick={() => navigate("/service-provider/feed")} className="text-sm text-blue underline w-fit">
          {t("eligibility.backToFeed")}
        </button>
      </main>
    );
  }
  if (ineligible) {
    return (
      <main className="max-w-2xl mx-auto px-5 py-8 grid gap-4">
        {eligibility.listing && <ListingSummary listing={eligibility.listing} />}
        <IneligibleNotice reasons={eligibility.reasons} />
        <button type="button" onClick={() => navigate("/service-provider/feed")} className="text-sm text-blue underline w-fit">
          {t("eligibility.backToFeed")}
        </button>
      </main>
    );
  }
  if (needsAccess && eligibility?.listing) {
    return (
      <main className="max-w-2xl mx-auto px-5 py-8 grid gap-4">
        <ListingSummary listing={eligibility.listing} />
        <div className="bg-blue-tint border border-blue rounded px-5 py-4 flex items-center justify-between flex-wrap gap-3" data-testid="needs-access">
          <p className="text-sm text-navy">{t("detail.needsAccess")}</p>
          <Link to="/service-provider/subscribe" className="bg-amber hover:bg-amber-dark text-white text-xs font-semibold rounded px-4 py-2 whitespace-nowrap">
            {t("service_provider.feed.viewPlans")}
          </Link>
        </div>
        <button type="button" onClick={() => navigate("/service-provider/feed")} className="text-sm text-blue underline w-fit">
          {t("eligibility.backToFeed")}
        </button>
      </main>
    );
  }
  if (!project) return <PageLoading />;

  // Stage 3.15: an owner-paused requirement accepts nothing until resumed.
  // Stage 4.5: the server's availability, and its clock for a deadline that
  // passes while the page is open.
  const biddingClosed =
    (project.participation ? project.participation.availability !== "open" : project.status !== "open" || !!project.paused_at) ||
    new Date(project.bid_deadline).getTime() <= serverNow();

  return (
    <main className="max-w-4xl mx-auto px-5 py-8">
      {/* Stage 4.8: save it to come back to (only while it can be discovered). */}
      {(project.saved || project.participation?.availability === "open") && (
        <div className="flex justify-end mb-3">
          <SaveButton projectId={project.id} saved={!!project.saved} />
        </div>
      )}
      <ProviderRequirementView project={project} closed={biddingClosed} />

      <div className="mb-6">
        {/* Stage 3.10: the same rule the server applies to new questions. */}
        <ClarificationsPanel projectId={project.id} role="service_provider" canAsk={project.tender_rules.questions_open}
          qaOpen={project.tender_rules.questions_open}
          closesAt={project.tender_rules.questions_close_at}
        />
      </div>

      {/* Stage 4.5: the server's verdict for this provider, when they can take part. */}
      {project.participation?.status === "can_participate" && (
        <p className="mb-4 text-sm text-green font-semibold" data-testid="participation">
          ✓ {t("eligibility.canParticipate")}
        </p>
      )}
      {biddingClosed ? (
        <div className="border border-dashed border-border rounded p-6 text-sm text-steel">
          {project.paused_at ? t("postPub.pausedProviderBody") : outcomeText(t, project.status, project.closure_reason) ?? t("service_provider.offer.biddingClosedNotice")}
          {existingOffer && (
            <div className="mt-3 font-mono text-xs text-navy">
              {t("service_provider.offer.yourFinalOffer")} {money(existingOffer.amount, project.currency)} —{" "}
              {offerStatusLabel(t, existingOffer.status, project.status, project.closure_reason)}
            </div>
          )}
          {project.status === "awarded" && <AwardOutcome projectId={project.id} />}
          {/* Stage 5.16: the provider's own offer in full, as it stands -- read-only now offers have closed. */}
          {existingOffer && (
            <div className="mt-4 text-start">
              <OfferPreview projectId={project.id} readOnly />
              <OfferHistory projectId={project.id} currency={project.currency} />
              {/* Stage 6.10: the owner's clarification requests on this offer. */}
              <OfferClarifications projectId={project.id} role="provider" />
            </div>
          )}
          {(project.status === "no_award" || project.status === "canceled" || project.status === "expired") && (
            <p className="mt-3 font-mono text-xs text-steel-light">{t("closure.offersKept")}</p>
          )}
        </div>
      ) : existingOffer || project.participation?.started ? (
        <>
          {/* Stage 5.11: a submitted offer says so, when, and what can still be done. */}
          {existingOffer?.status === "submitted" && (
            <div className="border border-green bg-green/5 rounded px-4 py-3 mb-4 text-sm" data-testid="offer-submitted">
              <strong className="font-display text-navy block">✓ {t("submitOffer.submitted")}</strong>
              <span className="text-steel">
                {existingOffer.submitted_at && `${t("submitOffer.submittedAt")} ${fullDate(existingOffer.submitted_at, language)}`}
                {existingOffer.revision > 1 && ` · ${t("submitOffer.revision")} ${existingOffer.revision}`}
              </span>
              <p className="text-xs text-steel mt-1">
                {project.tender_type === "sealed" ? t("submitOffer.sealedNote") : t("submitOffer.visibleNote")} {t("submitOffer.canStill")}
              </p>
            </div>
          )}
          {/* Stage 5.14: a withdrawn offer says so; the existing rule lets it be resubmitted while offers are open. */}
          {existingOffer?.status === "withdrawn" && (
            <div className="border border-border bg-white rounded px-4 py-3 mb-4 text-sm" data-testid="offer-withdrawn">
              <strong className="font-display text-navy block">{t("feed.offer_withdrawn")}</strong>
              <span className="text-steel">{t("submitOffer.withdrawnAt")} {fullDate(existingOffer.updated_at, language)}</span>
              <p className="text-xs text-steel mt-1">{t("submitOffer.withdrawnNote")}</p>
            </div>
          )}
          {/* Stage 5.1: which requirement this offer is for. */}
          <p className="mb-4 text-sm text-navy" data-testid="preparing-for">
            {t("participate.preparingFor")} <strong dir="auto" className="font-display">{project.title}</strong>
            {draft && (
              <span className="block font-mono text-xs text-steel mt-1" data-testid="draft-status">
                {t("participate.draftStatus")}
                {project.participation?.started_at && ` · ${t("participate.draftStarted")} ${fullDate(project.participation.started_at, language)}`}
                {draft.draft_version ? ` · ${t("participate.lastSaved")} ${fullDate(draft.updated_at, language)}` : ""}
              </span>
            )}
          </p>
          {/* Stage 4.9 / 5.1: changed materially since they decided -- the offer
              is prepared against the current requirement only, once they've seen it. */}
          {!existingOffer && (project.material_revision ?? 0) > (project.participation?.seen_material_revision ?? 0) ? (
            <ChangedSinceDecided projectId={project.id} />
          ) : (
            <OfferForm project={project} existingOffer={existingOffer ?? null} draft={draft} />
          )}
          {existingOffer && existingOffer.revision > 1 && <OfferHistory projectId={project.id} currency={project.currency} />}
        </>
      ) : project.participation?.status === "can_participate" ? (
        <ParticipateStep projectId={project.id} />
      ) : (
        <OfferForm project={project} existingOffer={existingOffer ?? null} />
      )}
    </main>
  );
}

// What an opportunity is, at listing level (no address, no scope), for a
// provider who can't open the full requirement.
function ListingSummary({ listing }: { listing: OpportunityListing }) {
  const { t, language } = useI18n();
  return (
    <div className="bg-navy text-white rounded px-5 py-4" data-testid="listing-summary">
      <div dir="auto" className="font-display font-semibold text-base">{listing.title}</div>
      <div className="font-mono text-[11.5px] text-white/70 mt-0.5">
        {listing.trade && `${listing.trade} · `}
        {formatArea(t, listing.governorate, listing.area)} · {t("service_provider.offer.deadlineLabel")} {fullDate(listing.bid_deadline, language)}
      </div>
      <div className="flex gap-2 mt-2">
        {listing.tender_type === "sealed" && <span className="font-mono text-[10px] uppercase px-2.5 py-1 rounded-full bg-white/15">{t("feed.sealed")}</span>}
        <span className="font-mono text-[10px] uppercase px-2.5 py-1 rounded-full bg-white/15">
          {listing.paused ? t("postPub.pausedPill") : timeLeft(t, listing.bid_deadline)}
        </span>
      </div>
    </div>
  );
}

// Stage 4.9: the decision to take part -- the step from evaluating the
// opportunity to preparing an offer. The server checks every condition again
// when it's taken; nothing is sent to the owner until an offer is submitted.
function ParticipateStep({ projectId }: { projectId: string }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const go = useMutation({
    mutationFn: () => apiFetch(`/projects/${projectId}/participate`, { method: "POST" }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    },
    // A refusal says why (closed, paused, eligibility...); the page then shows the current state.
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : t("participate.error"));
      queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    },
  });
  return (
    <div className="border border-navy rounded px-5 py-4 bg-blue-tint/40" data-testid="participate-step">
      <strong className="font-display text-navy block">{t("participate.heading")}</strong>
      <p className="text-sm text-steel mt-1 mb-3">{t("participate.body")}</p>
      {error && <p className="text-xs bg-red-tint text-red border border-red rounded px-3 py-2 mb-3">{error}</p>}
      <button
        type="button"
        disabled={go.isPending}
        onClick={() => go.mutate()}
        className="bg-amber hover:bg-amber-dark disabled:opacity-60 text-white text-sm font-semibold rounded px-5 py-2.5"
      >
        {t("participate.button")}
      </button>
      <p className="text-xs text-steel-light mt-2">{t("participate.notNow")}</p>
    </div>
  );
}

function ChangedSinceDecided({ projectId }: { projectId: string }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const seen = useMutation({
    mutationFn: () => apiFetch(`/projects/${projectId}/participate`, { method: "POST" }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["project", projectId] }),
  });
  return (
    <div className="border border-amber-dark/40 bg-amber/10 rounded px-4 py-3 mb-4 text-sm" data-testid="changed-since">
      <strong className="font-display text-navy block">{t("participate.changedHeading")}</strong>
      <p className="text-steel">{t("participate.changedBody")}</p>
      <p className="text-steel mt-1">{t("participate.reviewFirst")}</p>
      <button type="button" disabled={seen.isPending} onClick={() => seen.mutate()} className="mt-2 border border-navy text-navy text-xs font-semibold rounded px-3 py-1.5">
        {t("participate.reviewed")}
      </button>
    </div>
  );
}
