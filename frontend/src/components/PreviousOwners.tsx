import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiFetch } from "@/api/client";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";

interface PreviousOwner {
  owner_name: string | null;
  completed_transactions: number;
  last_completed_at: string | null;
  transactions: { project_id: string; title: string; completed_at: string | null }[];
}

// Stage 8.13: owners this provider organisation completed U-Tender work for --
// from completed transactions only, names only. Their new requirements reach
// the feed like anyone's, open to every eligible provider.
export function PreviousOwners() {
  const { t, language } = useI18n();
  const { data } = useQuery({ queryKey: ["previous-owners"], queryFn: () => apiFetch<PreviousOwner[]>("/service-provider/previous-owners") });
  if (!data?.length) return null;
  return (
    <section className="mb-6 max-w-xl border border-border rounded px-4 py-3 bg-white text-ink" data-testid="previous-owners">
      <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-2">{t("previous.ownersHeading")}</h3>
      <ul className="grid gap-2">
        {data.map((o, i) => (
          <li key={i} className="text-sm">
            <span className="font-semibold" dir="auto">{o.owner_name ?? t("ownerReview.theOwner")}</span>
            {" · "}
            {t("previous.together").replace("{n}", String(o.completed_transactions))}
            {o.last_completed_at && ` · ${t("previous.last")} ${fullDate(o.last_completed_at, language)}`}
            <div className="text-xs text-steel">
              {o.transactions.map((tx, j) => (
                <span key={tx.project_id}>
                  {j > 0 && ", "}
                  <Link to={`/service-provider/projects/${tx.project_id}/offer`} className="text-blue underline" dir="auto">{tx.title}</Link>
                </span>
              ))}
            </div>
          </li>
        ))}
      </ul>
      <p className="text-[11px] text-steel mt-2">{t("previous.ownersNote")}</p>
    </section>
  );
}
