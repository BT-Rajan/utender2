import { useState } from "react";
import { OpportunityCard } from "@/components/OpportunityCard";
import { Link, useLocation } from "react-router-dom";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { FeedPage, ServiceProviderProfile } from "@/api/types";
import { QueryError } from "@/components/QueryError";
import { useI18n } from "@/i18n/I18nContext";
import { KUWAIT_GOVERNORATES } from "@/lib/location";

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

  // Stage 4.1: a page at a time; the server decides what is available.
  const {
    data,
    isError,
    isPending,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ["service-provider-feed", search, trade, governorate, sort],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams();
      if (search.trim()) params.set("search", search.trim());
      if (trade) params.set("trade", trade);
      if (governorate) params.set("governorate", governorate);
      params.set("sort", sort);
      params.set("offset", String(pageParam));
      return apiFetch<FeedPage>(`/service-provider/feed?${params.toString()}`);
    },
    getNextPageParam: (last) => last.next_offset ?? undefined,
  });
  const projects = data?.pages.flatMap((p) => p.items);
  const hiddenIneligible = data?.pages[0]?.hidden_ineligible ?? 0;

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

      {!isError && !isPending && !projects?.length && (
        <div className="border border-dashed border-border rounded p-10 text-center text-sm text-steel" data-testid="feed-empty">
          {filtersActive ? t("service_provider.feed.noMatch") : t("service_provider.feed.noOpenProjects")}
          {hiddenIneligible > 0 && (
            <p className="mt-2 text-xs">
              {t("feed.hiddenIneligible").replace("{n}", String(hiddenIneligible))}{" "}
              <Link to="/service-provider/dashboard" className="text-blue underline">{t("feed.checkServices")}</Link>
            </p>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {projects?.map((p) => {
          const card = <OpportunityCard project={p} locked={!isSubscribed} />;

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

      {hasNextPage && (
        <div className="text-center mt-6">
          <button
            type="button"
            onClick={() => void fetchNextPage()}
            disabled={isFetchingNextPage}
            className="border border-navy text-navy hover:bg-navy hover:text-white disabled:opacity-60 text-xs font-semibold rounded px-5 py-2"
          >
            {isFetchingNextPage ? t("feed.loading") : t("feed.loadMore")}
          </button>
        </div>
      )}
    </main>
  );
}
