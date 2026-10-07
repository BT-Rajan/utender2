import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { ProjectDetail } from "@/api/types";
import { PageLoading } from "@/components/PageLoading";
import { OpportunityCard } from "@/components/OpportunityCard";
import { ProviderRequirementView } from "@/components/ProviderRequirementView";
import { QualityCheck, type QualityReport } from "@/components/QualityCheck";
import { useI18n } from "@/i18n/I18nContext";

// Stage 3.13: the owner sees the requirement as a provider who may respond
// will receive it -- first as it appears in the list of opportunities, then
// opened. Built from the same requirement record and the same components the
// providers' pages use; nothing is published, and the draft stays visible
// only to the owner's side (GET /projects/{id} keeps refusing everyone else).
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
        <p className="text-xs text-steel-light border-t border-border pt-3">{t("preview.thenForm")}</p>
      </div>

      <div className="mt-6">
        <Link to={back} className="text-sm text-blue underline">
          {t("preview.back")}
        </Link>
      </div>
    </main>
  );
}
