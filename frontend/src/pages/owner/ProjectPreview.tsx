import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { ProjectDetail } from "@/api/types";
import { PageLoading } from "@/components/PageLoading";
import { OpportunityCard } from "@/components/OpportunityCard";
import { ProviderRequirementView } from "@/components/ProviderRequirementView";
import { QualityCheck, type QualityReport } from "@/components/QualityCheck";
import { OfferForm } from "@/components/OfferForm";
import { useI18n } from "@/i18n/I18nContext";

// Stage 3.13: the owner sees the requirement as a provider who may respond
// will receive it -- first as it appears in the list of opportunities, then
// opened. Built from the same requirement record and the same components the
// providers' pages use; nothing is published, and the draft stays visible
// only to the owner's side (GET /projects/{id} keeps refusing everyone else).
interface Audience {
  active_providers: number;
  eligible: number;
  excluded_by: Record<string, number>;
}

// Who the requirement's "who can respond" rules reach today -- counts only,
// from the same check providers are held to -- so an owner sees whether a
// condition shuts out more than intended before publishing.
function AudienceSummary({ audience }: { audience: Audience }) {
  const { t } = useI18n();
  const none = audience.eligible === 0;
  return (
    <section className={`border rounded px-4 py-3 mb-6 text-sm ${none ? "border-red/40 bg-red-tint/30" : "border-border bg-white"}`}>
      <h2 className="font-display font-semibold text-navy mb-1">{t("preview.audienceHeading")}</h2>
      <p className="text-navy">
        {t("preview.audienceCount").replace("{eligible}", String(audience.eligible)).replace("{total}", String(audience.active_providers))}
      </p>
      {Object.keys(audience.excluded_by).length > 0 && (
        <ul className="list-disc ps-5 text-[13px] text-steel mt-1">
          {Object.entries(audience.excluded_by).map(([code, n]) => (
            <li key={code}>{t(`preview.excluded_${code}`).replace("{count}", String(n))}</li>
          ))}
        </ul>
      )}
      {none && <p className="text-[13px] text-red mt-1">{t("preview.audienceNone")}</p>}
      <p className="text-[11px] text-steel-light mt-1">{t("preview.audienceNote")}</p>
    </section>
  );
}

export function OwnerProjectPreviewPage() {
  const { id } = useParams<{ id: string }>();
  const { t } = useI18n();
  const { data: project } = useQuery({
    queryKey: ["project", id],
    queryFn: () => apiFetch<ProjectDetail>(`/projects/${id}`),
    enabled: !!id,
  });
  const { data: quality } = useQuery({
    queryKey: ["quality", id, project?.version],
    queryFn: () => apiFetch<QualityReport>(`/projects/${id}/quality`),
    enabled: !!project && project.status === "draft",
  });
  const { data: audience } = useQuery({
    queryKey: ["audience", id, project?.version],
    queryFn: () => apiFetch<Audience>(`/projects/${id}/audience`),
    enabled: !!project,
  });
  if (!project) return <PageLoading />;

  const back = `/owner/projects/${project.id}`;
  return (
    <main className="max-w-4xl mx-auto px-5 py-8">
      <div className="border border-amber-dark/40 bg-amber/10 rounded px-4 py-3 mb-6 flex items-start justify-between flex-wrap gap-3">
        <div className="text-sm text-navy max-w-2xl">
          <strong className="font-display block">{t("preview.heading")}</strong>
          <span className="text-steel text-[13px]">{t(project.status === "draft" ? "preview.draftNote" : "preview.liveNote")}</span>
        </div>
        <Link to={back} className="bg-navy hover:bg-navy-deep text-white text-xs font-semibold rounded px-4 py-2 whitespace-nowrap">
          {t("preview.back")}
        </Link>
      </div>

      {project.status === "draft" && quality && !quality.ready && <QualityCheck report={quality} />}

      {audience && <AudienceSummary audience={audience} />}

      <h2 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-2">{t("preview.inList")}</h2>
      <p className="text-xs text-steel-light mb-2">{t("preview.inListHint")}</p>
      <div className="max-w-md mb-8 pointer-events-none">
        {/* Not yet published: no offers, and nothing to lock behind payment. */}
        <OpportunityCard project={{ ...project, offer_count: 0, my_offer_status: null, eligible: null, ineligible_reasons: [] }} />
      </div>

      <h2 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-2">{t("preview.opened")}</h2>
      <p className="text-xs text-steel-light mb-3">{t("preview.openedHint")}</p>
      <div className="border border-border rounded px-4 py-4 bg-white/50">
        <ProviderRequirementView project={project} closed={false} />
        <p className="text-xs text-steel-light border-t border-border pt-3 mb-3">{t("preview.thenForm")}</p>
        {/* The real form, read-only: what a provider fills in. Nothing can be sent. */}
        <OfferForm project={project} existingOffer={null} preview />
      </div>

      <div className="mt-6">
        <Link to={back} className="text-sm text-blue underline">
          {t("preview.back")}
        </Link>
      </div>
    </main>
  );
}
