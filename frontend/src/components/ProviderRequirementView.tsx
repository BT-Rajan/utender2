import { API_URL } from "@/api/client";
import type { ProjectDetail } from "@/api/types";
import { RequirementItemsView } from "@/components/RequirementItems";
import { ResponseRequirementsSummary } from "@/components/ResponseRequirements";
import { ParticipationRules } from "@/components/TenderRules";
import { eligibilitySummary } from "@/components/ProviderEligibility";
import { AmendmentsList } from "@/components/PostPublication";
import { useI18n } from "@/i18n/I18nContext";
import { formatDeadline, timeRemaining } from "@/lib/format";
import { formatWorkTiming } from "@/lib/dates";
import { sortDocuments } from "@/lib/documents";
import { formatArea } from "@/lib/location";

// Stage 3.13: the requirement exactly as a provider who may respond sees it.
// One component, fed by the one requirement record (GET /projects/{id}, the
// same serializer for owner and provider), rendered on the provider's page
// and in the owner's preview -- so the owner can't see one thing and the
// provider another.
export function ProviderRequirementView({ project, closed }: { project: ProjectDetail; closed: boolean }) {
  const { t } = useI18n();
  return (
    <>
      <div className="bg-navy text-white rounded px-5 py-4 mb-6 flex items-center justify-between flex-wrap gap-2.5">
        <div>
          <div className="font-display font-semibold text-base">{project.title}</div>
          <div className="font-mono text-[11.5px] text-white/70 mt-0.5">
            {project.trade && `${project.trade} · `}
            {formatArea(t, project.governorate, project.area)}
            {project.address && ` — ${project.address}`} · {t("service_provider.offer.deadlineLabel")} {formatDeadline(project.bid_deadline)}
            {formatWorkTiming(t, project) && ` · ${formatWorkTiming(t, project)}`}
          </div>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-wide px-2.5 py-1 rounded-full bg-white/15">
          {project.paused_at && project.status === "open" ? t("postPub.pausedPill") : closed ? t("service_provider.offer.closed") : timeRemaining(project.bid_deadline)}
        </span>
      </div>

      {project.paused_at && (
        <div className="border border-amber-dark/40 bg-amber/10 rounded px-4 py-3 mb-6 text-sm text-navy">
          <strong className="font-display block">{t("postPub.pausedProvider").replace("{date}", formatDeadline(project.paused_at))}</strong>
          {project.pause_reason && <span className="block">{project.pause_reason}</span>}
          <span className="block text-steel text-[13px]">{t("postPub.pausedProviderBody")}</span>
        </div>
      )}
      {project.published_at && <AmendmentsList projectId={project.id} />}

      {project.description && (
        <div className="mb-6 text-sm text-steel">
          <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-1">{t("service_provider.offer.scope")}</h3>
          {/* Keep the owner's line breaks: lists of tasks, quantities, inclusions. */}
          <div className="whitespace-pre-wrap break-words">{project.description}</div>
        </div>
      )}

      <RequirementItemsView project={project} />

      <div className="mb-6">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
          <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy">{t("service_provider.offer.drawings")}</h3>
          {project.drawings.length > 1 && (
            <a href={`${API_URL}/projects/${project.id}/drawings-zip`} className="font-mono text-[11px] text-blue underline">
              {t("service_provider.offer.downloadZip")}
            </a>
          )}
        </div>
        {project.drawings.length ? (
          <ul className="flex flex-wrap gap-2">
            {sortDocuments(project.drawings).map((d) => (
              <li key={d.id} className="flex flex-col">
                <span className="font-mono text-[10px] uppercase text-steel mb-0.5">
                  {t(`documents.${d.category}`)} · {d.is_required ? t("documents.essential") : t("documents.supplementary")}
                </span>
                {d.url ? (
                  <a href={d.url} target="_blank" rel="noreferrer" className="font-mono text-xs text-blue underline bg-blue-tint px-3 py-1.5 rounded">
                    {d.file_name}
                    {d.revision > 1 && <span className="text-blue/60"> · v{d.revision}</span>}
                  </a>
                ) : (
                  <span className="font-mono text-xs text-steel">{d.file_name}</span>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-steel-light">{t("service_provider.offer.noDrawings")}</p>
        )}
      </div>

      {!closed && (
        <p className="mb-3 text-[12.5px] text-steel">
          <span className="font-mono text-[11px] uppercase tracking-wide text-navy">{t("eligibility.rulesLine")}:</span>{" "}
          {eligibilitySummary(t, project.provider_eligibility)}
        </p>
      )}
      {!closed && <ParticipationRules project={project} />}
      {!closed && <ResponseRequirementsSummary project={project} />}

    </>
  );
}
