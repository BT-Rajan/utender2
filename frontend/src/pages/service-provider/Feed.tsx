import { useEffect, useState } from "react";
import { OpportunityCard } from "@/components/OpportunityCard";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { FeedPage, ServiceProviderProfile } from "@/api/types";
import { QueryError } from "@/components/QueryError";
import { useI18n } from "@/i18n/I18nContext";
import { KUWAIT_GOVERNORATES } from "@/lib/location";
import { useCategories } from "@/components/CategoryField";
import { useSaveToggle } from "@/components/SaveOpportunity";

type Sort = "deadline" | "deadline_latest" | "newest" | "relevance";
const FILTER_KEYS = ["search", "category_id", "governorate", "min_days", "my_services", "my_areas", "accepting"] as const;

export function ServiceProviderFeedPage() {
  const { t } = useI18n();
  const location = useLocation() as { state?: { notice?: string } };
  // Stage 4.2: the query lives in the address, so it survives opening an
  // opportunity and coming back, a reload, or a shared link.
  const [params, setParams] = useSearchParams();
  const search = params.get("search") ?? "";
  const category = params.get("category_id") ?? "";
  const governorate = params.get("governorate") ?? "";
  const minDays = params.get("min_days") ?? "";
  const myServices = params.get("my_services") === "1";
  const myAreas = params.get("my_areas") === "1";
  const accepting = params.get("accepting") === "1";
  // With a search, the best text matches come first unless another order is chosen.
  const sort = (params.get("sort") as Sort | null) ?? (search ? "relevance" : "deadline");
  const [searchInput, setSearchInput] = useState(search);
  const { data: categories } = useCategories();

  function update(changes: Record<string, string | boolean>) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [k, v] of Object.entries(changes)) {
          const value = v === true ? "1" : v === false ? "" : v;
          if (value) next.set(k, value);
          else next.delete(k);
        }
        return next;
      },
      { replace: true },
    );
  }

  // Typing settles before the query runs.
  useEffect(() => {
    if (searchInput.trim() === search) return;
    const timer = setTimeout(() => update({ search: searchInput.trim() }), 350);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchInput]);
  useEffect(() => setSearchInput(search), [search]);

  const toggleSave = useSaveToggle();
  const { data: profile } = useQuery({
    queryKey: ["service-provider-profile"],
    queryFn: () => apiFetch<ServiceProviderProfile>("/service-provider/profile"),
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
    queryKey: ["service-provider-feed", params.toString()],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => {
      // Every page is the same query: the controls travel with each request.
      const query = new URLSearchParams();
      for (const k of FILTER_KEYS) {
        const v = params.get(k);
        if (v) query.set(k, v === "1" && k !== "min_days" ? "true" : v);
      }
      query.set("sort", sort);
      query.set("offset", String(pageParam));
      return apiFetch<FeedPage>(`/service-provider/feed?${query.toString()}`);
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
  const filtersActive = FILTER_KEYS.some((k) => !!params.get(k));

  return (
    <main className="max-w-5xl mx-auto px-5 py-8">
      <div className="mb-6">
        <span className="font-mono text-[10.5px] uppercase tracking-widest text-amber-dark block mb-1">{t("service_provider.feed.eyebrow")}</span>
        <div className="flex items-baseline justify-between flex-wrap gap-2">
          <h1 className="font-display text-2xl font-semibold text-navy mb-1">{t("service_provider.feed.heading")}</h1>
          <Link to="/service-provider/saved" className="text-sm text-blue underline" data-testid="saved-link">★ {t("saved.heading")}</Link>
        </div>
        <p className="text-[13.5px] text-steel">{sort === "newest" ? t("service_provider.feed.sortedNewest") : sort === "deadline_latest" ? t("feed.sortedLatest") : sort === "relevance" ? t("feed.sortedRelevance") : t("service_provider.feed.sortedClosest")}</p>
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

      <div className="grid gap-2.5 mb-5" data-testid="feed-controls">
        <div className="flex flex-wrap items-center gap-2.5">
          <input
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder={t("service_provider.feed.searchPlaceholder")}
            aria-label={t("service_provider.feed.searchPlaceholder")}
            maxLength={200}
            className="border border-border rounded px-3 py-2 text-sm flex-1 min-w-[200px]"
          />
          <select value={category} onChange={(e) => update({ category_id: e.target.value })} aria-label={t("service_provider.feed.trade")} className="border border-border rounded px-3 py-2 text-sm font-mono">
            <option value="">{t("service_provider.feed.allTrades")}</option>
            {categories?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <select value={governorate} onChange={(e) => update({ governorate: e.target.value })} aria-label={t("location.governorate")} className="border border-border rounded px-3 py-2 text-sm font-mono">
            <option value="">{t("location.allGovernorates")}</option>
            {KUWAIT_GOVERNORATES.map((g) => (
              <option key={g} value={g}>
                {t(`location.${g}`)}
              </option>
            ))}
          </select>
          <select value={minDays} onChange={(e) => update({ min_days: e.target.value })} aria-label={t("feed.timeLeft")} className="border border-border rounded px-3 py-2 text-sm font-mono">
            <option value="">{t("feed.anyTimeLeft")}</option>
            {["3", "7", "14"].map((d) => (
              <option key={d} value={d}>
                {t("feed.atLeastDays").replace("{n}", d)}
              </option>
            ))}
          </select>
          <select value={sort} onChange={(e) => update({ sort: e.target.value })} aria-label={t("feed.sortBy")} className="border border-border rounded px-3 py-2 text-sm font-mono">
            {search && <option value="relevance">{t("feed.sortRelevance")}</option>}
            <option value="deadline">{t("service_provider.feed.sortClosest")}</option>
            <option value="deadline_latest">{t("feed.sortLatest")}</option>
            <option value="newest">{t("service_provider.feed.sortNewest")}</option>
          </select>
        </div>
        <div className="flex flex-wrap items-center gap-4 text-[13px] text-navy">
          <label className="flex items-center gap-1.5">
            <input type="checkbox" checked={myServices} onChange={(e) => update({ my_services: e.target.checked })} />
            {t("feed.myServices")}
          </label>
          <label className="flex items-center gap-1.5">
            <input type="checkbox" checked={myAreas} onChange={(e) => update({ my_areas: e.target.checked })} />
            {t("feed.myAreas")}
          </label>
          <label className="flex items-center gap-1.5">
            <input type="checkbox" checked={accepting} onChange={(e) => update({ accepting: e.target.checked })} />
            {t("feed.acceptingNow")}
          </label>
          {(filtersActive || !!params.get("sort")) && (
            <button type="button" onClick={() => { setSearchInput(""); setParams({}, { replace: true }); }} className="text-blue underline">
              {t("feed.clear")}
            </button>
          )}
        </div>
      </div>

      {isError && <QueryError onRetry={() => refetch()} />}

      {!isError && !isPending && !projects?.length && (
        <div className="border border-dashed border-border rounded p-10 text-center text-sm text-steel" data-testid="feed-empty">
          {filtersActive ? t("service_provider.feed.noMatch") : t("service_provider.feed.noOpenProjects")}
          {filtersActive && (
            <button type="button" onClick={() => { setSearchInput(""); setParams({}, { replace: true }); }} className="block mx-auto mt-2 text-blue underline">
              {t("feed.clear")}
            </button>
          )}
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
          const card = <OpportunityCard project={p} locked={!isSubscribed} onToggleSave={() => toggleSave.mutate({ projectId: p.id, save: !p.saved })} />;

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
