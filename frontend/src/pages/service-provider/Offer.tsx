import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { EligibilityCheck, Offer, ProjectDetail } from "@/api/types";
import { PageLoading } from "@/components/PageLoading";
import { ClarificationsPanel } from "@/components/ClarificationsPanel";
import { IneligibleNotice } from "@/components/ProviderEligibility";
import { ProviderRequirementView } from "@/components/ProviderRequirementView";
import { OfferForm } from "@/components/OfferForm";
import { useI18n } from "@/i18n/I18nContext";
import { money } from "@/lib/money";

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
  const ineligible = projectError && eligibility && !eligibility.eligible;
  useEffect(() => {
    if (projectError && (eligibilityError || eligibility?.eligible)) {
      navigate("/service-provider/feed", {
        replace: true,
        state: { notice: t("service_provider.offer.notAvailableNotice") },
      });
    }
  }, [projectError, eligibility, eligibilityError, navigate, t]);

  const { data: existingOffer } = useQuery({
    queryKey: ["my-offer", id],
    queryFn: () => apiFetch<Offer | null>(`/projects/${id}/offers/mine`),
    enabled: !!id,
  });

  if (ineligible) {
    return (
      <main className="max-w-2xl mx-auto px-5 py-8 grid gap-4">
        <IneligibleNotice reasons={eligibility.reasons} />
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
          {project.paused_at ? t("postPub.pausedProviderBody") : t("service_provider.offer.biddingClosedNotice")}
          {existingOffer && (
            <div className="mt-3 font-mono text-xs text-navy">
              {t("service_provider.offer.yourFinalOffer")} {money(existingOffer.amount, project.currency)} — status: {existingOffer.status}
            </div>
          )}
          {project.status === "awarded" && <AwardOutcome projectId={project.id} />}
          {project.status === "no_award" && (
            <p className="mt-3 font-mono text-xs text-steel-light">{t("service_provider.offer.noAwardNotice")}</p>
          )}
        </div>
      ) : (
        <OfferForm project={project} existingOffer={existingOffer ?? null} />
      )}
    </main>
  );
}
