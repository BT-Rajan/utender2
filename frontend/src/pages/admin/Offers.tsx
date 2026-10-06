import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { AdminOffer } from "@/api/types";
import { QueryError } from "@/components/QueryError";
import { useI18n } from "@/i18n/I18nContext";
import { money } from "@/lib/money";

const STATUS_BADGE: Record<string, string> = {
  submitted: "bg-blue-tint text-blue",
  approved: "bg-green-tint text-green",
  rejected: "bg-border text-steel",
  withdrawn: "bg-border text-steel-light",
};

interface ProjectGroup {
  project_id: string;
  project_title: string;
  tender_type: string;
  latest_offer_at: string;
  offers: AdminOffer[];
}

// The API returns offers newest-first, not grouped by project (a bid on an
// older project can be more recent than one on a newer project) -- grouped
// client-side here rather than asking the backend to change its shape,
// since nothing else consuming /admin/offers wants it pre-grouped.
function groupByProject(offers: AdminOffer[]): ProjectGroup[] {
  const groups = new Map<string, ProjectGroup>();
  for (const o of offers) {
    let group = groups.get(o.project_id);
    if (!group) {
      group = { project_id: o.project_id, project_title: o.project_title, tender_type: o.tender_type, latest_offer_at: o.created_at, offers: [] };
      groups.set(o.project_id, group);
    }
    group.offers.push(o);
    if (o.created_at > group.latest_offer_at) group.latest_offer_at = o.created_at;
  }
  return Array.from(groups.values()).sort((a, b) => (a.latest_offer_at < b.latest_offer_at ? 1 : -1));
}

export function AdminOffersPage() {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const {
    data: offers,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["admin-offers"],
    queryFn: () => apiFetch<AdminOffer[]>("/admin/offers"),
  });

  const groups = useMemo(() => (offers ? groupByProject(offers) : []), [offers]);

  const toggle = (projectId: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(projectId)) next.delete(projectId);
      else next.add(projectId);
      return next;
    });

  return (
    <main className="max-w-5xl mx-auto px-5 py-8">
      <div className="mb-6">
        <span className="font-mono text-[10.5px] uppercase tracking-widest text-amber-dark block mb-1">{t("admin.offers.eyebrow")}</span>
        <h1 className="font-display text-2xl font-semibold text-navy mb-1">{t("admin.offers.heading")}</h1>
        <p className="text-[13.5px] text-steel">{offers?.length ?? 0} {t("admin.offers.total")}</p>
      </div>

      {isError ? (
        <QueryError onRetry={() => refetch()} />
      ) : !offers?.length ? (
        <div className="border border-dashed border-border rounded p-10 text-center text-sm text-steel">{t("admin.offers.empty")}</div>
      ) : (
        <div className="grid gap-2.5">
          {groups.map((g) => {
            const isOpen = expanded.has(g.project_id);
            const anySuspended = g.offers.some((o) => o.is_suspended);
            return (
              <div key={g.project_id} className="border border-border rounded bg-white overflow-hidden">
                <button
                  type="button"
                  onClick={() => toggle(g.project_id)}
                  aria-expanded={isOpen}
                  className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-blue-tint/20"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className={`shrink-0 font-mono text-[11px] text-steel transition-transform ${isOpen ? "rotate-90" : ""}`}>▶</span>
                    <span className="font-display font-semibold text-[14px] text-navy truncate">{g.project_title}</span>
                    {anySuspended && (
                      <span className="shrink-0 font-mono text-[10px] uppercase px-2 py-0.5 rounded-full bg-red-tint text-red">
                        {t("admin.offers.suspendedBadge")}
                      </span>
                    )}
                  </div>
                  <div className="shrink-0 flex items-center gap-3 font-mono text-[11px] text-steel-light">
                    <span>{g.tender_type.replace(/_/g, " ")}</span>
                    <span>{g.offers.length} {t("admin.offers.total")}</span>
                  </div>
                </button>

                {isOpen && (
                  <div className="border-t border-border">
                    <div className="px-4 pt-2.5">
                      <Link to={`/admin/projects/${g.project_id}`} className="text-[11.5px] text-navy hover:underline">
                        {t("admin.offers.viewProject")} →
                      </Link>
                    </div>
                    <div className="overflow-x-auto">
                    <table className="w-full border-collapse">
                      <thead>
                        <tr>
                          <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left py-2 px-4">{t("admin.offers.service_provider")}</th>
                          <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left py-2 px-2.5">{t("admin.offers.amount")}</th>
                          <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left py-2 px-2.5">{t("admin.offers.status")}</th>
                          <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left py-2 px-2.5">{t("admin.offers.submitted")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {g.offers.map((o) => (
                          <tr key={o.id} className="border-t border-border">
                            <td className="py-2.5 px-4 text-[13px]">
                              {o.service_provider_company_name ?? "—"}
                              {o.revision > 1 && <span className="text-[11px] text-steel-light"> · {t("admin.offers.revised")} x{o.revision - 1}</span>}
                            </td>
                            <td className="py-2.5 px-2.5 font-mono font-semibold text-navy text-sm">
                              {money(o.amount)}
                            </td>
                            <td className="py-2.5 px-2.5">
                              <div className="flex items-center gap-1.5">
                                <span className={`font-mono text-[10px] uppercase px-2 py-0.5 rounded-full ${STATUS_BADGE[o.status] ?? "bg-blue-tint text-steel"}`}>
                                  {o.status}
                                </span>
                                {o.is_suspended && (
                                  <span className="font-mono text-[10px] uppercase px-2 py-0.5 rounded-full bg-red-tint text-red">
                                    {t("admin.offers.suspendedBadge")}
                                  </span>
                                )}
                              </div>
                            </td>
                            <td className="py-2.5 px-2.5 font-mono text-[11px] text-steel-light">{new Date(o.created_at).toLocaleDateString()}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </main>
  );
}
