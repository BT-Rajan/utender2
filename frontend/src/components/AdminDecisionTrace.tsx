import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { AdminProjectDetail } from "@/api/types";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";

interface TimelineEntry {
  at: string;
  kind: string;
  party: "owner" | "provider" | null;
  actor_name: string | null;
  note: string | null;
  milestone_title: string | null;
}

// Stage 9.3: what became of a requirement, for an admin -- its version, the
// award and the transaction it started, with that transaction's own history
// (read-only, from the same agreement record the two parties see).
export function AdminDecisionTrace({ projectId, detail }: { projectId: string; detail: AdminProjectDetail }) {
  const { t, language } = useI18n();
  const { version, award, transaction } = detail;
  const { data: agreement } = useQuery({
    queryKey: ["admin-agreement", projectId],
    queryFn: () => apiFetch<{ timeline: TimelineEntry[] }>(`/projects/${projectId}/agreement`),
    enabled: !!transaction,
    retry: false,
  });
  const when = (v: string | null | undefined) => (v ? fullDate(v, language) : "—");
  return (
    <div className="bg-white border border-border rounded px-5 py-4.5 grid gap-3 text-sm" data-testid="admin-decision-trace">
      <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy">{t("trace.heading")}</h3>
      {version && (
        <p>
          {t("trace.version").replace("{n}", String(version.material_revision))}
          {version.amendments > 0 && ` · ${t("trace.amendments").replace("{n}", String(version.amendments))}`}
        </p>
      )}
      {award ? (
        <p>
          {t("trace.awardedTo")} <span className="font-semibold" dir="auto">{award.service_provider_company_name ?? "—"}</span>
          {award.amount && ` · ${award.amount}`} · {when(award.created_at)}
          {award.offer_priced_on != null && <> · {t("trace.pricedOn").replace("{n}", String(award.offer_priced_on))}{version && award.offer_priced_on < version.material_revision && <span className="text-amber-dark"> · {t("trace.earlierVersion")}</span>}</>}
        </p>
      ) : (
        <p className="text-steel">{t("trace.noAward")}</p>
      )}
      {transaction && (
        <div>
          <p>
            {t("trace.transaction")}: <span className="font-semibold">{t(`trace.status.${transaction.status}`)}</span>
            {transaction.status === "active" && transaction.on_hold_at && ` · ${t("trace.onHold")} ${when(transaction.on_hold_at)}`}
            {transaction.status === "active" && transaction.completion_status === "submitted" && ` · ${t("trace.completionSubmitted")}`}
            {transaction.completed_at && ` · ${when(transaction.completed_at)}`}
            {transaction.terminated_at && ` · ${when(transaction.terminated_at)}`}
          </p>
          {transaction.termination_reason && <p className="text-steel" dir="auto">{transaction.termination_reason}</p>}
          {agreement?.timeline?.length ? (
            <ol className="mt-2 grid gap-1 text-xs text-steel border-s-2 border-border ps-3">
              {agreement.timeline.map((e, i) => (
                <li key={i}>
                  <span className="font-mono">{when(e.at)}</span> · {t(`trace.kinds.${e.kind}`)}
                  {e.milestone_title && <span dir="auto"> — {e.milestone_title}</span>}
                  {e.party && ` (${t(e.party === "owner" ? "trace.owner" : "trace.provider")}${e.actor_name ? `: ${e.actor_name}` : ""})`}
                  {e.note && <span dir="auto"> — {e.note}</span>}
                </li>
              ))}
            </ol>
          ) : null}
        </div>
      )}
    </div>
  );
}
