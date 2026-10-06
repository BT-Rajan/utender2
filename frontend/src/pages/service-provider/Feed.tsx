import { useState } from "react";
import { IneligibleNotice } from "@/components/ProviderEligibility";
import { Link, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { ServiceProviderProfile, Project } from "@/api/types";
import { formatDeadline, timeRemaining } from "@/lib/format";
import { QueryError } from "@/components/QueryError";
import { useI18n } from "@/i18n/I18nContext";
import { formatWorkTiming } from "@/lib/dates";
import { KUWAIT_GOVERNORATES, formatArea } from "@/lib/location";

export function ServiceProviderFeedPage() {
  const { t } = useI18n();
  const location = useLocation() as { state?: { notice?: string } };
  const [search, setSearch] = useState("");
  const [trade, setTrade] = useState("");
  const [governorate, setGovernorate] = useState("");
  const [sort, setSort] = useState<"deadline" | "newest">("deadline");

  const { data: profile } = useQuery({
    queryKey: ["service-provider-profile"],
    queryFn: () => apiFetch<ServiceProviderProfile>("/service-provider/profile"),
  });

  const { data: trades } = useQuery({
    queryKey: ["service-provider-feed-trades"],
    queryFn: () => apiFetch<string[]>("/service-provider/feed/trades"),
  });

  const {
    data: projects,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["service-provider-feed", search, trade, governorate, sort],
    queryFn: () => {
      const params = new URLSearchParams();
      if (search.trim()) params.set("search", search.trim());
      if (trade) params.set("trade", trade);
      if (governorate) params.set("governorate", governorate);
      params.set("sort", sort);
      return apiFetch<Project[]>(`/service-provider/feed?${params.toString()}`);
    },
  });

  // marketplace_status is the backend's single derived source of truth for
  // full access (verification approved AND — real subscription OR admin
  // override), never the raw subscription_status alone: a service provider with
  // an admin-granted payment override has no Stripe subscription at all,
  // but is fully active.
  const isSubscribed = profile?.marketplace_status === "verified_active";
  const filtersActive = !!search.trim() || !!trade || !!governorate;

  return (
    <main className="max-w-5xl mx-auto px-5 py-8">
      <div className="mb-6">
        <span className="font-mono text-[10.5px] uppercase tracking-widest text-amber-dark block mb-1">{t("service_provider.feed.eyebrow")}</span>
        <h1 className="font-display text-2xl font-semibold text-navy mb-1">{t("service_provider.feed.heading")}</h1>
        <p className="text-[13.5px] text-steel">{sort === "newest" ? t("service_provider.feed.sortedNewest") : t("service_provider.feed.sortedClosest")}</p>
      </div>

      {location.state?.notice && (
        <p className="text-xs bg-blue-tint text-blue border border-blue rounded px-3 py-2.5 mb-4">{location.state.notice}</p>
      )}

      {!isSubscribed && (
        <div className="bg-blue-tint border border-blue rounded px-5 py-4 mb-6 flex items-center justify-between flex-wrap gap-3">
          <p className="text-sm text-navy">{t("service_provider.feed.subscribeBanner")}</p>
          <Link to="/service-provider/subscribe" className="bg-amber hover:bg-amber-dark text-white text-xs font-semibold rounded px-4 py-2 whitespace-nowrap">
            {t("service_provider.feed.viewPlans")}
          </Link>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2.5 mb-5">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t("service_provider.feed.searchPlaceholder")}
          className="border border-border rounded px-3 py-2 text-sm flex-1 min-w-[200px]"
        />
        <select
          value={trade}
          onChange={(e) => setTrade(e.target.value)}
          className="border border-border rounded px-3 py-2 text-sm font-mono"
        >
          <option value="">{t("service_provider.feed.allTrades")}</option>
          {trades?.map((tr) => (
            <option key={tr} value={tr}>
              {tr}
            </option>
          ))}
        </select>
        <select
          value={governorate}
          onChange={(e) => setGovernorate(e.target.value)}
          aria-label={t("location.governorate")}
          className="border border-border rounded px-3 py-2 text-sm font-mono"
        >
          <option value="">{t("location.allGovernorates")}</option>
          {KUWAIT_GOVERNORATES.map((g) => (
            <option key={g} value={g}>
              {t(`location.${g}`)}
            </option>
          ))}
        </select>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as "deadline" | "newest")}
          className="border border-border rounded px-3 py-2 text-sm font-mono"
        >
          <option value="deadline">{t("service_provider.feed.sortClosest")}</option>
          <option value="newest">{t("service_provider.feed.sortNewest")}</option>
        </select>
      </div>

      {isError && <QueryError onRetry={() => refetch()} />}

      {!isError && !projects?.length && (
        <div className="border border-dashed border-border rounded p-10 text-center text-sm text-steel">
          {filtersActive ? t("service_provider.feed.noMatch") : t("service_provider.feed.noOpenProjects")}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {projects?.map((p) => {
          const card = (
            <div className="tblock rounded px-5 pt-4 relative overflow-hidden h-full">
              <div className="flex justify-between items-start gap-2">
                <div>
                  <h3 className="font-display font-semibold text-[16.5px] mb-0.5">{p.title}</h3>
                  <p className="text-[12.5px] text-steel mb-3">
                    {formatArea(t, p.governorate, p.area)}
                    {formatWorkTiming(t, p) && <span className="block text-[11.5px]">{formatWorkTiming(t, p)}</span>}
                  </p>
                </div>
                {p.my_offer_status && (
                  <span className="font-mono text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-green-tint text-green whitespace-nowrap">
                    {p.my_offer_status === "submitted" ? t("service_provider.feed.bidPlaced") : p.my_offer_status}
                  </span>
                )}
              </div>
              <p className="font-mono text-xs text-blue">{timeRemaining(p.bid_deadline)}</p>
              <div className="tblock-strip mt-4">
                <div className="tblock-field">
                  <span className="k">{t("service_provider.feed.deadline")}</span>
                  <span className="v">{formatDeadline(p.bid_deadline)}</span>
                </div>
                <div className="tblock-field">
                  <span className="k">{t("service_provider.feed.offersSoFar")}</span>
                  <span className="v">{p.offer_count}</span>
                </div>
                <div className="tblock-field">
                  <span className="k">{t("service_provider.feed.trade")}</span>
                  <span className="v">{p.trade || "—"}</span>
                </div>
              </div>

              {p.eligible === false && (
                <div className="mt-3 mb-4">
                  <IneligibleNotice reasons={p.ineligible_reasons ?? []} />
                </div>
              )}

              {!isSubscribed && (
                <div className="absolute inset-0 bg-navy/90 flex flex-col items-center justify-center text-center gap-2.5 px-4">
                  <div className="text-xl">🔒</div>
                  <strong className="font-display text-white text-sm">{t("service_provider.feed.lockedTitle")}</strong>
                  <p className="text-[11.5px] text-white/70 max-w-[220px]">{t("service_provider.feed.lockedDescription")}</p>
                </div>
              )}
            </div>
          );

          // Stage 3.9: an ineligible provider sees why, not a link the server would refuse.
          return isSubscribed && (p.eligible !== false || p.my_offer_status) ? (
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
