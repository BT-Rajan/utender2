import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { Project, ServiceProviderProfile } from "@/api/types";
import { OpportunityCard } from "@/components/OpportunityCard";
import { QueryError } from "@/components/QueryError";
import { useSaveToggle } from "@/components/SaveOpportunity";
import { useI18n } from "@/i18n/I18nContext";

// Stage 4.8: the opportunities a provider saved to come back to, each as the
// feed's card, as it stands now (from the server): still open first, then
// those that have ended. Opening one leads to the requirement itself.
export function ServiceProviderSavedPage() {
  const { t } = useI18n();
  const toggle = useSaveToggle();
  const { data: saved, isError, isPending, refetch } = useQuery({
    queryKey: ["saved-opportunities"],
    queryFn: () => apiFetch<Project[]>("/service-provider/saved"),
    refetchOnWindowFocus: true,
  });
  const { data: profile } = useQuery({
    queryKey: ["service-provider-profile"],
    queryFn: () => apiFetch<ServiceProviderProfile>("/service-provider/profile"),
  });
  const isSubscribed = profile?.marketplace_status === "verified_active";
  const unsave = (id: string) => toggle.mutate({ projectId: id, save: false });

  return (
    <main className="max-w-5xl mx-auto px-5 py-8">
      <div className="mb-6 flex items-end justify-between flex-wrap gap-3">
        <div>
          <span className="font-mono text-[10.5px] uppercase tracking-widest text-amber-dark block mb-1">{t("service_provider.feed.eyebrow")}</span>
          <h1 className="font-display text-2xl font-semibold text-navy mb-1">{t("saved.heading")}</h1>
          <p className="text-[13.5px] text-steel">{t("saved.intro")}</p>
        </div>
        <Link to="/service-provider/feed" className="text-sm text-blue underline">{t("saved.backToFeed")}</Link>
      </div>

      {isError && <QueryError onRetry={() => refetch()} />}
      {!isError && !isPending && !saved?.length && (
        <div className="border border-dashed border-border rounded p-10 text-center text-sm text-steel" data-testid="saved-empty">
          {t("saved.empty")}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {saved?.map((p) => {
          if (p.availability === "unavailable") {
            // Hidden by U-Tender: only that it is unavailable.
            return (
              <div key={p.id} className="tblock rounded px-5 py-4 text-sm text-steel flex items-start justify-between gap-3" data-testid="saved-unavailable">
                <span>{t("saved.unavailable")}</span>
                <button type="button" onClick={() => unsave(p.id)} className="text-xs text-blue underline whitespace-nowrap">
                  {t("saved.remove")}
                </button>
              </div>
            );
          }
          const card = <OpportunityCard project={p} locked={!isSubscribed} onToggleSave={() => unsave(p.id)} />;
          // An ended requirement opens only for a provider who took part in it.
          const opens = isSubscribed && (p.availability !== "ended" || !!p.my_offer_status) && (p.eligible !== false || !!p.my_offer_status);
          return opens ? (
            <Link key={p.id} to={`/service-provider/projects/${p.id}/offer`}>
              {card}
            </Link>
          ) : (
            <div key={p.id}>{card}</div>
          );
        })}
      </div>
    </main>
  );
}
