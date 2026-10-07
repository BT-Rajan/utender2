import { useEffect } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { EligibilityCheck, Offer, OpportunityListing, ProjectDetail, ServiceProviderProfile } from "@/api/types";
import { PageLoading } from "@/components/PageLoading";
import { ClarificationsPanel } from "@/components/ClarificationsPanel";
import { IneligibleNotice } from "@/components/ProviderEligibility";
import { ProviderRequirementView } from "@/components/ProviderRequirementView";
import { OfferForm } from "@/components/OfferForm";
import { useI18n } from "@/i18n/I18nContext";
import { outcomeText } from "@/components/ClosureOutcome";
import { money } from "@/lib/money";
import { fullDate, timeLeft } from "@/lib/format";
import { formatArea } from "@/lib/location";

interface AwardRecord {
  amount: string;
  service_provider_company_name: string | null;
  created_at: string;
}

function AwardOutcome({ projectId }: { projectId: string }) {
  const { t } = useI18n();
  const { data: award } = useQuery({
    queryKey: ["award", projectId],
    queryFn: () => apiFetch<AwardRecord>(`/projects/${projectId}/award`),
  });

  if (!award) return null;

  return (
    <p className="mt-3 font-mono text-xs text-navy">
      {t("service_provider.offer.awardedTo")} {award.service_provider_company_name ?? t("service_provider.offer.anotherServiceProvider")} at{" "}
      {money(award.amount)}
    </p>
  );
}

export function ServiceProviderOfferPage() {
  const { t } = useI18n();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const {
    data: project,
    isError: projectError,
  } = useQuery({
    queryKey: ["project", id],
    queryFn: () => apiFetch<ProjectDetail>(`/projects/${id}`),
    enabled: !!id,
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
  const { data: profile } = useQuery({
    queryKey: ["service-provider-profile"],
    queryFn: () => apiFetch<ServiceProviderProfile>("/service-provider/profile"),
    enabled: !!id && projectError,
  });
  const ineligible = projectError && eligibility && !eligibility.eligible;
  // Stage 4.4 follow-up: qualifies, but hasn't full marketplace access yet --
  // say what the opportunity is and how to open it, not just "not available".
  const needsAccess = projectError && eligibility?.eligible && !!eligibility.listing && !!profile && profile.marketplace_status !== "verified_active";
  useEffect(() => {
    if (projectError && (eligibilityError || (eligibility?.eligible && profile && !needsAccess))) {
      navigate("/service-provider/feed", {
        replace: true,
        state: { notice: t("service_provider.offer.notAvailableNotice") },
      });
    }
  }, [projectError, eligibility, eligibilityError, profile, needsAccess, navigate, t]);

  const { data: existingOffer } = useQuery({
    queryKey: ["my-offer", id],
    queryFn: () => apiFetch<Offer | null>(`/projects/${id}/offers/mine`),
    enabled: !!id,
  });

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
  const biddingClosed = project.status !== "open" || !!project.paused_at || new Date(project.bid_deadline) < new Date();

  return (
    <main className="max-w-4xl mx-auto px-5 py-8">
      <ProviderRequirementView project={project} closed={biddingClosed} />

      <div className="mb-6">
        {/* Stage 3.10: the same rule the server applies to new questions. */}
        <ClarificationsPanel projectId={project.id} role="service_provider" canAsk={project.tender_rules.questions_open}
          qaOpen={project.tender_rules.questions_open}
          closesAt={project.tender_rules.questions_close_at}
        />
      </div>

      {biddingClosed ? (
        <div className="border border-dashed border-border rounded p-6 text-sm text-steel">
          {project.paused_at ? t("postPub.pausedProviderBody") : outcomeText(t, project.status, project.closure_reason) ?? t("service_provider.offer.biddingClosedNotice")}
          {existingOffer && (
            <div className="mt-3 font-mono text-xs text-navy">
              {t("service_provider.offer.yourFinalOffer")} {money(existingOffer.amount, project.currency)} —{" "}
              {existingOffer.status === "submitted" ? t("service_provider.feed.bidPlaced") : t(`feed.offer_${existingOffer.status}`)}
            </div>
          )}
          {project.status === "awarded" && <AwardOutcome projectId={project.id} />}
          {(project.status === "no_award" || project.status === "canceled" || project.status === "expired") && (
            <p className="mt-3 font-mono text-xs text-steel-light">{t("closure.offersKept")}</p>
          )}
        </div>
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
