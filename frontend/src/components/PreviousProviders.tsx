import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiFetch } from "@/api/client";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";

interface PreviousProvider {
  company_name: string | null;
  completed_transactions: number;
  last_completed_at: string | null;
  transactions: { project_id: string; title: string; completed_at: string | null }[];
}

// Stage 8.12: providers this owner organisation completed U-Tender work with --
// from completed transactions only. To work with one again, publish a new
// requirement as usual: it competes like any other.
export function PreviousProviders() {
  const { t, language } = useI18n();
  const { data } = useQuery({ queryKey: ["previous-providers"], queryFn: () => apiFetch<PreviousProvider[]>("/owner/previous-providers") });
  if (!data?.length) return null;
  return (
    <section className="mb-6 max-w-xl border border-border rounded px-4 py-3 bg-white text-ink" data-testid="previous-providers">
      <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-2">{t("previous.heading")}</h3>
      <ul className="grid gap-2">
        {data.map((p, i) => (
          <li key={i} className="text-sm">
            <span className="font-semibold" dir="auto">{p.company_name ?? t("owner.projectDetail.theServiceProvider")}</span>
            {" · "}
            {t("previous.together").replace("{n}", String(p.completed_transactions))}
            {p.last_completed_at && ` · ${t("previous.last")} ${fullDate(p.last_completed_at, language)}`}
            <div className="text-xs text-steel">
              {p.transactions.map((tx, j) => (
                <span key={tx.project_id}>
                  {j > 0 && ", "}
                  <Link to={`/owner/projects/${tx.project_id}`} className="text-blue underline" dir="auto">{tx.title}</Link>
                </span>
              ))}
            </div>
          </li>
        ))}
      </ul>
      <p className="text-[11px] text-steel mt-2">{t("previous.note")}</p>
    </section>
  );
}
