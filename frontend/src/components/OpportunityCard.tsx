import type { Project } from "@/api/types";
import { eligibilitySummary, IneligibleNotice } from "@/components/ProviderEligibility";
import { useI18n } from "@/i18n/I18nContext";
import { deviceOutsideKuwait, formatDeadline, fullDate, timeLeft } from "@/lib/format";
import { formatWorkTiming } from "@/lib/dates";
import { formatArea } from "@/lib/location";

// One opportunity in the providers' list -- enough to decide whether to open
// it, not the requirement itself: no exact address, only the opening of the
// scope. Shared by the feed and the owner's preview (Stage 3.13).
export function OpportunityCard({ project, locked = false }: { project: Project; locked?: boolean }) {
  const { t, language } = useI18n();
  const timing = formatWorkTiming(t, project);
  const scope = [
    project.document_count ? t("feed.documents").replace("{n}", String(project.document_count)) : null,
    project.pricing_basis === "per_item" && project.item_count ? t("feed.items").replace("{n}", String(project.item_count)) : null,
    project.published_at ? t("feed.published").replace("{date}", fullDate(project.published_at, language, false)) : null,
  ].filter(Boolean);
  return (
    <div className="tblock rounded px-5 pt-4 relative overflow-hidden h-full" data-testid="opportunity-card">
      <div className="flex justify-between items-start gap-2">
        <div>
          <h3 dir="auto" className="font-display font-semibold text-[16.5px] mb-0.5">{project.title}</h3>
          <p className="text-[12.5px] text-steel mb-2">
            {formatArea(t, project.governorate, project.area)}
            {timing && <span className="block text-[11.5px]">{timing}</span>}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          {project.my_offer_status && (
            <span className="font-mono text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-green-tint text-green whitespace-nowrap">
              {project.my_offer_status === "submitted" ? t("service_provider.feed.bidPlaced") : t(`feed.offer_${project.my_offer_status}`)}
            </span>
          )}
          {project.tender_type === "sealed" && (
            <span className="font-mono text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-blue-tint text-steel whitespace-nowrap" title={t("feed.sealedHint")}>
              {t("feed.sealed")}
            </span>
          )}
        </div>
      </div>
      {project.summary && <p dir="auto" className="text-[13px] text-navy mb-2 line-clamp-3">{project.summary}</p>}
      {scope.length > 0 && <p className="text-[11.5px] text-steel mb-1.5">{scope.join(" · ")}</p>}
      <p className="font-mono text-xs text-blue">
        {project.paused_at ? (
          <span className="text-amber-dark uppercase">{t("postPub.pausedProvider").replace("{date}", formatDeadline(project.paused_at))}</span>
        ) : (
          timeLeft(t, project.bid_deadline)
        )}
      </p>
      <div className="tblock-strip mt-4">
        <div className="tblock-field">
          <span className="k">{t("service_provider.feed.deadline")}</span>
          <span className="v">
            {fullDate(project.bid_deadline, language)}
            {deviceOutsideKuwait() && <span className="block text-[10px] text-steel-light">{t("detail.kuwaitTime")}</span>}
          </span>
        </div>
        <div className="tblock-field">
          <span className="k">{t("service_provider.feed.trade")}</span>
          <span className="v">{project.trade || "—"}</span>
        </div>
        {project.pricing_basis && (
          <div className="tblock-field">
            <span className="k">{t("feed.pricing")}</span>
            <span className="v">{t(`feed.${project.pricing_basis}`)}</span>
          </div>
        )}
        <div className="tblock-field">
          <span className="k">{t("service_provider.feed.offersSoFar")}</span>
          <span className="v">{project.offer_count}</span>
        </div>
      </div>

      {/* Who may respond, when the owner narrowed it -- the conditions in one line. */}
      {project.conditions && (
        <p className="text-[11.5px] text-steel mt-2.5 mb-3" data-testid="card-conditions">
          <span className="font-semibold text-navy">{t("feed.whoCanRespond")}</span> {eligibilitySummary(t, project.conditions)}
          {project.eligible === true && <span className="text-green"> · {t("feed.youQualify")}</span>}
        </p>
      )}

      {project.eligible === false && (
        <div className="mt-3 mb-4">
          <IneligibleNotice reasons={project.ineligible_reasons ?? []} />
        </div>
      )}

      {locked && (
        <div className="absolute inset-0 bg-navy/90 flex flex-col items-center justify-center text-center gap-2.5 px-4">
          <div className="text-xl">🔒</div>
          <strong className="font-display text-white text-sm">{t("service_provider.feed.lockedTitle")}</strong>
          <p className="text-[11.5px] text-white/70 max-w-[220px]">{t("service_provider.feed.lockedDescription")}</p>
        </div>
      )}
    </div>
  );
}
