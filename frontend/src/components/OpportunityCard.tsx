import type { Project } from "@/api/types";
import { IneligibleNotice } from "@/components/ProviderEligibility";
import { useI18n } from "@/i18n/I18nContext";
import { formatDeadline, timeRemaining } from "@/lib/format";
import { formatWorkTiming } from "@/lib/dates";
import { formatArea } from "@/lib/location";

// One opportunity in the providers' list (what they see before opening it:
// no exact address, no scope). Shared by the feed and the owner's preview
// (Stage 3.13).
export function OpportunityCard({ project, locked = false }: { project: Project; locked?: boolean }) {
  const { t } = useI18n();
  return (
    <div className="tblock rounded px-5 pt-4 relative overflow-hidden h-full">
      <div className="flex justify-between items-start gap-2">
        <div>
          <h3 className="font-display font-semibold text-[16.5px] mb-0.5">{project.title}</h3>
          <p className="text-[12.5px] text-steel mb-3">
            {formatArea(t, project.governorate, project.area)}
            {formatWorkTiming(t, project) && <span className="block text-[11.5px]">{formatWorkTiming(t, project)}</span>}
          </p>
        </div>
        {project.my_offer_status && (
          <span className="font-mono text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-green-tint text-green whitespace-nowrap">
            {project.my_offer_status === "submitted" ? t("service_provider.feed.bidPlaced") : project.my_offer_status}
          </span>
        )}
      </div>
      <p className="font-mono text-xs text-blue">
        {project.paused_at ? <span className="text-amber-dark uppercase">{t("postPub.pausedProvider").replace("{date}", formatDeadline(project.paused_at))}</span> : timeRemaining(project.bid_deadline)}
      </p>
      <div className="tblock-strip mt-4">
        <div className="tblock-field">
          <span className="k">{t("service_provider.feed.deadline")}</span>
          <span className="v">{formatDeadline(project.bid_deadline)}</span>
        </div>
        <div className="tblock-field">
          <span className="k">{t("service_provider.feed.offersSoFar")}</span>
          <span className="v">{project.offer_count}</span>
        </div>
        <div className="tblock-field">
          <span className="k">{t("service_provider.feed.trade")}</span>
          <span className="v">{project.trade || "—"}</span>
        </div>
      </div>

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
