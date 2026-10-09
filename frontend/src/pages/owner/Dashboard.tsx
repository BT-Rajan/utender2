import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { Project, ProjectStatus } from "@/api/types";
import { formatDeadline } from "@/lib/format";
import { QueryError } from "@/components/QueryError";
import { outcomeLabel } from "@/components/ClosureOutcome";
import { PreviousProviders } from "@/components/PreviousProviders";
import { Reputation } from "@/components/Reputation";
import { useI18n } from "@/i18n/I18nContext";

function badgeClasses(status: string) {
  switch (status) {
    case "open":
      return "bg-green-tint text-green";
    case "closed":
    case "under_evaluation":
      return "bg-blue-tint text-blue";
    case "awarded":
      return "bg-amber/15 text-amber-dark";
    case "draft":
      return "bg-border text-steel";
    default:
      // no_award, canceled, expired
      return "bg-red-tint text-red";
  }
}

function statusFilters(t: (key: string) => string): { value: ProjectStatus | "all"; label: string }[] {
  const d = "owner.dashboard";
  return [
    { value: "all", label: t(`${d}.statusAll`) },
    { value: "draft", label: t(`${d}.statusDraft`) },
    { value: "open", label: t(`${d}.statusOpen`) },
    { value: "closed", label: t(`${d}.statusAwaitingReview`) },
    { value: "under_evaluation", label: t(`${d}.statusUnderEvaluation`) },
    { value: "awarded", label: t(`${d}.statusAwarded`) },
    { value: "no_award", label: t(`${d}.statusNoAward`) },
    { value: "canceled", label: t(`${d}.statusCanceled`) },
    { value: "expired", label: t(`${d}.statusExpired`) },
  ];
}

function KpiCard({ label, value, highlight }: { label: string; value: number; highlight?: boolean }) {
  return (
    <div className={`border rounded px-4 py-3 ${highlight ? "border-amber bg-amber/10" : "border-border bg-white"}`}>
      <div className="font-display text-2xl font-semibold text-navy leading-none">{value}</div>
      <div className="font-mono text-[10px] uppercase tracking-wide text-steel mt-1">{label}</div>
    </div>
  );
}

export function OwnerDashboardPage() {
  const { t } = useI18n();
  const {
    data: projects,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["owner-projects"],
    queryFn: () => apiFetch<Project[]>("/owner/projects"),
  });

  const [statusFilter, setStatusFilter] = useState<ProjectStatus | "all">("all");
  const [tenderTypeFilter, setTenderTypeFilter] = useState<"all" | "sealed" | "owner_visible">("all");
  const [search, setSearch] = useState("");

  const kpis = useMemo(() => {
    const list = projects ?? [];
    return {
      open: list.filter((p) => p.status === "open").length,
      awaitingReview: list.filter((p) => p.status === "closed").length,
      underEvaluation: list.filter((p) => p.status === "under_evaluation").length,
      awarded: list.filter((p) => p.status === "awarded").length,
      totalOffers: list.reduce((sum, p) => sum + (p.offer_count ?? 0), 0),
    };
  }, [projects]);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return (projects ?? []).filter((p) => {
      if (statusFilter !== "all" && p.status !== statusFilter) return false;
      if (tenderTypeFilter !== "all" && p.tender_type !== tenderTypeFilter) return false;
      if (term && !p.title.toLowerCase().includes(term) && !(p.address ?? "").toLowerCase().includes(term) && !(p.area ?? "").toLowerCase().includes(term)) return false;
      return true;
    });
  }, [projects, statusFilter, tenderTypeFilter, search]);

  const filtersActive = statusFilter !== "all" || tenderTypeFilter !== "all" || !!search.trim();

  return (
    <main className="max-w-5xl mx-auto px-5 py-8">
      <div className="flex items-end justify-between flex-wrap gap-4 mb-6">
        <div>
          <span className="font-mono text-[10.5px] uppercase tracking-widest text-amber-dark block mb-1">
            {t("owner.dashboard.eyebrow")}
          </span>
          <h1 className="font-display text-2xl font-semibold text-navy">{t("owner.dashboard.heading")}</h1>
        </div>
        <Link to="/owner/projects/new" className="bg-amber hover:bg-amber-dark text-white font-semibold text-sm rounded px-5 py-2.5">
          {t("owner.dashboard.newProject")}
        </Link>
      </div>
      {/* Stage 8.8: its own U-Tender track record, from providers' reviews. */}
      <div className="mb-6 max-w-xl"><Reputation of="owner" own url="/owner/reputation" /></div>
      {/* Stage 8.12: providers it has completed work with -- history, not a shortlist. */}
      <PreviousProviders />

      {!!projects?.length && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
          <KpiCard label={t("owner.dashboard.kpiOpen")} value={kpis.open} />
          <KpiCard label={t("owner.dashboard.kpiAwaitingReview")} value={kpis.awaitingReview} highlight={kpis.awaitingReview > 0} />
          <KpiCard label={t("owner.dashboard.kpiUnderEvaluation")} value={kpis.underEvaluation} />
          <KpiCard label={t("owner.dashboard.kpiAwarded")} value={kpis.awarded} />
          <KpiCard label={t("owner.dashboard.kpiTotalOffers")} value={kpis.totalOffers} />
        </div>
      )}

      {isError && <QueryError onRetry={() => refetch()} />}

      {!isError && !projects?.length && (
        <div className="border border-dashed border-border rounded p-10 text-center text-sm text-steel">
          {t("owner.dashboard.emptyStatePrefix")}{" "}
          <Link to="/owner/projects/new" className="text-navy underline">
            {t("owner.dashboard.emptyStateLink")}
          </Link>{" "}
          {t("owner.dashboard.emptyStateSuffix")}
        </div>
      )}

      {!!projects?.length && (
        <div className="flex flex-wrap items-center gap-2.5 mb-5">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("owner.dashboard.searchPlaceholder")}
            className="border border-border rounded px-3 py-2 text-sm flex-1 min-w-[200px]"
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as ProjectStatus | "all")}
            className="border border-border rounded px-3 py-2 text-sm font-mono"
          >
            {statusFilters(t).map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
          <select
            value={tenderTypeFilter}
            onChange={(e) => setTenderTypeFilter(e.target.value as "all" | "sealed" | "owner_visible")}
            className="border border-border rounded px-3 py-2 text-sm font-mono"
          >
            <option value="all">{t("owner.dashboard.allTenderTypes")}</option>
            <option value="sealed">{t("owner.dashboard.sealed")}</option>
            <option value="owner_visible">{t("owner.dashboard.ownerVisible")}</option>
          </select>
        </div>
      )}

      {!isError && projects?.length && !filtered.length && (
        <div className="border border-dashed border-border rounded p-10 text-center text-sm text-steel">
          {filtersActive ? t("owner.dashboard.noMatch") : t("owner.dashboard.nothingHere")}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {filtered.map((p) => {
          return (
            <Link key={p.id} to={`/owner/projects/${p.id}`} className="tblock rounded px-5 pt-4">
              <div className="flex justify-between items-start gap-2">
                <div>
                  <h3 className="font-display font-semibold text-[16.5px] mb-0.5">{p.title}</h3>
                  <p className="text-[12.5px] text-steel mb-3">{p.address}</p>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <span className={`font-mono text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full ${badgeClasses(p.status)}`}>
                    {outcomeLabel(t, p.status, p.closure_reason, p.transaction_status)}
                  </span>
                  {p.tender_type === "sealed" && (
                    <span className="font-mono text-[9px] uppercase text-steel-light">{t("owner.dashboard.sealed")}</span>
                  )}
                </div>
              </div>
              <p className="font-mono text-xs text-blue">
                {p.offer_count} {t("owner.dashboard.offersReceived")}
                {p.status === "closed" && <span className="text-amber-dark"> · {t("owner.dashboard.readyToReview")}</span>}
                {p.status === "draft" && p.updated_at && (
                  <span className="text-steel-light"> · {t("draftDetails.lastSavedShort").replace("{date}", formatDeadline(p.updated_at))}</span>
                )}
              </p>
              <div className="tblock-strip mt-4">
                <div className="tblock-field">
                  <span className="k">{t("owner.dashboard.deadline")}</span>
                  <span className="v">{formatDeadline(p.bid_deadline)}</span>
                </div>
                <div className="tblock-field">
                  <span className="k">{t("owner.dashboard.trade")}</span>
                  <span className="v">{p.trade || "—"}</span>
                </div>
                <div className="tblock-field">
                  <span className="k">{t("owner.dashboard.posted")}</span>
                  <span className="v">
                    {new Date(p.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                  </span>
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </main>
  );
}
